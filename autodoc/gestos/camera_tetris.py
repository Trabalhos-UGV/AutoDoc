"""A camera comandando o Tetris.

Cada quadro da camera vira um passo do jogo: a mao principal e reconhecida,
o gesto confirmado vai para os `Comandos`, e o retrato sai para a tela junto
com os pontos da mao, que a tela desenha por cima da imagem.

**A camera abre na thread principal; os quadros sao lidos em outra.** No macOS
o OpenCV nao consegue pedir a permissao da camera fora da thread principal —
ele mesmo avisa: "can not spin main run loop from other thread". E a janela
tambem precisa da principal. Entao a ordem e: a thread principal abre a
`Sessao` (camera e modelo), sobe o servidor e o laco em threads, e fica com a
janela ate ela fechar. Ler quadros de uma camera ja aberta funciona de qualquer
thread.

**Se a camera parar no meio, o jogo nao para.** O laco cai para o modo de
teclado e a tela troca sozinha a lista de gestos pela de teclas. Numa
apresentacao, perder a camera e perder o efeito, nao a partida.
"""

from __future__ import annotations

import logging
import threading

from autodoc.gestos import GestosIndisponiveis
from autodoc.gestos.camera import Sessao, importar_visao
from autodoc.gestos.reconhecimento import Mao, separar_maos
from autodoc.gestos.servidor_tetris import PORTA_TETRIS, Partida, ServidorTetris, rodar_sem_camera

logger = logging.getLogger(__name__)

# A imagem que vai para a tela: o painel da camera tem uns 240 px de largura,
# entao 480 cobre telas de alta densidade sem pesar.
LARGURA_DA_IMAGEM = 480
QUALIDADE_JPEG = 70

# Uma imagem a cada tantos quadros: 15 por segundo bastam para o video; o jogo
# continua recebendo os 30.
QUADROS_POR_IMAGEM = 2


def maos_para_tela(maos, principal) -> list[dict]:
    """Os pontos de cada mao, arredondados, marcando qual e a que comanda."""
    return [
        {"principal": pontos is principal, "pontos": [[round(p.x, 3), round(p.y, 3)] for p in pontos]}
        for _, pontos in maos
    ]


def codificar(cv2, imagem) -> tuple[bytes, tuple[int, int]]:
    """A imagem reduzida e em JPEG, com o tamanho que ela ficou."""
    altura, largura = imagem.shape[:2]
    tamanho = (LARGURA_DA_IMAGEM, round(altura * LARGURA_DA_IMAGEM / largura))
    _, jpeg = cv2.imencode(".jpg", cv2.resize(imagem, tamanho), [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG])
    return jpeg.tobytes(), tamanho


def rodar_com_camera(sessao: Sessao, partida: Partida, servidor: ServidorTetris, parar: threading.Event, cv2, destro: bool = True) -> None:
    mao = Mao()
    try:
        for numero, (imagem, maos, agora) in enumerate(sessao.quadros()):
            if parar.is_set():
                return
            principal, _ = separar_maos(maos, destro)
            partida.passo(agora, mao.atualizar(principal), principal, maos_para_tela(maos, principal))
            servidor.publicar(partida.retrato())
            if numero % QUADROS_POR_IMAGEM == 0:
                jpeg, partida.camera_tamanho = codificar(cv2, imagem)
                servidor.publicar_imagem(jpeg)
    except GestosIndisponiveis as erro:
        logger.warning("a camera parou (%s); o jogo segue pelo teclado", erro)
        partida.camera = False
        partida.maos = []
        rodar_sem_camera(partida, servidor, parar)


def jogar_com_camera(camera: int = 0, destro: bool = True, porta: int = PORTA_TETRIS) -> int:
    """Abre o Tetris na janela nativa, comandado pela mao. Bloqueia ate fechar."""
    from autodoc.web import janela

    cv2, mediapipe, BaseOptions, vision = importar_visao()
    with Sessao(cv2, mediapipe, BaseOptions, vision, camera, "AutoDoc - Tetris") as sessao:
        partida = Partida()
        partida.camera = True
        servidor = ServidorTetris(partida, porta)
        url = servidor.iniciar()
        parar = threading.Event()
        laco = threading.Thread(target=rodar_com_camera, args=(sessao, partida, servidor, parar, cv2, destro), daemon=True)
        laco.start()
        try:
            janela.abrir(url, titulo="AutoDoc — Tetris")
        finally:
            parar.set()
            # Esperar o laco antes de a Sessao soltar a camera: solta-la no meio
            # de uma leitura derruba o processo em alguns sistemas.
            laco.join(timeout=2)
            servidor.parar()
    return 0
