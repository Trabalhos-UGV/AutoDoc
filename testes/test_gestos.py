"""Controle do mouse por gestos.

Nada aqui abre camera, mexe no mouse ou muda volume de verdade: as maos sao
montadas ponto a ponto, o mouse e um `mock` e o sistema e trocado por um falso.
Por isso a suite roda sem OpenCV, MediaPipe e PyAutoGUI instalados — que e
justamente o caso de quem so usa o organizador de documentos.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import main
from autodoc.gestos import GestosIndisponiveis, camera, sistema
from autodoc.gestos.controle import Controlador
from autodoc.gestos.reconhecimento import (
    QUADROS_PARA_CONFIRMAR,
    Gesto,
    Mao,
    classificar,
    dedos_abertos,
    separar_maos,
)
from autodoc.gestos.sistema import RecursoIndisponivel

# Indice da ponta, da junta e x da base de cada dedo (indicador ao minimo).
PONTAS = {"indicador": (8, 5, 0.44), "medio": (12, 9, 0.48), "anelar": (16, 13, 0.52), "minimo": (20, 17, 0.56)}


def montar_mao(abertos=(), pontas_x=None, z=None, polegar=(0.30, 0.70), x=0.0, y=0.0):
    """Uma mao de pe, pulso embaixo; dedo aberto aponta para cima.

    `x` e `y` deslocam a mao inteira, para simular o movimento.
    """
    pontos = [SimpleNamespace(x=0.5, y=0.9, z=0.0) for _ in range(21)]
    for nome, (ponta, junta, base_x) in PONTAS.items():
        pontos[junta] = SimpleNamespace(x=base_x, y=0.6, z=0.0)
        ponta_x = (pontas_x or {}).get(nome, base_x)
        ponta_y = 0.4 if nome in abertos else 0.65
        pontos[ponta] = SimpleNamespace(x=ponta_x, y=ponta_y, z=(z or {}).get(nome, 0.0))
    pontos[4] = SimpleNamespace(x=polegar[0], y=polegar[1], z=0.0)
    for ponto in pontos:
        ponto.x += x
        ponto.y += y
    return pontos


def mao_pinca(**deslocamento):
    # Indicador dobrado, os outros tres abertos, polegar encostado na ponta dele.
    return montar_mao(("medio", "anelar", "minimo"), polegar=(0.44, 0.65), **deslocamento)


V = dict(abertos=("indicador", "medio"), pontas_x={"indicador": 0.38, "medio": 0.54})
JUNTOS = dict(abertos=("indicador", "medio"), pontas_x={"indicador": 0.455, "medio": 0.465})


class TestDedos(unittest.TestCase):
    def test_um_bit_por_dedo(self):
        self.assertEqual(dedos_abertos(montar_mao()), 0)
        self.assertEqual(dedos_abertos(montar_mao(("indicador",))), 8)
        self.assertEqual(dedos_abertos(montar_mao(("medio",))), 4)
        self.assertEqual(dedos_abertos(montar_mao(("anelar", "minimo"))), 3)
        self.assertEqual(dedos_abertos(montar_mao(tuple(PONTAS))), 15)

    def test_junta_em_cima_do_pulso_nao_divide_por_zero(self):
        # Era um NameError no original: o `except` usava uma variavel inexistente.
        pontos = montar_mao(("indicador",))
        pontos[5] = SimpleNamespace(x=0.5, y=0.9, z=0.0)
        dedos_abertos(pontos)


class TestClassificar(unittest.TestCase):
    def test_gestos_simples(self):
        self.assertEqual(classificar(montar_mao()), Gesto.PUNHO)
        self.assertEqual(classificar(montar_mao(("indicador",))), Gesto.INDICADOR)
        self.assertEqual(classificar(montar_mao(tuple(PONTAS))), Gesto.QUATRO_DEDOS)

    def test_v(self):
        self.assertEqual(classificar(montar_mao(**V)), Gesto.V)

    def test_dois_dedos_juntos_na_mesma_profundidade(self):
        self.assertEqual(classificar(montar_mao(**JUNTOS)), Gesto.DOIS_JUNTOS)

    def test_dois_dedos_juntos_em_profundidades_diferentes(self):
        self.assertEqual(classificar(montar_mao(**JUNTOS, z={"medio": 0.3})), Gesto.MEDIO)

    def test_pinca_depende_da_mao(self):
        self.assertEqual(classificar(mao_pinca()), Gesto.PINCA_PRINCIPAL)
        self.assertEqual(classificar(mao_pinca(), secundaria=True), Gesto.PINCA_SECUNDARIA)

    def test_polegar_longe_nao_e_pinca(self):
        self.assertEqual(classificar(montar_mao(("medio", "anelar", "minimo"))), 7)


class TestMao(unittest.TestCase):
    def test_gesto_so_vale_depois_de_repetir(self):
        mao = Mao()
        for _ in range(QUADROS_PARA_CONFIRMAR - 1):
            self.assertEqual(mao.atualizar(montar_mao()), Gesto.PALMA)
        self.assertEqual(mao.atualizar(montar_mao()), Gesto.PUNHO)

    def test_oscilacao_nao_troca_o_gesto(self):
        mao = Mao()
        for _ in range(QUADROS_PARA_CONFIRMAR):
            mao.atualizar(montar_mao())
        self.assertEqual(mao.atualizar(montar_mao(("indicador",))), Gesto.PUNHO)

    def test_sem_mao_e_palma(self):
        self.assertEqual(Mao().atualizar(None), Gesto.PALMA)

    def test_separar_maos(self):
        direita, esquerda = object(), object()
        maos = [("Left", esquerda), ("Right", direita)]
        self.assertEqual(separar_maos(maos), (direita, esquerda))
        self.assertEqual(separar_maos(maos, destro=False), (esquerda, direita))
        self.assertEqual(separar_maos([("Left", esquerda)]), (None, esquerda))


class SistemaFalso(sistema.Sistema):
    def __init__(self, mouse):
        super().__init__(mouse)
        self.ajustes = []

    def ajustar_volume(self, delta):
        self.ajustes.append(("volume", delta))

    def ajustar_brilho(self, delta):
        raise RecursoIndisponivel("sem brilho aqui")


def novo_mouse():
    mouse = mock.Mock()
    mouse.size.return_value = (1000, 800)
    mouse.position.return_value = (500, 400)
    return mouse


class TestControlador(unittest.TestCase):
    def setUp(self):
        self.mouse = novo_mouse()
        self.sistema = SistemaFalso(self.mouse)
        self.controle = Controlador(self.mouse, self.sistema)

    def test_v_move_o_cursor_amortecido(self):
        self.controle.aplicar(Gesto.V, montar_mao(**V))
        self.mouse.moveTo.assert_called_with(500, 400)  # primeiro quadro: sem deslocamento
        self.controle.aplicar(Gesto.V, montar_mao(**V, x=0.01))  # 10 px: amortece
        self.mouse.moveTo.assert_called_with(507, 400)
        self.controle.aplicar(Gesto.V, montar_mao(**V, x=0.11))  # 100 px: amplia
        self.mouse.moveTo.assert_called_with(710, 400)

    def test_tremida_e_ignorada(self):
        self.controle.aplicar(Gesto.V, montar_mao(**V))
        self.controle.aplicar(Gesto.V, montar_mao(**V, x=0.003))
        self.mouse.moveTo.assert_called_with(500, 400)

    def test_cursor_nunca_chega_ao_canto(self):
        self.mouse.position.return_value = (999, 0)
        self.controle.aplicar(Gesto.V, montar_mao(**V))
        self.controle.aplicar(Gesto.V, montar_mao(**V, x=0.2, y=-0.2))
        self.mouse.moveTo.assert_called_with(998, 1)

    def test_clique_so_com_v_antes(self):
        self.controle.aplicar(Gesto.MEDIO, montar_mao(("medio",)))
        self.mouse.click.assert_not_called()

        self.controle.aplicar(Gesto.V, montar_mao(**V))
        self.controle.aplicar(Gesto.MEDIO, montar_mao(("medio",)))
        self.controle.aplicar(Gesto.MEDIO, montar_mao(("medio",)))
        self.mouse.click.assert_called_once_with()

    def test_clique_direito_e_duplo(self):
        self.controle.aplicar(Gesto.V, montar_mao(**V))
        self.controle.aplicar(Gesto.INDICADOR, montar_mao(("indicador",)))
        self.mouse.click.assert_called_once_with(button="right")
        self.controle.aplicar(Gesto.V, montar_mao(**V))
        self.controle.aplicar(Gesto.DOIS_JUNTOS, montar_mao(**JUNTOS))
        self.mouse.doubleClick.assert_called_once_with()

    def test_punho_arrasta_e_solta(self):
        self.controle.aplicar(Gesto.PUNHO, montar_mao())
        self.controle.aplicar(Gesto.PUNHO, montar_mao())
        self.mouse.mouseDown.assert_called_once_with(button="left")
        self.controle.aplicar(Gesto.PALMA, None)
        self.mouse.mouseUp.assert_called_once_with(button="left")

    def test_mao_sumida_solta_o_arrasto(self):
        self.controle.aplicar(Gesto.PUNHO, montar_mao())
        self.controle.mao_sumiu()
        self.mouse.mouseUp.assert_called_once_with(button="left")

    def segurar_pinca(self, gesto, quadros=12, **deslocamento):
        self.controle.aplicar(gesto, mao_pinca())
        for _ in range(quadros):
            self.controle.aplicar(gesto, mao_pinca(**deslocamento))

    def test_pinca_para_cima_sobe_o_volume_e_repete(self):
        self.segurar_pinca(Gesto.PINCA_PRINCIPAL, y=-0.05)
        self.assertEqual(self.sistema.ajustes, [("volume", 0.01), ("volume", 0.01)])

    def test_pinca_parada_nao_faz_nada(self):
        self.segurar_pinca(Gesto.PINCA_PRINCIPAL)
        self.assertEqual(self.sistema.ajustes, [])

    def test_pinca_que_volta_recomeca_a_contar(self):
        for deslocamento in (-0.05, -0.15, -0.05):
            self.controle.aplicar(Gesto.PINCA_PRINCIPAL, mao_pinca(y=deslocamento))
        self.assertEqual(self.sistema.ajustes, [])

    def test_brilho_indisponivel_avisa_uma_vez(self):
        with self.assertLogs("autodoc.gestos.controle", "WARNING") as registro:
            self.segurar_pinca(Gesto.PINCA_PRINCIPAL, quadros=20, x=0.05)
        self.assertEqual(registro.output, ["WARNING:autodoc.gestos.controle:sem brilho aqui"])

    def test_pinca_secundaria_rola(self):
        self.segurar_pinca(Gesto.PINCA_SECUNDARIA, quadros=7, y=0.05)
        self.mouse.scroll.assert_called_once_with(-1)
        self.controle.aplicar(Gesto.PALMA, None)
        self.segurar_pinca(Gesto.PINCA_SECUNDARIA, quadros=7, x=0.05)
        self.mouse.hscroll.assert_called_once_with(1)


def concluido(saida=""):
    return subprocess.CompletedProcess([], 0, stdout=saida)


class TestSistema(unittest.TestCase):
    def test_escolha_por_plataforma(self):
        self.assertIsInstance(sistema.sistema_atual(None, "win32"), sistema.Windows)
        self.assertIsInstance(sistema.sistema_atual(None, "darwin"), sistema.MacOS)
        self.assertIsInstance(sistema.sistema_atual(None, "linux"), sistema.Linux)
        self.assertIsInstance(sistema.sistema_atual(None), sistema.Sistema)

    def test_padrao_nao_ajusta_nada(self):
        base = sistema.Sistema(None)
        self.assertEqual(base.permissoes_faltando(), [])
        with self.assertRaises(RecursoIndisponivel):
            base.ajustar_volume(0.1)
        with self.assertRaises(RecursoIndisponivel):
            base.ajustar_brilho(0.1)

    def test_rolagem_na_unidade_do_sistema(self):
        mouse = mock.Mock()
        sistema.MacOS(mouse).rolar_vertical(-1)
        mouse.scroll.assert_called_once_with(-8)
        sistema.Linux(mouse).rolar_horizontal(1)
        mouse.hscroll.assert_called_once_with(1)

    def test_rolagem_horizontal_no_windows_vai_pela_api(self):
        user32 = mock.Mock()
        with mock.patch.object(sistema.ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            sistema.Windows(None).rolar_horizontal(-1)
        user32.mouse_event.assert_called_once_with(0x01000, 0, 0, -120, 0)

    def test_volume_no_windows(self):
        volume = mock.Mock()
        volume.GetMasterVolumeLevelScalar.return_value = 0.95
        pycaw = SimpleNamespace(AudioUtilities=SimpleNamespace(GetSpeakers=lambda: SimpleNamespace(EndpointVolume=volume)))
        with mock.patch.dict(sys.modules, {"pycaw": SimpleNamespace(pycaw=pycaw), "pycaw.pycaw": pycaw}):
            sistema.Windows(None).ajustar_volume(0.1)
        volume.SetMasterVolumeLevelScalar.assert_called_once_with(1.0, None)

    def test_volume_no_windows_sem_pycaw(self):
        with mock.patch.dict(sys.modules, {"pycaw": None, "pycaw.pycaw": None}):
            with self.assertRaises(RecursoIndisponivel):
                sistema.Windows(None).ajustar_volume(0.1)

    def falso_sbc(self, atual):
        erro = type("ScreenBrightnessError", (Exception,), {})
        sbc = mock.Mock(exceptions=SimpleNamespace(ScreenBrightnessError=erro))
        sbc.get_brightness.return_value = [atual]
        return sbc, erro

    def test_brilho_por_sbc(self):
        sbc, _ = self.falso_sbc(50)
        with mock.patch.dict(sys.modules, {"screen_brightness_control": sbc}):
            sistema.Windows(None).ajustar_brilho(-0.2)
            sistema.Linux(None).ajustar_brilho(-0.9)
        self.assertEqual(sbc.set_brightness.call_args_list, [mock.call(30, display=0), mock.call(0, display=0)])

    def test_brilho_por_sbc_que_falha(self):
        sbc, erro = self.falso_sbc(50)
        sbc.set_brightness.side_effect = erro("monitor sem DDC/CI")
        with mock.patch.dict(sys.modules, {"screen_brightness_control": sbc}):
            with self.assertRaisesRegex(RecursoIndisponivel, "DDC"):
                sistema.Windows(None).ajustar_brilho(0.1)

    def test_brilho_sem_sbc(self):
        with mock.patch.dict(sys.modules, {"screen_brightness_control": None}):
            with self.assertRaises(RecursoIndisponivel):
                sistema.Linux(None).ajustar_brilho(0.1)

    def test_volume_no_macos(self):
        with mock.patch.object(sistema.subprocess, "run", side_effect=[concluido("38\n"), concluido()]) as rodar:
            sistema.MacOS(None).ajustar_volume(0.1)
        self.assertEqual(rodar.call_args_list[1].args[0], ["osascript", "-e", "set volume output volume 48"])

    def test_volume_no_macos_em_saida_sem_volume(self):
        with mock.patch.object(sistema.subprocess, "run", return_value=concluido("missing value")):
            with self.assertRaises(RecursoIndisponivel):
                sistema.MacOS(None).ajustar_volume(0.1)

    def bibliotecas_macos(self, leitura=0, acessivel=True):
        servicos = mock.Mock()
        servicos.DisplayServicesGetBrightness.return_value = leitura
        servicos.AXIsProcessTrusted.return_value = acessivel
        graficos = mock.Mock()
        graficos.CGMainDisplayID.return_value = 1
        return lambda caminho: graficos if "CoreGraphics" in caminho else servicos

    def test_brilho_no_macos(self):
        with mock.patch.object(sistema.ctypes, "CDLL", self.bibliotecas_macos()) as carregar:
            sistema.MacOS(None).ajustar_brilho(0.3)
        servicos = carregar("DisplayServices")
        self.assertEqual(servicos.DisplayServicesSetBrightness.call_args.args, (1, 0.3))

    def test_brilho_no_macos_em_tela_externa(self):
        with mock.patch.object(sistema.ctypes, "CDLL", self.bibliotecas_macos(leitura=1)):
            with self.assertRaises(RecursoIndisponivel):
                sistema.MacOS(None).ajustar_brilho(0.3)

    def test_brilho_no_macos_sem_framework(self):
        with mock.patch.object(sistema.ctypes, "CDLL", side_effect=OSError):
            with self.assertRaises(RecursoIndisponivel):
                sistema.MacOS(None).ajustar_brilho(0.3)
            self.assertEqual(sistema.MacOS(None).permissoes_faltando(), [])

    def test_acessibilidade_no_macos(self):
        with mock.patch.object(sistema.ctypes, "CDLL", self.bibliotecas_macos()):
            self.assertEqual(sistema.MacOS(None).permissoes_faltando(), [])

    def test_sem_acessibilidade_abre_os_ajustes(self):
        with (
            mock.patch.object(sistema.ctypes, "CDLL", self.bibliotecas_macos(acessivel=False)),
            mock.patch.object(sistema.subprocess, "run") as rodar,
        ):
            faltando = sistema.MacOS(None).permissoes_faltando()
        self.assertIn("Acessibilidade", faltando[0])
        self.assertEqual(rodar.call_args.args[0][0], "open")

    def test_volume_no_linux(self):
        with (
            mock.patch.object(sistema.shutil, "which", return_value="/usr/bin/pactl"),
            mock.patch.object(sistema.subprocess, "run") as rodar,
        ):
            sistema.Linux(None).ajustar_volume(-0.05)
        self.assertEqual(rodar.call_args.args[0][-1], "-5%")

    def test_volume_no_linux_sem_pactl(self):
        with mock.patch.object(sistema.shutil, "which", return_value=None):
            with self.assertRaises(RecursoIndisponivel):
                sistema.Linux(None).ajustar_volume(0.1)


class TestModelo(unittest.TestCase):
    def test_pasta_de_cache_por_sistema(self):
        with mock.patch.dict(camera.os.environ, {"LOCALAPPDATA": "C:/local", "XDG_CACHE_HOME": "/cache"}):
            self.assertEqual(camera.pasta_cache("win32"), Path("C:/local/AutoDoc"))
            self.assertEqual(camera.pasta_cache("linux"), Path("/cache/autodoc"))
        self.assertEqual(camera.pasta_cache("darwin"), Path.home() / "Library" / "Caches" / "AutoDoc")
        self.assertIsInstance(camera.pasta_cache(), Path)

    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.destino = self.pasta / "hand_landmarker.task"

    def baixar(self, *, curl=True, **efeito):
        def escrever(argumentos, check):
            Path(argumentos[3]).write_bytes(b"modelo")

        def escrever_urllib(url, caminho):
            Path(caminho).write_bytes(b"modelo")

        with (
            mock.patch.object(camera.shutil, "which", return_value="/usr/bin/curl" if curl else None),
            mock.patch.object(camera.subprocess, "run", **(efeito or {"side_effect": escrever})) as rodar,
            mock.patch.object(camera.urllib.request, "urlretrieve", side_effect=escrever_urllib),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return camera.obter_modelo(self.destino), rodar

    def test_baixa_uma_vez_so(self):
        _, rodar = self.baixar()
        self.assertEqual(self.destino.read_bytes(), b"modelo")
        _, rodar = self.baixar()
        rodar.assert_not_called()

    def test_sem_curl_usa_urllib(self):
        self.baixar(curl=False)
        self.assertTrue(self.destino.exists())

    def test_download_que_falha_nao_deixa_resto(self):
        with self.assertRaises(GestosIndisponiveis):
            self.baixar(side_effect=subprocess.CalledProcessError(22, "curl"))
        self.assertEqual(list(self.pasta.iterdir()), [])

    def test_caminho_padrao_fica_no_cache(self):
        with mock.patch.object(camera, "pasta_cache", return_value=self.pasta):
            self.destino.write_bytes(b"ja estava")
            self.assertEqual(camera.obter_modelo(), self.destino)


class TestDependencias(unittest.TestCase):
    def test_falta_de_dependencia_diz_o_que_instalar(self):
        with mock.patch.dict(sys.modules, {"cv2": None}):
            with self.assertRaisesRegex(GestosIndisponiveis, "requirements-gestos"):
                camera.importar_dependencias()

    def test_com_dependencias(self):
        falsos = {nome: mock.MagicMock() for nome in ("cv2", "mediapipe", "pyautogui", "mediapipe.tasks", "mediapipe.tasks.python")}
        with mock.patch.dict(sys.modules, falsos):
            self.assertEqual(len(camera.importar_dependencias()), 5)


class FalhaSegura(Exception):
    pass


class CameraFalsa:
    """Uma webcam que entrega os quadros dados e depois uma lista de teclas."""

    def __init__(self, quadros, aberta=True):
        self.quadros = list(quadros)
        self.aberta = aberta
        self.solta = False

    def isOpened(self):
        return self.aberta

    def read(self):
        return self.quadros.pop(0)

    def release(self):
        self.solta = True


class TestExecutar(unittest.TestCase):
    """O laco inteiro, com camera, MediaPipe e mouse falsos."""

    def montar(self, quadros, maos_por_quadro, teclas=None, aberta=True, permissoes=(), janela=True):
        quadro = mock.MagicMock()
        quadro.shape = (100, 200, 3)
        self.webcam = CameraFalsa([(lido, quadro) for lido in quadros], aberta)

        cv2 = mock.MagicMock()
        cv2.error = type("error", (Exception,), {})
        cv2.VideoCapture.return_value = self.webcam
        cv2.flip.side_effect = lambda q, _: q
        teclas = list(teclas or [-1] * (len(quadros) - 1) + [27])
        cv2.waitKey.side_effect = lambda _: teclas.pop(0)
        if janela is not True:
            cv2.getWindowProperty.side_effect = janela
        else:
            cv2.getWindowProperty.return_value = 1.0
        self.cv2 = cv2

        resultados = list(maos_por_quadro)

        class Rotulo:
            def __init__(self, nome):
                self.category_name = nome

        def detectar(imagem, ms):
            maos = resultados.pop(0)
            return SimpleNamespace(
                handedness=[[Rotulo(rotulo)] for rotulo, _ in maos],
                hand_landmarks=[pontos for _, pontos in maos],
            )

        detector = mock.Mock(detect_for_video=mock.Mock(side_effect=detectar))
        vision = mock.MagicMock()
        vision.HandLandmarker.create_from_options.return_value = detector
        vision.HandLandmarksConnections.HAND_CONNECTIONS = [SimpleNamespace(start=0, end=1)]
        self.detector = detector

        self.mouse = novo_mouse()
        self.mouse.FailSafeException = FalhaSegura
        self.sistema = SistemaFalso(self.mouse)
        self.sistema.permissoes_faltando = lambda: list(permissoes)

        pilha = contextlib.ExitStack()
        self.addCleanup(pilha.close)
        pilha.enter_context(mock.patch.object(camera, "importar_dependencias", return_value=(cv2, mock.MagicMock(), self.mouse, mock.MagicMock(), vision)))
        pilha.enter_context(mock.patch.object(camera, "sistema_atual", return_value=self.sistema))
        pilha.enter_context(mock.patch.object(camera, "obter_modelo", return_value=Path("modelo.task")))
        pilha.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def test_v_move_o_cursor_ate_fechar_com_esc(self):
        quadros = QUADROS_PARA_CONFIRMAR + 2
        self.montar([True] * quadros, [[("Right", montar_mao(**V))]] * quadros)
        self.assertEqual(camera.executar(), 0)
        self.mouse.moveTo.assert_called()
        self.assertEqual(self.mouse.PAUSE, 0)
        self.assertTrue(self.webcam.solta)
        self.detector.close.assert_called_once_with()

    def test_pinca_da_mao_secundaria_tem_prioridade(self):
        quadros = QUADROS_PARA_CONFIRMAR + 8
        # A pinca so conta depois de confirmada; dali em diante a mao desce.
        descida = [0.0] * QUADROS_PARA_CONFIRMAR + [0.05] * 8
        maos = [[("Right", montar_mao(**V)), ("Left", mao_pinca(y=y))] for y in descida]
        self.montar([True] * quadros, maos)
        camera.executar()
        self.mouse.scroll.assert_called()
        self.mouse.moveTo.assert_not_called()

    def test_so_a_mao_secundaria_solta_o_arrasto(self):
        quadros = QUADROS_PARA_CONFIRMAR * 2
        maos = [[("Right", montar_mao())]] * QUADROS_PARA_CONFIRMAR + [[("Left", montar_mao())]] * QUADROS_PARA_CONFIRMAR
        self.montar([True] * quadros, maos)
        camera.executar()
        self.mouse.mouseDown.assert_called_once()
        self.mouse.mouseUp.assert_called_once()

    def test_canhoto(self):
        quadros = QUADROS_PARA_CONFIRMAR + 1
        self.montar([True] * quadros, [[("Left", montar_mao(**V))]] * quadros)
        camera.executar(destro=False)
        self.mouse.moveTo.assert_called()

    def test_quadro_sem_mao(self):
        self.montar([True, False, True], [[], []], teclas=[-1, 27])
        camera.executar()
        self.cv2.putText.assert_called()

    def test_camera_que_nao_abre(self):
        self.montar([], [], aberta=False)
        with self.assertRaisesRegex(GestosIndisponiveis, "camera 0"):
            camera.executar()

    def test_permissao_faltando(self):
        self.montar([], [], permissoes=["libere a Acessibilidade"])
        with self.assertRaisesRegex(GestosIndisponiveis, "Acessibilidade"):
            camera.executar()

    def test_camera_que_para_de_mandar_imagem(self):
        self.montar([False] * (camera.FALHAS_TOLERADAS + 1), [])
        with self.assertRaisesRegex(GestosIndisponiveis, "parou"):
            camera.executar()
        self.assertTrue(self.webcam.solta)

    def test_fechar_pelo_botao_da_janela(self):
        self.montar([True, True], [[], []], teclas=[-1, -1], janela=[0.0])
        camera.executar()
        self.assertEqual(len(self.webcam.quadros), 1)

    def test_janela_que_some_no_macos(self):
        self.montar([True, True], [[], []], teclas=[-1, -1], janela=None)
        self.cv2.getWindowProperty.side_effect = self.cv2.error("NULL window")
        camera.executar()
        self.assertEqual(len(self.webcam.quadros), 1)

    def test_freio_do_canto(self):
        self.montar([True], [[]])
        self.cv2.imshow.side_effect = FalhaSegura
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(camera.executar(), 0)
        self.assertIn("freio", saida.getvalue())

    def test_desenha_gesto_sem_nome(self):
        cv2 = mock.MagicMock()
        quadro = mock.MagicMock(shape=(100, 200, 3))
        camera.desenhar(cv2, quadro, [("Right", montar_mao())], [(0, 1)], 7)
        self.assertEqual(cv2.putText.call_args.args[1], "dedos 0111")


class TestComando(unittest.TestCase):
    def test_gestos_nao_cria_pasta(self):
        with (
            mock.patch.object(main.camera_gestos, "executar", return_value=0) as executar,
            mock.patch.object(main.Config, "carregar") as carregar,
        ):
            self.assertEqual(main.main(["gestos", "--camera", "1", "--canhoto"]), 0)
        executar.assert_called_once_with(1, False)
        carregar.assert_not_called()

    def test_gestos_indisponiveis(self):
        erro = GestosIndisponiveis("falta cv2")
        with (
            mock.patch.object(main.camera_gestos, "executar", side_effect=erro),
            contextlib.redirect_stderr(io.StringIO()) as saida,
        ):
            self.assertEqual(main.main(["gestos"]), 1)
        self.assertIn("falta cv2", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
