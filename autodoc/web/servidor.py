"""Servidor local que liga as telas ao nucleo do AutoDoc.

Fala o contrato que autodoc/web/estatico/js/app.js ja esperava desde que as
telas foram construidas:

    GET /api/estado                 existir ja significa "modo real"
    GET /api/documentos?cat=&q=     {linhas, todos, categorias, estatisticas}
    GET /api/eventos                SSE — um evento por documento novo

Roda so em 127.0.0.1: e um programa de mesa, o catalogo tem o conteudo dos
documentos da pessoa, e nada disso tem por que estar acessivel na rede.

O `/api/eventos` e o que faz a linha aparecer sozinha na tela quando um arquivo
cai na pasta: o observador do watchdog avisa este modulo, que empurra o
documento para todas as telas abertas.
"""

from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__
from ..catalogo import Catalogo
from ..classificador import ROTULOS
from ..monitor import criar_observador, processar_pendentes
from ..pipeline import Pipeline

logger = logging.getLogger(__name__)

ESTATICO = Path(__file__).resolve().parent / "estatico"
PORTA_PADRAO = 8757
TODOS = "Todos"

# Teto do que vai para a tela de uma vez. A tela mostra uma lista, nao um
# relatorio; alem disso o painel de detalhe carrega o texto inteiro de cada um.
LIMITE = 500

# Rotulo -> categoria interna, para o filtro da barra lateral voltar traduzido.
CATEGORIAS_POR_ROTULO = {rotulo: chave for chave, rotulo in ROTULOS.items()}


def _formatar_data(iso: str | None) -> str:
    """2026-03-12 -> 12/03/2026, que e como se le data em portugues."""
    if not iso:
        return "—"
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


