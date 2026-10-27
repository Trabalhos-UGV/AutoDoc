"""O que o controle por gestos faz de diferente em cada sistema.

Mover e clicar o PyAutoGUI resolve igual nos tres. O resto nao:

- **Volume.** No Windows, pela API de audio do sistema (pycaw). No macOS, pelo
  AppleScript, que ja vem instalado. No Linux, pelo `pactl` do PulseAudio /
  PipeWire.
- **Brilho.** No Windows e no Linux, pelo `screen_brightness_control`. No macOS
  ele nao funciona; la o caminho e o DisplayServices, framework privado da
  Apple que o proprio sistema usa. Vale para a tela embutida; monitor externo
  nao responde, e isso vira `RecursoIndisponivel`, nao queda.
- **Rolagem.** A unidade muda: no Windows uma volta da roda vale 120, no macOS
  a conta e em linhas. E o PyAutoGUI no Windows nao rola na horizontal — o
  `hscroll` dele rola na vertical —, entao la vai direto pela API do Windows.
- **Clique duplo.** No Windows e no Linux o sistema decide pelo intervalo entre
  dois cliques. No macOS nao: cada evento diz se e o primeiro ou o segundo
  clique, e o PyAutoGUI manda todos como primeiro — o `doubleClick()` dele
  nunca abriu uma pasta no Finder.

Cada ajuste recebe um delta entre -1 e 1 sobre o valor atual, ja que o gesto e
"mais um pouco", e nao "va para 70%".
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path


class RecursoIndisponivel(RuntimeError):
    """Este sistema (ou esta tela) nao permite o ajuste pedido."""


def limitar(valor: float) -> float:
    return min(1.0, max(0.0, valor))


class Sistema:
    """O comportamento comum; cada sistema troca o que precisa."""

    nome = "desconhecido"
    # Quanto cada passo do gesto de rolagem rola, na unidade do sistema. O passo
    # se repete varias vezes por segundo enquanto o punho esta fechado.
    passo_rolagem = 1

    def __init__(self, mouse) -> None:
        self.mouse = mouse

    def rolar_vertical(self, sentido: int) -> None:
        """`sentido` 1 sobe, -1 desce."""
        self.mouse.scroll(sentido * self.passo_rolagem)

    def rolar_horizontal(self, sentido: int) -> None:
        """`sentido` 1 vai para a direita, -1 para a esquerda."""
        self.mouse.hscroll(sentido * self.passo_rolagem)

    def clique_duplo(self, x: int, y: int) -> None:
        """O segundo clique de um duplo; o primeiro ja foi dado."""
        self.mouse.click(x, y)

    def ajustar_volume(self, delta: float) -> None:
        raise RecursoIndisponivel(f"volume nao suportado em {self.nome}")

    def ajustar_brilho(self, delta: float) -> None:
        raise RecursoIndisponivel(f"brilho nao suportado em {self.nome}")

    def permissoes_faltando(self) -> list[str]:
        """O que a pessoa precisa liberar antes de os gestos funcionarem."""
        return []

    def preparar_camera(self) -> None:
        """Antes de abrir a camera: garante que o sistema deixa.

        Levanta `RecursoIndisponivel` dizendo o que fazer, em vez de deixar o
        OpenCV falhar com "camera failed to properly initialize".
        """

    def dica_camera(self) -> str:
        """Onde procurar quando a camera nao abre, para completar a mensagem."""
        return ""


class Windows(Sistema):
    nome = "Windows"
    passo_rolagem = 120  # WHEEL_DELTA: um "dente" da roda do mouse

    def rolar_horizontal(self, sentido: int) -> None:
        mouseeventf_hwheel = 0x01000
        ctypes.windll.user32.mouse_event(mouseeventf_hwheel, 0, 0, sentido * self.passo_rolagem, 0)

    def ajustar_volume(self, delta: float) -> None:
        try:
            from pycaw.pycaw import AudioUtilities
        except ImportError as erro:
            raise RecursoIndisponivel("instale o pycaw para controlar o volume") from erro
        volume = AudioUtilities.GetSpeakers().EndpointVolume
        atual = volume.GetMasterVolumeLevelScalar()
        volume.SetMasterVolumeLevelScalar(limitar(atual + delta), None)

    def ajustar_brilho(self, delta: float) -> None:
        _brilho_por_sbc(delta)

    # Programa de mesa nao recebe pergunta de permissao no Windows: vale o que
    # estiver nas Configuracoes, e o OpenCV so falha. Ler o registro antes diz
    # se o bloqueio e de la, e leva a pessoa direto para a chave certa.
    CHAVE_CAMERA = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    AJUSTES_CAMERA = "ms-settings:privacy-webcam"

    def preparar_camera(self) -> None:
        import winreg

        for subchave in ("", "\\NonPackaged"):  # a geral e a dos aplicativos da area de trabalho
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.CHAVE_CAMERA + subchave) as chave:
                    valor, _ = winreg.QueryValueEx(chave, "Value")
            except OSError:
                continue
            if valor == "Deny":
                subprocess.run(["explorer.exe", self.AJUSTES_CAMERA], check=False)
                raise RecursoIndisponivel(
                    "o Windows está bloqueando a câmera. Em Configurações > Privacidade e segurança > Câmera, "
                    "ligue o acesso à câmera e \"Permitir que aplicativos da área de trabalho acessem a câmera\"."
                )

    def dica_camera(self) -> str:
        return " e se as Configurações > Privacidade e segurança > Câmera deixam aplicativos da área de trabalho usá-la"


class MacOS(Sistema):
    nome = "macOS"
    passo_rolagem = 2  # linhas

    DISPLAY_SERVICES = "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
    CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    APPLICATION_SERVICES = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    AJUSTES_ACESSIBILIDADE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    AJUSTES_CAMERA = "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"

    # Quanto esperar a pessoa responder a pergunta da camera.
    ESPERA_PERMISSAO = 120

    def preparar_camera(self) -> None:
        """Pede a camera ao macOS e espera a resposta.

        O OpenCV tambem pede, mas desiste na hora, sem esperar: a pergunta
        aparecia, a pessoa permitia, e o jogo ja tinha fechado — era preciso
        abrir de novo. Aqui a pergunta e feita antes, e so se segue depois da
        resposta. Sem o PyObjC do AVFoundation, fica com o jeito do OpenCV.
        """
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
        except ImportError:
            return
        autorizada, nao_perguntada = 3, 0
        situacao = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
        if situacao == nao_perguntada:
            resposta = threading.Event()
            AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeVideo, lambda _concedida: resposta.set())
            resposta.wait(self.ESPERA_PERMISSAO)
            situacao = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
        if situacao != autorizada:
            subprocess.run(["open", self.AJUSTES_CAMERA], check=False)
            raise RecursoIndisponivel(
                "o macOS não deixou o AutoDoc usar a câmera. Em Ajustes do Sistema > Privacidade e Segurança > "
                "Câmera, ative o AutoDoc e abra o jogo de novo."
            )

    def dica_camera(self) -> str:
        return " e se o AutoDoc tem acesso em Ajustes do Sistema > Privacidade e Segurança > Câmera"

    def clique_duplo(self, x: int, y: int) -> None:
        import Quartz  # vem com o PyAutoGUI no macOS

        for tipo in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            evento = Quartz.CGEventCreateMouseEvent(None, tipo, (x, y), Quartz.kCGMouseButtonLeft)
            Quartz.CGEventSetIntegerValueField(evento, Quartz.kCGMouseEventClickState, 2)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evento)

    def ajustar_volume(self, delta: float) -> None:
        lido = _osascript("output volume of (get volume settings)")
        # Saida sem controle de volume (HDMI, alguns DACs) responde "missing value".
        if not lido.isdigit():
            raise RecursoIndisponivel("a saida de audio atual nao tem controle de volume")
        novo = round(limitar(int(lido) / 100 + delta) * 100)
        _osascript(f"set volume output volume {novo}")

    def ajustar_brilho(self, delta: float) -> None:
        try:
            servicos = ctypes.CDLL(self.DISPLAY_SERVICES)
            graficos = ctypes.CDLL(self.CORE_GRAPHICS)
        except OSError as erro:
            raise RecursoIndisponivel("DisplayServices ausente nesta versao do macOS") from erro

        graficos.CGMainDisplayID.restype = ctypes.c_uint32
        servicos.DisplayServicesGetBrightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
        servicos.DisplayServicesSetBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]

        tela = graficos.CGMainDisplayID()
        atual = ctypes.c_float()
        if servicos.DisplayServicesGetBrightness(tela, ctypes.byref(atual)) != 0:
            raise RecursoIndisponivel("a tela principal nao aceita ajuste de brilho")
        servicos.DisplayServicesSetBrightness(tela, limitar(atual.value + delta))

    def permissoes_faltando(self) -> list[str]:
        """Sem Acessibilidade, o macOS descarta os cliques em silencio.

        A permissao e do aplicativo que abriu o Python — Terminal, iTerm,
        VS Code —, e nao do AutoDoc. A camera pede a dela sozinha, na primeira
        vez que e aberta.
        """
        try:
            servicos = ctypes.CDLL(self.APPLICATION_SERVICES)
        except OSError:
            return []
        if servicos.AXIsProcessTrusted():
            return []
        subprocess.run(["open", self.AJUSTES_ACESSIBILIDADE], check=False)
        return [
            "o macOS ainda nao deixa este programa controlar o mouse. Em Ajustes do "
            "Sistema > Privacidade e Seguranca > Acessibilidade, ative o aplicativo "
            "de onde o AutoDoc foi aberto (Terminal, VS Code...) e abra-o de novo."
        ]


class Linux(Sistema):
    nome = "Linux"
    passo_rolagem = 1  # cada unidade e um clique da roda

    def ajustar_volume(self, delta: float) -> None:
        if not shutil.which("pactl"):
            raise RecursoIndisponivel("pactl nao encontrado (PulseAudio/PipeWire)")
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{round(delta * 100):+d}%"],
            check=True,
            capture_output=True,
        )

    def ajustar_brilho(self, delta: float) -> None:
        _brilho_por_sbc(delta)

    DISPOSITIVOS = Path("/dev")

    def preparar_camera(self) -> None:
        """No Linux a camera e um arquivo, /dev/video0; o que falta costuma ser permissao nele."""
        cameras = sorted(self.DISPOSITIVOS.glob("video*"))
        if not cameras:
            raise RecursoIndisponivel("nenhuma câmera encontrada (não há /dev/video*). Confira se a webcam está conectada.")
        if not any(os.access(camera, os.R_OK | os.W_OK) for camera in cameras):
            raise RecursoIndisponivel(
                f"seu usuário não tem permissão para usar {cameras[0]}. Rode: sudo usermod -aG video $USER "
                "e entre de novo na sessão."
            )

    def dica_camera(self) -> str:
        return " e se seu usuário está no grupo video"


def _osascript(script: str) -> str:
    resultado = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
    return resultado.stdout.strip()


def _brilho_por_sbc(delta: float) -> None:
    try:
        import screen_brightness_control as sbc
    except ImportError as erro:
        raise RecursoIndisponivel("instale o screen-brightness-control para controlar o brilho") from erro
    try:
        # Versoes atuais devolvem uma lista, uma entrada por tela.
        atual = sbc.get_brightness(display=0)[0]
        sbc.set_brightness(round(limitar(atual / 100 + delta) * 100), display=0)
    except sbc.exceptions.ScreenBrightnessError as erro:
        raise RecursoIndisponivel(str(erro)) from erro


def sistema_atual(mouse, plataforma: str | None = None) -> Sistema:
    plataforma = plataforma or sys.platform
    if plataforma == "win32":
        return Windows(mouse)
    if plataforma == "darwin":
        return MacOS(mouse)
    return Linux(mouse)
