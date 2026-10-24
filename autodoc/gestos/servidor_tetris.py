"""Servidor local do Tetris: entrega a tela e transmite a partida.

    GET  /                   a tela (tetris.html)
    GET  /api/estado         o retrato atual, sem consumir os eventos
    GET  /api/eventos        SSE — um retrato por quadro, 30 por segundo
    POST /api/tecla          {tecla} com o `event.key` do navegador

E o mesmo arranjo do aplicativo: um servidor so em 127.0.0.1, as telas em HTML
e a janela nativa por cima. As rotas herdam de `web.servidor.Rotas`, que ja
resolve o JSON, o SSE e o HTTP/1.1 que o `EventSource` precisa.

**Uma trava em volta da partida.** O laco do jogo (ou da camera) e as teclas
que chegam pela rede rodam em threads diferentes e mexem no mesmo `Jogo`; sem a
trava, uma tecla no meio de um quadro poderia ver a peca pela metade.

**Fila curta por tela.** Cada retrato carrega o jogo inteiro, entao perder um
nao faz falta: a tela que engasgou pula para o mais novo em vez de acumular
atraso. A fila do aplicativo nao tem limite porque la cada evento e um
documento; aqui sao 30 por segundo.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from functools import partial

from autodoc.gestos.comandos_tetris import Comandos
from autodoc.gestos.tetris import ROTACOES, TIPOS, Jogo
from autodoc.web.servidor import Rotas, abrir_porta

logger = logging.getLogger(__name__)

PORTA_TETRIS = 8758

QUADROS_POR_SEGUNDO = 60  # do laco sem camera
PUBLICACOES_POR_SEGUNDO = 30  # retratos para a tela
FILA_POR_TELA = 4

# As pecas como nascem, para a tela desenhar a fila e a guardada. Vao junto do
# retrato em vez de copiadas no JavaScript: uma fonte so, sem chance de as duas
# divergirem.
FORMAS = {tipo: [list(celula) for celula in ROTACOES[tipo][0]] for tipo in TIPOS}


class Partida:
    """O jogo e o controle dele, com o que a tela precisa alem das regras."""

    def __init__(self, jogo: Jogo | None = None) -> None:
        self.jogo = jogo or Jogo()
        self.comandos = Comandos(self.jogo)
        # Preenchidos pela camera, quando houver: se ela esta ligada e as maos
        # do quadro, ja no formato que a tela desenha.
        self.camera = False
        self.maos: list[dict] = []
        self._eventos: list[dict] = []
        self._trava = threading.Lock()

    def passo(self, agora: float, gesto=None, pontos=None, maos: list[dict] | None = None) -> None:
        """Um quadro. Sem `gesto` e so o tempo passando — o modo sem camera."""
        with self._trava:
            if gesto is not None:
                self.comandos.aplicar(gesto, pontos, agora)
                self.maos = maos or []
            self.jogo.atualizar(agora)
            self._eventos += self.jogo.tirar_eventos()

    def tecla(self, nome: str) -> bool:
        with self._trava:
            aceita = self.comandos.tecla(nome)
            self._eventos += self.jogo.tirar_eventos()
            return aceita

    def retrato(self, consumir: bool = True) -> dict:
        """O jogo, o controle e os eventos desde o ultimo retrato.

        Quem transmite consome os eventos, para cada animacao acontecer uma vez
        so. A consulta avulsa de `/api/estado` nao: ela nao pode roubar o
        "linha completa" que a tela estava para receber.
        """
        with self._trava:
            eventos = self._eventos
            if consumir:
                self._eventos = []
            return {
                **self.jogo.estado(),
                "controle": self.comandos.estado(),
                "camera": self.camera,
                "maos": self.maos,
                "eventos": eventos,
                "formas": FORMAS,
            }


class ServidorTetris:
    def __init__(self, partida: Partida, porta: int = PORTA_TETRIS) -> None:
        self.partida = partida
        self.porta = porta
        self._http = None
        self._ouvintes: list[queue.Queue] = []
        self._trava = threading.Lock()

    def iniciar(self) -> str:
        self._http, self.porta = abrir_porta(partial(RotasTetris, servidor=self), self.porta)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.porta}/"

    def parar(self) -> None:
        if self._http:
            self._http.shutdown()
            self._http.server_close()

    def publicar(self, retrato: dict) -> None:
        with self._trava:
            for fila in self._ouvintes:
                if fila.full():
                    fila.get_nowait()
                fila.put_nowait(retrato)

    # O nome e o formato que `Rotas._sse` espera do servidor.
    def _inscrever(self) -> queue.Queue:
        fila: queue.Queue = queue.Queue(maxsize=FILA_POR_TELA)
        with self._trava:
            self._ouvintes.append(fila)
        return fila

    def _desinscrever(self, fila: queue.Queue) -> None:
        with self._trava:
            if fila in self._ouvintes:
                self._ouvintes.remove(fila)


class RotasTetris(Rotas):
    def do_GET(self) -> None:  # noqa: N802 - nome exigido pela biblioteca
        rota = self.path.split("?", 1)[0]
        if rota == "/":
            self.path = "/tetris.html"
            return super(Rotas, self).do_GET()
        if not rota.startswith("/api/"):
            return super(Rotas, self).do_GET()
        if rota == "/api/estado":
            return self._json(self.servidor.partida.retrato(consumir=False))
        if rota == "/api/eventos":
            return self._sse()
        self._json({"erro": "rota desconhecida"}, 404)

    def do_POST(self) -> None:  # noqa: N802 - nome exigido pela biblioteca
        if self.path.split("?", 1)[0] == "/api/tecla":
            tecla = str(self._corpo().get("tecla", ""))
            return self._json({"aceita": self.servidor.partida.tecla(tecla)})
        self._json({"erro": "rota desconhecida"}, 404)


def rodar_sem_camera(partida: Partida, servidor: ServidorTetris, parar: threading.Event, relogio=time.monotonic) -> None:
    """O laco do jogo quando so o teclado comanda: tempo passando e retratos saindo.

    A folga de meio quadro na conta da publicacao e o que mantem os 30 por
    segundo: sem ela, um arredondamento deixava o intervalo um fio abaixo de
    1/30 e a publicacao escorregava para o quadro seguinte — 20 por segundo.
    """
    intervalo = 1 / PUBLICACOES_POR_SEGUNDO - 0.5 / QUADROS_POR_SEGUNDO
    ultimo = -1.0
    while not parar.is_set():
        agora = relogio()
        partida.passo(agora)
        if agora - ultimo >= intervalo:
            servidor.publicar(partida.retrato())
            ultimo = agora
        parar.wait(1 / QUADROS_POR_SEGUNDO)


def jogar_pelo_teclado(porta: int = PORTA_TETRIS) -> int:
    """Abre o Tetris na janela nativa, so com o teclado. Bloqueia ate fechar.

    A janela fica com a thread principal, como a do aplicativo; o servidor e o
    laco do jogo vao para threads, e descem quando a janela fecha.
    """
    from autodoc.web import janela

    partida = Partida()
    servidor = ServidorTetris(partida, porta)
    url = servidor.iniciar()
    parar = threading.Event()
    laco = threading.Thread(target=rodar_sem_camera, args=(partida, servidor, parar), daemon=True)
    laco.start()
    try:
        janela.abrir(url, titulo="AutoDoc — Tetris")
    finally:
        parar.set()
        laco.join(timeout=2)
        servidor.parar()
    return 0
