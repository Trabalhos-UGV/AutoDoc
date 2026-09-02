"""Instalador grafico do AutoDoc.

Sobe um servidor local, abre a tela de instalacao numa janela do sistema e
executa as seis etapas de verdade, com o log saindo na tela conforme acontecem.

Ao final, "Abrir o AutoDoc" sobe o servidor do aplicativo e leva a mesma janela
para ele — nao adianta terminar a instalacao e devolver a pessoa ao terminal.
"""

from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

from .. import __version__
from ..catalogo import Catalogo
from ..config import Config
from ..pipeline import Pipeline
from ..web import janela
from ..web.servidor import ESTATICO, Rotas, ServidorHTTP
from ..web.servidor import PORTA_PADRAO as PORTA_APP
from .instalador import Instalacao

logger = logging.getLogger(__name__)

PORTA = 8756

# A janela nativa, guardada para conseguir abrir o seletor de pastas do sistema
# a partir das threads que atendem a API.
_janela = None


class Instalador:
    """Estado do instalador enquanto ele roda."""

    def __init__(self) -> None:
        config = Config.carregar()
        self.pasta_entrada = config.pasta_entrada
        self.pasta_saida = config.pasta_saida
        self.instalacao: Instalacao | None = None
        self.ouvintes: list[queue.Queue] = []
        self.trava = threading.Lock()
        self.servidor_app = None

    # ------------------------------------------------------------ eventos

    def inscrever(self) -> queue.Queue:
        fila: queue.Queue = queue.Queue()
        with self.trava:
            self.ouvintes.append(fila)
            # Quem chega depois do inicio precisa ver onde a instalacao esta,
            # senao fica olhando uma tela parada em 0%.
            if self.instalacao:
                fila.put(self.instalacao.instantaneo())
        return fila

    def desinscrever(self, fila: queue.Queue) -> None:
        with self.trava:
            if fila in self.ouvintes:
                self.ouvintes.remove(fila)

    def _emitir(self, estado: dict) -> None:
        with self.trava:
            for fila in list(self.ouvintes):
                fila.put(estado)

    # ------------------------------------------------------------ acoes

    def instalar(self, pasta_entrada: str | None = None) -> None:
        """Comeca a instalacao numa thread, para a tela nao congelar."""
        if pasta_entrada:
            self._apontar(Path(pasta_entrada).expanduser())

        if self.instalacao and not self.instalacao.concluido:
            return  # ja esta rodando

        self.instalacao = Instalacao(self.pasta_entrada)

        def rodar() -> None:
            for estado in self.instalacao.executar():
                self._emitir(estado)

        threading.Thread(target=rodar, daemon=True).start()

    def _apontar(self, pasta_entrada: Path) -> None:
        """Registra a pasta escolhida — em memoria **e no config.json**.

        Sem gravar, escolher outra pasta so mudava o texto da tela: a instalacao
        seguia usando a pasta anterior e o AutoDoc subia vigiando o lugar
        errado, com a tela mostrando o certo. Era o defeito que fazia a janela
        abrir vazia depois de apontar para uma pasta pessoal.
        """
        self.pasta_entrada = pasta_entrada
        config = Config.carregar()
        config.pasta_entrada = pasta_entrada
        config.pasta_saida = config.saida_ao_lado()
        config.salvar()
        self.pasta_saida = config.pasta_saida

    def escolher_pasta(self) -> str | None:
        """Abre o seletor de pastas do proprio sistema e guarda a escolha."""
        if _janela is None:
            return None
        try:
            import webview
            escolha = _janela.create_file_dialog(
                webview.FOLDER_DIALOG, directory=str(self.pasta_entrada)
            )
        except Exception:
            logger.exception("nao foi possivel abrir o seletor de pastas")
            return None

        if not escolha:
            return None
        self._apontar(Path(escolha[0]))
        return str(self.pasta_entrada)

    def concluir(self) -> str:
        """Sobe o aplicativo e devolve o endereco para a janela seguir."""
        if self.servidor_app is None:
            from ..web.servidor import Servidor

            config = Config.carregar()
            config.preparar_pastas()
            catalogo = Catalogo(config.pasta_saida)
            self.servidor_app = Servidor(
                config, catalogo, Pipeline(config, catalogo), PORTA_APP
            )
            self.servidor_app.iniciar()

        return f"http://127.0.0.1:{PORTA_APP}/"


class RotasInstalador(Rotas):
    """Serve a tela do instalador e responde a API dele."""

    def __init__(self, *args, instalador: Instalador, **kwargs) -> None:
        self.instalador = instalador
        # Pula o __init__ de Rotas, que espera um Servidor de aplicativo.
        super(Rotas, self).__init__(*args, directory=str(ESTATICO), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - nome exigido pela biblioteca
        rota = urlparse(self.path).path

        if rota == "/":
            self.path = "/instalador.html"
            return super(Rotas, self).do_GET()

        if rota == "/api/estado":
            return self._json({
                "modo": "real",
                "versao": __version__,
                "pasta": str(self.instalador.pasta_entrada),
                "pasta_saida": str(self.instalador.pasta_saida),
            })

        if rota == "/api/eventos":
            return self._eventos()

        if not rota.startswith("/api/"):
            return super(Rotas, self).do_GET()

        self._json({"erro": "rota desconhecida"}, 404)

    def do_POST(self) -> None:  # noqa: N802 - nome exigido pela biblioteca
        rota = urlparse(self.path).path
        corpo = self._corpo()

        if rota == "/api/instalar":
            self.instalador.instalar(corpo.get("pasta_entrada"))
            return self._json({"iniciado": True})

        if rota == "/api/escolher-pasta":
            # A saida acompanha a entrada, entao a tela precisa das duas para
            # dizer onde os documentos vao ficar.
            return self._json({
                "caminho": self.instalador.escolher_pasta(),
                "pasta_saida": str(self.instalador.pasta_saida),
            })

        if rota == "/api/concluir":
            return self._json({"url": self.instalador.concluir()})

        self._json({"erro": "rota desconhecida"}, 404)

    def _eventos(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        fila = self.instalador.inscrever()
        try:
            while True:
                try:
                    estado = fila.get(timeout=15)
                    corpo = json.dumps(estado, ensure_ascii=False)
                    self.wfile.write(f"data: {corpo}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.instalador.desinscrever(fila)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    instalador = Instalador()
    servidor = ServidorHTTP(
        ("127.0.0.1", PORTA), partial(RotasInstalador, instalador=instalador)
    )
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{PORTA}/"
    print(f"Instalador do AutoDoc {__version__} — {url}")

    def guardar(criada) -> None:
        global _janela
        _janela = criada

    try:
        # Uma funcao so para os dois caminhos. Antes daqui havia uma copia que
        # tratava apenas `ImportError`, e no Linux sem GTK o pywebview levanta
        # `WebViewException` — que escapava e derrubava o instalador inteiro
        # com um traceback, em vez de abrir a mesma tela no navegador.
        janela.abrir(
            url,
            titulo=f"Instalador do AutoDoc — {__version__}",
            largura=980,
            altura=760,
            minimo=(820, 640),
            fundo="#16140f",
            ao_criar=guardar,
        )
    finally:
        servidor.shutdown()
        servidor.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