class ServidorHTTP(ThreadingHTTPServer):
    """ThreadingHTTPServer que nao grita quando uma tela e fechada.

    Fechar a janela derruba a conexao do SSE no meio, e o padrao da biblioteca
    e despejar um traceback no terminal. Isso e comportamento normal de quem
    fecha um programa, nao defeito — e um usuario nao tem por que ver pilha de
    excecao por ter fechado a janela.
    """

    def handle_error(self, request, client_address) -> None:
        excecao = sys.exc_info()[1]
        if isinstance(excecao, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class Servidor:
    """Sobe o servidor HTTP e o monitoramento, e liga um no outro."""

    def __init__(
        self,
        config,
        catalogo: Catalogo,
        pipeline: Pipeline,
        porta: int = PORTA_PADRAO,
    ) -> None:
        self.config = config
        self.catalogo = catalogo
        self.pipeline = pipeline
        self.porta = porta
        self._http: ThreadingHTTPServer | None = None
        self._observador = None
        # Uma fila por tela aberta. Sem isso, duas janelas brigariam pelos
        # mesmos eventos e cada documento novo apareceria em so uma delas.
        self._ouvintes: list[queue.Queue] = []
        self._trava = threading.Lock()

    # ------------------------------------------------------------ dados

    def _linha(self, registro) -> dict:
        """Converte uma ficha do catalogo no formato que a tela consome."""
        dados = dict(registro)
        categoria = dados["categoria"]
        caminho = Path(dados["caminho"])

        try:
            destino = str(caminho.parent.relative_to(self.config.pasta_saida)) + "/"
        except ValueError:
            destino = str(caminho.parent) + "/"

        return {
            "id": dados["id"],
            "arquivo": dados["arquivo"],
            "origem": dados.get("origem") or "—",
            "tipo": ROTULOS.get(categoria, categoria),
            "categoria": categoria,
            "confianca": f"{(dados.get('confianca') or 0) * 100:.0f}%",
            "data": _formatar_data(dados.get("data_documento")),
            "destino": destino,
            "regra": dados.get("regra") or "",
            "chaves": dados.get("palavras_chave") or [],
            "trecho": dados.get("trecho") or "",
            "etapas": dados.get("etapas") or [],
        }

    def _categorias(self) -> list[dict]:
        contagem = self.catalogo.contar_por_categoria()
        total = sum(contagem.values())

        lista = [{"nome": TODOS, "contagem": str(total)}]
        for categoria, quantos in contagem.items():
            lista.append({
                "nome": ROTULOS.get(categoria, categoria),
                "contagem": str(quantos),
            })
        return lista

    def _documentos(self, categoria: str, termo: str) -> dict:
        registros = (
            self.catalogo.buscar(termo, LIMITE) if termo.strip()
            else self.catalogo.listar(LIMITE)
        )
        linhas = [self._linha(r) for r in registros]

        if categoria and categoria != TODOS:
            alvo = CATEGORIAS_POR_ROTULO.get(categoria, categoria)
            linhas = [l for l in linhas if l["categoria"] == alvo]

        # `todos` existe porque o painel de detalhe precisa achar o documento
        # selecionado mesmo depois de ele sair do filtro.
        todos = [self._linha(r) for r in self.catalogo.listar(LIMITE)]

        return {
            "linhas": linhas,
            "todos": todos,
            "categorias": self._categorias(),
            "estatisticas": self.catalogo.estatisticas(),
        }

    def _estado(self) -> dict:
        return {
            "modo": "real",
            "versao": __version__,
            "pasta": str(self.config.pasta_entrada),
            "pasta_saida": str(self.config.pasta_saida),
            "busca": "índice interno",
            "backup": bool(self.config.pasta_backup),
        }

    # ----------------------------------------------------------- eventos

    def _anunciar(self, resultado) -> None:
        """Avisa todas as telas abertas que chegou documento novo.

        A linha vem do proprio resultado, e nao de "o primeiro da listagem": a
        listagem ordena por data do documento, entao uma conta de 2019 que
        acabou de ser processada faria a tela anunciar outro arquivo.
        """
        if resultado.documento is None:
            return
        linha = self._linha(self.catalogo.como_dict(resultado.documento))

        with self._trava:
            for fila in list(self._ouvintes):
                fila.put(linha)

    def _inscrever(self) -> queue.Queue:
        fila: queue.Queue = queue.Queue()
        with self._trava:
            self._ouvintes.append(fila)
        return fila

    def _desinscrever(self, fila: queue.Queue) -> None:
        with self._trava:
            if fila in self._ouvintes:
                self._ouvintes.remove(fila)

    # ------------------------------------------------------------ ciclo

    def iniciar(self) -> str:
        """Sobe o HTTP e o observador. Devolve a URL para abrir."""
        manipulador = partial(Rotas, servidor=self)
        self._http = ServidorHTTP(("127.0.0.1", self.porta), manipulador)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

        # A pasta organizada e a verdade: antes de mostrar qualquer coisa, o
        # catalogo se acerta com ela — o que foi apagado some, e o que foi
        # colocado la a mao entra.
        self.catalogo.reconciliar(self.pipeline.analisar)

        pendentes = processar_pendentes(self.pipeline)
        if pendentes:
            logger.info("%d documento(s) que ja estavam na pasta", pendentes)

        self._observador = criar_observador(self.pipeline, ao_processar=self._anunciar)
        logger.info("monitorando %s", self.config.pasta_entrada)

        return f"http://127.0.0.1:{self.porta}/"

    def parar(self) -> None:
        if self._observador:
            self._observador.stop()
            self._observador.join()
        if self._http:
            self._http.shutdown()
            self._http.server_close()


class Rotas(SimpleHTTPRequestHandler):
    """Serve os arquivos das telas e responde a API."""

    # HTTP/1.0 fecha a conexao ao terminar cada resposta, e conexao fechada e
    # exatamente o que um EventSource entende como erro — a tela passaria a
    # vida dizendo "watchdog desconectado". Todas as respostas daqui mandam
    # Content-Length, menos o proprio SSE, que e um fluxo aberto de proposito.
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, servidor: Servidor, **kwargs) -> None:
        self.servidor = servidor
        super().__init__(*args, directory=str(ESTATICO), **kwargs)

    def log_message(self, formato, *args) -> None:
        # Uma linha por arquivo servido so atrapalha quem esta olhando o log.
        pass

    # ------------------------------------------------------------ ajuda

    def _json(self, dados: dict, codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _sse(self) -> None:
        """Mantem a conexao aberta mandando cada documento novo que chegar."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        fila = self.servidor._inscrever()
        try:
            while True:
                try:
                    linha = fila.get(timeout=15)
                    corpo = json.dumps(linha, ensure_ascii=False)
                    self.wfile.write(f"data: {corpo}\n\n".encode("utf-8"))
                except queue.Empty:
                    # Comentario SSE: so para o navegador (e qualquer proxy)
                    # saber que a conexao continua viva.
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # a tela foi fechada
        finally:
            self.servidor._desinscrever(fila)

    # ------------------------------------------------------------ rotas

    def do_GET(self) -> None:  # noqa: N802 - nome exigido pela biblioteca
        partes = urlparse(self.path)
        rota = partes.path

        if rota == "/":
            self.path = "/app.html"
            return super().do_GET()

        if not rota.startswith("/api/"):
            return super().do_GET()

        if rota == "/api/estado":
            return self._json(self.servidor._estado())

        if rota == "/api/eventos":
            return self._sse()

        if rota == "/api/documentos":
            consulta = parse_qs(partes.query)
            return self._json(
                self.servidor._documentos(
                    categoria=consulta.get("cat", [""])[0],
                    termo=consulta.get("q", [""])[0],
                )
            )

        self._json({"erro": "rota desconhecida"}, 404)
