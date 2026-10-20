"""A webcam, o MediaPipe e o laco que liga os dois ao controlador.

**O modelo da mao nao vem no pip.** A API de tarefas do MediaPipe pede o arquivo
`hand_landmarker.task` (7,8 MB), baixado do Google na primeira vez e guardado no
cache do usuario, fora do repositorio. Baixa por `curl`, que existe no macOS e
no Windows 10+: o Python do python.org no macOS nao traz a cadeia de
certificados, e o `urllib` falha no TLS — ele fica so de reserva.

**A janela da camera precisa da thread principal**, pelo mesmo motivo da janela
do app: no macOS o Cocoa nao desenha janela em outra. Por isso `executar()`
bloqueia, e e chamada direto pelo `main.py`.
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
from autodoc.gestos.reconhecimento import Gesto, Mao, separar_maos
from autodoc.gestos.sistema import sistema_atual

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

TITULO = "AutoDoc - gestos (Esc para sair)"


def pasta_cache(plataforma: str | None = None) -> Path:
    plataforma = plataforma or sys.platform
    if plataforma == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AutoDoc"
    if plataforma == "darwin":
        return Path.home() / "Library" / "Caches" / "AutoDoc"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "autodoc"


def obter_modelo(destino: Path | None = None) -> Path:
    """O caminho do modelo, baixando-o se ainda nao estiver no cache."""
    destino = destino or pasta_cache() / "hand_landmarker.task"
    if destino.exists():
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".parcial")
    print("baixando o modelo da mao (7,8 MB, so na primeira vez)...")
    try:
        if shutil.which("curl"):
            subprocess.run(["curl", "-fsSL", "-o", str(parcial), URL_MODELO], check=True)
        else:
            urllib.request.urlretrieve(URL_MODELO, parcial)
    except (OSError, subprocess.CalledProcessError) as erro:
        parcial.unlink(missing_ok=True)
        raise GestosIndisponiveis(f"nao consegui baixar o modelo da mao: {erro}") from erro
    # Renomear so no fim: download interrompido nao deixa modelo pela metade.
    parcial.replace(destino)
    return destino


def importar_dependencias():
    try:
        import cv2
        import mediapipe
        import pyautogui
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError as erro:
        raise GestosIndisponiveis(f"falta {erro.name}; rode: {INSTALAR}") from erro
    return cv2, mediapipe, pyautogui, BaseOptions, vision


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
        # O modo video exige carimbo de tempo estritamente crescente.
        agora = max(time.monotonic_ns() // 1_000_000, self._ultimo_ms + 1)
        self._ultimo_ms = agora
        imagem = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=quadro_rgb)
        resultado = self._detector.detect_for_video(imagem, agora)
        return [
            (lado[0].category_name, pontos)
            for lado, pontos in zip(resultado.handedness, resultado.hand_landmarks)
        ]

    def fechar(self) -> None:
        self._detector.close()


def desenhar(cv2, quadro, maos, conexoes, gesto: int) -> None:
    altura, largura = quadro.shape[:2]
    for _, pontos in maos:
        tela = [(round(p.x * largura), round(p.y * altura)) for p in pontos]
        for inicio, fim in conexoes:
            cv2.line(quadro, tela[inicio], tela[fim], (200, 200, 200), 2)
        for ponto in tela:
            cv2.circle(quadro, ponto, 4, (0, 140, 255), -1)
    nome = Gesto(gesto).name.lower() if gesto in Gesto._value2member_map_ else f"dedos {gesto:04b}"
    cv2.putText(quadro, nome, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 140, 255), 2)


def janela_aberta(cv2) -> bool:
    """Se a pessoa nao fechou a janela pelo botao do sistema.

    No Windows a propriedade cai para 0; no macOS a janela fechada some, e a
    consulta levanta erro em vez de responder.
    """
    try:
        return cv2.getWindowProperty(TITULO, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


def executar(camera: int = 0, destro: bool = True) -> int:
    """Liga a camera e controla o mouse ate a pessoa fechar a janela."""
    cv2, mediapipe, pyautogui, BaseOptions, vision = importar_dependencias()

    # Sem isto o PyAutoGUI dorme 0,1 s depois de cada chamada: o cursor anda
    # a 10 quadros por segundo, e e daqui que vem a fama de "mouse travado".
    pyautogui.PAUSE = 0
    sistema = sistema_atual(pyautogui)
    faltando = sistema.permissoes_faltando()
    if faltando:
        raise GestosIndisponiveis("\n".join(faltando))

    captura = cv2.VideoCapture(camera)
    if not captura.isOpened():
        raise GestosIndisponiveis(
            f"nao consegui abrir a camera {camera}. Confira se outro programa a esta usando"
            + (" e se o aplicativo tem acesso em Ajustes > Privacidade > Camera" if sys.platform == "darwin" else "")
        )

    detector = Detector(mediapipe, BaseOptions, vision, obter_modelo())
    controlador = Controlador(pyautogui, sistema)
    principal, secundaria = Mao(), Mao(secundaria=True)
    falhas = 0
    print(f"gestos ligados ({sistema.nome}). Mao aberta descansa; Esc fecha. Mouse no canto da tela e o freio.")

    try:
        while True:
            lido, quadro = captura.read()
            if not lido:
                falhas += 1
                if falhas > FALHAS_TOLERADAS:
                    raise GestosIndisponiveis("a camera parou de mandar imagem")
                continue
            falhas = 0

            # Espelhado, como num espelho: mao para a direita, cursor para a direita.
            quadro = cv2.flip(quadro, 1)
            maos = detector.detectar(cv2.cvtColor(quadro, cv2.COLOR_BGR2RGB))

            gesto = Gesto.PALMA
            if maos:
                pontos_principal, pontos_secundaria = separar_maos(maos, destro)
                gesto_secundaria = secundaria.atualizar(pontos_secundaria)
                gesto_principal = principal.atualizar(pontos_principal)
                if gesto_secundaria == Gesto.PINCA_SECUNDARIA:
                    gesto = gesto_secundaria
                    controlador.aplicar(gesto, secundaria.pontos)
                else:
                    # Sem a mao principal, atualizar() da palma, que solta o arrasto.
                    gesto = gesto_principal
                    controlador.aplicar(gesto, principal.pontos)
            else:
                controlador.mao_sumiu()

            desenhar(cv2, quadro, maos, detector.conexoes, gesto)
            cv2.imshow(TITULO, quadro)
            if cv2.waitKey(5) & 0xFF in TECLAS_SAIR:
                break
            if not janela_aberta(cv2):
                break
    except pyautogui.FailSafeException:
        print("freio acionado: o mouse foi levado ao canto da tela.")
    finally:
        controlador.mao_sumiu()
        detector.fechar()
        captura.release()
        cv2.destroyAllWindows()
    return 0
