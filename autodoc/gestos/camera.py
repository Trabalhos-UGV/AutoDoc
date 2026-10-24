"""A webcam, o MediaPipe e o laco que liga os dois a quem usa os gestos.

Dois usam: o controle do mouse (`executar`, aqui) e o quadro de desenho
(`quadro.py`). Os dois recebem a mesma coisa de `Sessao.quadros()`: a imagem ja
espelhada, as maos com os pontos espelhados e o instante do quadro.

**Detecta na imagem original, espelha depois.** O MediaPipe diz se a mao e
direita ou esquerda olhando a imagem; espelhada, ele troca as duas. A primeira
versao espelhava antes — como o projeto original, feito para a API antiga — e a
mao direita de quem usava virava a secundaria, que nao move o cursor.

**O modelo da mao nao vem no pip.** A API de tarefas pede o arquivo
`hand_landmarker.task` (7,8 MB), baixado do Google na primeira vez e guardado no
cache do usuario, fora do repositorio. Baixa por `curl`, que existe no macOS e
no Windows 10+: o Python do python.org no macOS nao traz a cadeia de
certificados, e o `urllib` falha no TLS — ele fica so de reserva.

**A janela da camera precisa da thread principal**, pelo mesmo motivo da janela
do app: no macOS o Cocoa nao desenha janela em outra. Por isso tudo aqui
bloqueia, e e chamado direto pelo `main.py`.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from autodoc.gestos import GestosIndisponiveis
from autodoc.gestos.controle import Controlador
from autodoc.gestos.reconhecimento import Gesto, Mao, aberturas, espelhar, separar_maos
from autodoc.gestos.sistema import RecursoIndisponivel, sistema_atual

logger = logging.getLogger(__name__)

URL_MODELO = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)

INSTALAR = "pip install -r requirements-gestos.txt"

# Teclas que fecham a janela da camera: Enter, Esc e q.
TECLAS_SAIR = {13, 27, ord("q")}

# Quadros seguidos sem imagem antes de desistir da camera.
FALHAS_TOLERADAS = 60

# Cores em BGR, como o OpenCV quer.
COR_PRINCIPAL = (80, 200, 60)
COR_SECUNDARIA = (0, 140, 255)
COR_LINHA = (200, 200, 200)


def pasta_cache(plataforma: str | None = None) -> Path:
    plataforma = plataforma or sys.platform
    if plataforma == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AutoDoc"
    if plataforma == "darwin":
        return Path.home() / "Library" / "Caches" / "AutoDoc"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "autodoc"


def obter_modelo(destino: Path | None = None, url: str = URL_MODELO, descricao: str = "o modelo da mao (7,8 MB)") -> Path:
    """O caminho do modelo, baixando-o se ainda nao estiver no cache.

    O padrao e o da mao; a mascara do Tetris usa o mesmo caminho para o do rosto.
    """
    destino = destino or pasta_cache() / "hand_landmarker.task"
    if destino.exists():
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".parcial")
    print(f"baixando {descricao}, so na primeira vez...")
    try:
        if shutil.which("curl"):
            subprocess.run(["curl", "-fsSL", "-o", str(parcial), url], check=True)
        else:
            urllib.request.urlretrieve(url, parcial)
    except (OSError, subprocess.CalledProcessError) as erro:
        parcial.unlink(missing_ok=True)
        raise GestosIndisponiveis(f"nao consegui baixar {descricao}: {erro}") from erro
    # Renomear so no fim: download interrompido nao deixa modelo pela metade.
    parcial.replace(destino)
    return destino


def importar_visao():
    """OpenCV e MediaPipe: o que a camera e o quadro de desenho precisam."""
    try:
        import cv2
        import mediapipe
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError as erro:
        # Nem todo ImportError diz o nome do que faltou: o do OpenCV sem numpy
        # vem sem nome, e a mensagem saia "falta None".
        raise GestosIndisponiveis(f"falta {erro.name or erro}; rode: {INSTALAR}") from erro
    return cv2, mediapipe, BaseOptions, vision


def importar_mouse():
    try:
        import pyautogui
    except ImportError as erro:
        raise GestosIndisponiveis(f"falta {erro.name}; rode: {INSTALAR}") from erro
    return pyautogui


class Detector:
    """O `HandLandmarker` em modo video, devolvendo pares (rotulo, pontos)."""

    def __init__(self, mediapipe, BaseOptions, vision, modelo: Path) -> None:
        self._mp = mediapipe
        self.conexoes = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
        opcoes = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(modelo)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._detector = vision.HandLandmarker.create_from_options(opcoes)
        self._ultimo_ms = -1

    def detectar(self, quadro_rgb) -> list[tuple[str, list]]:
        """As maos de um quadro NAO espelhado, com os pontos ja espelhados."""
        # O modo video exige carimbo de tempo estritamente crescente.
        agora = max(time.monotonic_ns() // 1_000_000, self._ultimo_ms + 1)
        self._ultimo_ms = agora
        imagem = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=quadro_rgb)
        resultado = self._detector.detect_for_video(imagem, agora)
        return [
            (lado[0].category_name, espelhar(pontos))
            for lado, pontos in zip(resultado.handedness, resultado.hand_landmarks)
        ]

    def fechar(self) -> None:
        self._detector.close()


class Sessao:
    """Camera aberta, detector carregado e a janela onde tudo aparece."""

    def __init__(self, cv2, mediapipe, BaseOptions, vision, camera: int, titulo: str) -> None:
        self.cv2 = cv2
        self.titulo = titulo
        sistema = sistema_atual(None)
        try:
            sistema.preparar_camera()
        except RecursoIndisponivel as erro:
            raise GestosIndisponiveis(str(erro)) from erro

        self.captura = cv2.VideoCapture(camera)
        if not self.captura.isOpened() and sys.platform == "win32":
            # O OpenCV abre pelo Media Foundation no Windows, e algumas webcams
            # so respondem pelo DirectShow.
            self.captura = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
        if not self.captura.isOpened():
            raise GestosIndisponiveis(
                f"não consegui abrir a câmera {camera}. Confira se outro programa está usando ela" + sistema.dica_camera()
            )
        try:
            self.detector = Detector(mediapipe, BaseOptions, vision, obter_modelo())
        except BaseException:
            self.captura.release()
            raise
        self.conexoes = self.detector.conexoes

    def __enter__(self) -> "Sessao":
        return self

    def __exit__(self, *_) -> None:
        self.detector.fechar()
        self.captura.release()
        self.cv2.destroyAllWindows()

    def quadros(self):
        """(imagem espelhada, maos, instante) ate a camera parar."""
        falhas = 0
        while True:
            lido, quadro = self.captura.read()
            if not lido:
                falhas += 1
                if falhas > FALHAS_TOLERADAS:
                    raise GestosIndisponiveis("a camera parou de mandar imagem")
                continue
            falhas = 0
            maos = self.detector.detectar(self.cv2.cvtColor(quadro, self.cv2.COLOR_BGR2RGB))
            yield self.cv2.flip(quadro, 1), maos, time.monotonic()

    def mostrar(self, imagem) -> int | None:
        """Desenha a imagem; devolve a tecla apertada, ou None para encerrar."""
        self.cv2.imshow(self.titulo, imagem)
        tecla = self.cv2.waitKey(1) & 0xFF
        if tecla in TECLAS_SAIR or not self.janela_aberta():
            return None
        return tecla

    def janela_aberta(self) -> bool:
        """Se a pessoa nao fechou a janela pelo botao do sistema.

        No Windows a propriedade cai para 0; no macOS a janela fechada some, e a
        consulta levanta erro em vez de responder.
        """
        try:
            return self.cv2.getWindowProperty(self.titulo, self.cv2.WND_PROP_VISIBLE) >= 1
        except self.cv2.error:
            return False


def desenhar(cv2, quadro, maos, conexoes, principal, legendas) -> None:
    """Os pontos das maos — a principal em verde — e as legendas no topo."""
    altura, largura = quadro.shape[:2]
    for _, pontos in maos:
        cor = COR_PRINCIPAL if pontos is principal else COR_SECUNDARIA
        tela = [(round(p.x * largura), round(p.y * altura)) for p in pontos]
        for inicio, fim in conexoes:
            cv2.line(quadro, tela[inicio], tela[fim], COR_LINHA, 2)
        for ponto in tela:
            cv2.circle(quadro, ponto, 4, cor, -1)
    for linha, texto in enumerate(legendas):
        cv2.putText(quadro, texto, (12, 32 + 30 * linha), cv2.FONT_HERSHEY_SIMPLEX, 0.8, COR_PRINCIPAL, 2)


def legenda(gesto: Gesto, pontos) -> str:
    """O gesto e as duas medidas da pinca — o que se olha para calibrar."""
    if pontos is None:
        return gesto.value
    indicador, medio = aberturas(pontos)
    return f"{gesto.value}  |  pinca indicador {indicador:.2f}  medio {medio:.2f}"


def executar(camera: int = 0, destro: bool = True) -> int:
    """Liga a camera e controla o mouse ate a pessoa fechar a janela."""
    cv2, mediapipe, BaseOptions, vision = importar_visao()
    pyautogui = importar_mouse()

    # Sem isto o PyAutoGUI dorme 0,1 s depois de cada chamada, e o cursor anda
    # a 10 quadros por segundo.
    pyautogui.PAUSE = 0
    sistema = sistema_atual(pyautogui)
    faltando = sistema.permissoes_faltando()
    if faltando:
        raise GestosIndisponiveis("\n".join(faltando))

    with Sessao(cv2, mediapipe, BaseOptions, vision, camera, "AutoDoc - gestos (Esc para sair)") as sessao:
        controlador = Controlador(pyautogui, sistema)
        principal, secundaria = Mao(), Mao()
        print(f"gestos ligados ({sistema.nome}). Esc fecha; mouse no canto da tela e o freio.")
        try:
            for quadro, maos, agora in sessao.quadros():
                pontos_principal, pontos_secundaria = separar_maos(maos, destro)
                controlador.aplicar(principal.atualizar(pontos_principal), pontos_principal, agora)
                controlador.aplicar_secundaria(secundaria.atualizar(pontos_secundaria), pontos_secundaria, agora)

                desenhar(cv2, quadro, maos, sessao.conexoes, pontos_principal, [legenda(principal.gesto, pontos_principal)])
                if sessao.mostrar(quadro) is None:
                    break
        except pyautogui.FailSafeException:
            print("freio acionado: o mouse foi levado ao canto da tela.")
        finally:
            controlador.soltar_tudo()
    return 0
