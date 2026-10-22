"""Controle do mouse por gestos e quadro de desenho.

Nada aqui abre camera, mexe no mouse ou muda volume de verdade: as maos sao
montadas ponto a ponto, o mouse e um `mock` e o sistema e trocado por um falso.
Por isso a suite roda sem OpenCV, MediaPipe e PyAutoGUI instalados — que e
justamente o caso de quem so usa o organizador de documentos.
"""

from __future__ import annotations

import contextlib
import io
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import main
from autodoc.gestos import GestosIndisponiveis, camera, quadro, sistema
from autodoc.gestos.controle import (
    CLIQUE_DUPLO,
    INTERVALO_AJUSTE,
    INTERVALO_ROLAGEM,
    TOQUE_MAXIMO,
    ZONA_ALAVANCA,
    Alavanca,
    Controlador,
)
from autodoc.gestos.cursor import AREA, Cursor, FiltroUmEuro
from autodoc.gestos.reconhecimento import (
    PINCA_ABRE,
    PINCA_FECHA,
    Gesto,
    Mao,
    aberturas,
    centro_da_palma,
    classificar,
    dedos_abertos,
    espelhar,
    separar_maos,
    tamanho_da_mao,
)
from autodoc.gestos.sistema import RecursoIndisponivel

# x da base, de cada dedo: (base, junta, ponta)
DEDOS = {"indicador": (5, 6, 8, 0.44), "medio": (9, 10, 12, 0.48), "anelar": (13, 14, 16, 0.52), "minimo": (17, 18, 20, 0.56)}


def ponto(x, y, z=0.0):
    return SimpleNamespace(x=x, y=y, z=z)


def montar_mao(abertos=tuple(DEDOS), pinca=None, afastamento=0.0, escala=1.0, girar=False, x=0.0, y=0.0):
    """Uma mao de pe, pulso embaixo, palma para a camera.

    `pinca` encosta o polegar na ponta do "indicador" ou do "medio";
    `afastamento` o afasta dela, em palmas. `escala` aproxima ou afasta a mao
    da camera, `girar` a deita, e `x`/`y` a deslocam no quadro.
    """
    pontos = [ponto(0.5, 0.9) for _ in range(21)]
    for nome, (base, junta, ponta, base_x) in DEDOS.items():
        pontos[base] = ponto(base_x, 0.6)
        pontos[junta] = ponto(base_x, 0.5)
        pontos[ponta] = ponto(base_x, 0.4 if nome in abertos else 0.62)
    pontos[4] = ponto(0.30, 0.70)
    if pinca:
        alvo = pontos[DEDOS[pinca][2]]
        # Afasta para cima, e nao para o lado, para nao chegar perto do dedo vizinho.
        pontos[4] = ponto(alvo.x, alvo.y - afastamento * tamanho_da_mao(pontos))

    pulso = pontos[0]
    resultado = []
    for p in pontos:
        dx, dy = (p.x - pulso.x) * escala, (p.y - pulso.y) * escala
        if girar:
            dx, dy = -dy, dx
        resultado.append(ponto(pulso.x + dx + x, pulso.y + dy + y))
    return resultado


class TestMedidas(unittest.TestCase):
    def test_dedos_abertos_e_fechados(self):
        self.assertEqual(dedos_abertos(montar_mao()), [True] * 4)
        self.assertEqual(dedos_abertos(montar_mao(())), [False] * 4)
        self.assertEqual(dedos_abertos(montar_mao(("medio",))), [False, True, False, False])

    def test_mao_deitada_continua_com_os_dedos_abertos(self):
        # A primeira versao comparava so a altura: deitar a mao fechava os dedos.
        self.assertEqual(dedos_abertos(montar_mao(girar=True)), [True] * 4)

    def test_pinca_nao_depende_da_distancia_da_camera(self):
        perto = aberturas(montar_mao(pinca="indicador", afastamento=0.2))
        longe = aberturas(montar_mao(pinca="indicador", afastamento=0.2, escala=0.4))
        self.assertAlmostEqual(perto[0], 0.2)
        self.assertAlmostEqual(longe[0], 0.2)

    def test_mao_degenerada_nao_divide_por_zero(self):
        self.assertGreater(tamanho_da_mao([ponto(0.5, 0.5)] * 21), 0)

    def test_centro_da_palma(self):
        x, y = centro_da_palma(montar_mao())
        self.assertAlmostEqual(x, 0.5)
        self.assertAlmostEqual(y, 0.66)

    def test_espelhar(self):
        espelhado = espelhar([ponto(0.2, 0.3, 0.1)])
        self.assertEqual((espelhado[0].x, espelhado[0].y, espelhado[0].z), (0.8, 0.3, 0.1))


class TestClassificar(unittest.TestCase):
    def test_gestos(self):
        self.assertEqual(classificar(montar_mao()), Gesto.MOVER)
        self.assertEqual(classificar(montar_mao(())), Gesto.PUNHO)
        self.assertEqual(classificar(montar_mao(pinca="indicador")), Gesto.PINCA_INDICADOR)
        self.assertEqual(classificar(montar_mao(pinca="medio")), Gesto.PINCA_MEDIO)

    def test_pinca_de_longe_e_de_perto(self):
        for escala in (0.3, 1.0, 1.5):
            self.assertEqual(classificar(montar_mao(pinca="indicador", escala=escala)), Gesto.PINCA_INDICADOR)

    def test_vale_o_dedo_mais_perto_do_polegar(self):
        # Polegar entre os dois, um pouco mais perto do medio.
        pontos = montar_mao()
        pontos[4] = ponto(0.465, 0.4)
        self.assertEqual(classificar(pontos), Gesto.PINCA_MEDIO)

    def test_histerese(self):
        meio_termo = (PINCA_FECHA + PINCA_ABRE) / 2
        for dedo, gesto in (("indicador", Gesto.PINCA_INDICADOR), ("medio", Gesto.PINCA_MEDIO)):
            entre = montar_mao(pinca=dedo, afastamento=meio_termo)
            self.assertEqual(classificar(entre, Gesto.MOVER), Gesto.MOVER)
            self.assertEqual(classificar(entre, gesto), gesto)
            longe = montar_mao(pinca=dedo, afastamento=PINCA_ABRE + 0.05)
            self.assertEqual(classificar(longe, gesto), Gesto.MOVER)


class TestMao(unittest.TestCase):
    def test_mao_nova_comeca_movendo(self):
        self.assertEqual(Mao().atualizar(montar_mao(pinca="indicador")), Gesto.MOVER)

    def test_gesto_confirma_no_segundo_quadro(self):
        mao = Mao()
        mao.atualizar(montar_mao())
        self.assertEqual(mao.atualizar(montar_mao(pinca="indicador")), Gesto.MOVER)
        self.assertEqual(mao.atualizar(montar_mao(pinca="indicador")), Gesto.PINCA_INDICADOR)

    def test_sem_mao(self):
        mao = Mao()
        mao.atualizar(montar_mao())
        self.assertEqual(mao.atualizar(None), Gesto.NENHUM)
        self.assertIsNone(mao.pontos)


class TestSepararMaos(unittest.TestCase):
    def test_nenhuma(self):
        self.assertEqual(separar_maos([]), (None, None))

    def test_uma_mao_sozinha_e_sempre_a_principal(self):
        esquerda = montar_mao()
        self.assertEqual(separar_maos([("Left", esquerda)]), (esquerda, None))

    def test_duas_pelo_rotulo(self):
        direita, esquerda = montar_mao(x=-0.2), montar_mao(x=0.2)
        maos = [("Left", esquerda), ("Right", direita)]
        self.assertEqual(separar_maos(maos), (direita, esquerda))
        self.assertEqual(separar_maos(maos, destro=False), (esquerda, direita))

    def test_rotulos_iguais_decide_a_posicao(self):
        a_esquerda, a_direita = montar_mao(x=-0.2), montar_mao(x=0.2)
        self.assertEqual(separar_maos([("Left", a_esquerda), ("Left", a_direita)]), (a_direita, a_esquerda))
        self.assertEqual(separar_maos([("Left", a_direita), ("Left", a_esquerda)]), (a_direita, a_esquerda))


class TestCursor(unittest.TestCase):
    def test_filtro_deixa_passar_o_primeiro_valor(self):
        self.assertEqual(FiltroUmEuro()(100.0, 0.0), 100.0)

    def test_filtro_segura_a_tremida(self):
        filtro = FiltroUmEuro()
        valores = [filtro(100 + (3 if i % 2 else -3), i / 30) for i in range(60)]
        self.assertLess(max(valores[30:]) - min(valores[30:]), 1.5)

    def test_filtro_acompanha_movimento_rapido(self):
        filtro = FiltroUmEuro()
        for i in range(10):
            ultimo = filtro(i * 50.0, i / 30)
        self.assertGreater(ultimo, 9 * 50 - 60)

    def test_filtro_reiniciado_esquece(self):
        filtro = FiltroUmEuro()
        filtro(0.0, 0.0)
        filtro.reiniciar()
        self.assertEqual(filtro(500.0, 0.0), 500.0)

    def test_area_central_cobre_a_tela(self):
        esquerda, topo, direita, base = AREA
        cursor = Cursor(1000, 800)
        self.assertEqual(cursor.posicionar((esquerda + direita) / 2, (topo + base) / 2, 0.0), (500, 400))
        cursor.reiniciar()
        self.assertEqual(cursor.posicionar(0.0, 1.0, 0.0), (1, 798))  # fora da area: borda, nunca o canto


class TestAlavanca(unittest.TestCase):
    def test_primeira_posicao_e_a_origem(self):
        alavanca = Alavanca(0.1)
        self.assertEqual(alavanca.mover(0.5, 0.5, 0.0), (0, 0))
        self.assertEqual(alavanca.mover(0.5, 0.5, 1.0), (0, 0))

    def test_quanto_mais_longe_mais_rapido(self):
        alavanca = Alavanca(0.1)
        alavanca.mover(0.5, 0.5, 0.0)
        self.assertEqual(alavanca.mover(0.5, 0.5 - ZONA_ALAVANCA * 2.5, 1.0), (0, 2))
        self.assertEqual(alavanca.mover(0.5 - ZONA_ALAVANCA * 1.5, 0.5, 2.0), (-1, 0))

    def test_respeita_o_intervalo(self):
        alavanca = Alavanca(0.1)
        alavanca.mover(0.5, 0.5, 0.0)
        self.assertEqual(alavanca.mover(0.5, 0.3, 0.05), (0, 0))
        self.assertNotEqual(alavanca.mover(0.5, 0.3, 0.2), (0, 0))
        self.assertEqual(alavanca.mover(0.5, 0.3, 0.25), (0, 0))

    def test_soltar_esquece_a_origem(self):
        alavanca = Alavanca(0.1)
        alavanca.mover(0.5, 0.5, 0.0)
        alavanca.soltar()
        self.assertEqual(alavanca.mover(0.9, 0.9, 1.0), (0, 0))


class SistemaFalso(sistema.Sistema):
    def __init__(self, mouse):
        super().__init__(mouse)
        self.ajustes = []
        self.duplos = []

    def clique_duplo(self, x, y):
        self.duplos.append((x, y))

    def ajustar_volume(self, delta):
        self.ajustes.append(("volume", round(delta, 2)))

    def ajustar_brilho(self, delta):
        raise RecursoIndisponivel("sem brilho aqui")


def novo_mouse():
    mouse = mock.Mock()
    mouse.size.return_value = (1000, 800)
    return mouse


class CursorDireto:
    """Sem filtro: a palma em (x, y) vira (x*1000, y*1000)."""

    def __init__(self):
        self.reiniciado = 0

    def posicionar(self, x, y, tempo):
        return round(x * 1000), round(y * 1000)

    def reiniciar(self):
        self.reiniciado += 1


class TestControlador(unittest.TestCase):
    def setUp(self):
        self.mouse = novo_mouse()
        self.sistema = SistemaFalso(self.mouse)
        self.controle = Controlador(self.mouse, self.sistema)
        self.controle.cursor = CursorDireto()
        self.agora = 0.0

    def quadro(self, gesto, pontos=None, passo=1 / 30, secundaria=False):
        self.agora += passo
        if pontos is None and gesto != Gesto.NENHUM:
            pontos = montar_mao()
        aplicar = self.controle.aplicar_secundaria if secundaria else self.controle.aplicar
        aplicar(gesto, pontos, self.agora)

    def test_mover(self):
        self.quadro(Gesto.MOVER)
        self.mouse.moveTo.assert_called_once_with(500, 660)

    def test_toque_rapido_e_clique_onde_a_pinca_fechou(self):
        self.quadro(Gesto.PINCA_INDICADOR)
        self.quadro(Gesto.PINCA_INDICADOR, montar_mao(x=0.005))
        self.quadro(Gesto.MOVER)
        self.mouse.click.assert_called_once_with(500, 660)
        self.mouse.mouseDown.assert_not_called()

    def test_dois_toques_sao_clique_duplo(self):
        for _ in range(2):
            self.quadro(Gesto.PINCA_INDICADOR)
            self.quadro(Gesto.MOVER)
        self.assertEqual(self.sistema.duplos, [(500, 660)])
        self.quadro(Gesto.PINCA_INDICADOR, passo=CLIQUE_DUPLO)
        self.quadro(Gesto.MOVER)
        self.assertEqual(self.mouse.click.call_count, 2)

    def test_pinca_segurada_arrasta(self):
        self.quadro(Gesto.PINCA_INDICADOR)
        self.quadro(Gesto.PINCA_INDICADOR, passo=TOQUE_MAXIMO + 0.01)
        self.mouse.mouseDown.assert_called_once_with(500, 660, button="left")
        self.quadro(Gesto.PINCA_INDICADOR, montar_mao(x=0.1))
        self.mouse.dragTo.assert_called_with(600, 660, button="left", mouseDownUp=False)
        self.quadro(Gesto.MOVER)
        self.mouse.mouseUp.assert_called_once_with(button="left")
        self.mouse.click.assert_not_called()

    def test_pinca_que_anda_arrasta_na_hora(self):
        self.quadro(Gesto.PINCA_INDICADOR)
        self.quadro(Gesto.PINCA_INDICADOR, montar_mao(y=0.05))
        self.mouse.mouseDown.assert_called_once()

    def test_pinca_do_medio_e_clique_direito_uma_vez(self):
        for _ in range(5):
            self.quadro(Gesto.PINCA_MEDIO)
        self.mouse.click.assert_called_once_with(button="right")

    def test_punho_rola(self):
        self.quadro(Gesto.PUNHO, montar_mao(()))
        self.quadro(Gesto.PUNHO, montar_mao((), y=0.12), passo=INTERVALO_ROLAGEM)
        self.mouse.scroll.assert_called_once_with(-2)
        self.quadro(Gesto.PUNHO, montar_mao((), x=0.06), passo=INTERVALO_ROLAGEM)
        self.mouse.hscroll.assert_called_once_with(1)

    def test_soltar_o_punho_esquece_a_origem(self):
        self.quadro(Gesto.PUNHO, montar_mao(()))
        self.quadro(Gesto.MOVER)
        self.quadro(Gesto.PUNHO, montar_mao((), y=0.2), passo=1)
        self.mouse.scroll.assert_not_called()

    def test_mao_sumida(self):
        self.quadro(Gesto.PINCA_INDICADOR)
        self.quadro(Gesto.PINCA_INDICADOR, passo=TOQUE_MAXIMO + 0.01)
        self.quadro(Gesto.NENHUM)
        self.mouse.mouseUp.assert_called_once_with(button="left")
        self.assertEqual(self.controle.cursor.reiniciado, 1)

    def test_soltar_tudo(self):
        self.quadro(Gesto.PINCA_INDICADOR)
        self.quadro(Gesto.PINCA_INDICADOR, passo=TOQUE_MAXIMO + 0.01)
        self.controle.soltar_tudo()
        self.controle.soltar_tudo()
        self.mouse.mouseUp.assert_called_once_with(button="left")

    def test_secundaria_ajusta_o_volume(self):
        self.quadro(Gesto.PINCA_INDICADOR, secundaria=True)
        self.quadro(Gesto.PINCA_INDICADOR, montar_mao(y=-0.06), passo=INTERVALO_AJUSTE, secundaria=True)
        self.assertEqual(self.sistema.ajustes, [("volume", 0.05)])

    def test_secundaria_sem_brilho_avisa_uma_vez(self):
        self.quadro(Gesto.PINCA_INDICADOR, secundaria=True)
        with self.assertLogs("autodoc.gestos.controle", "WARNING") as registro:
            for _ in range(3):
                self.quadro(Gesto.PINCA_INDICADOR, montar_mao(x=0.06), passo=INTERVALO_AJUSTE, secundaria=True)
        self.assertEqual(registro.output, ["WARNING:autodoc.gestos.controle:sem brilho aqui"])

    def test_secundaria_sem_pinca_nao_faz_nada(self):
        self.quadro(Gesto.PINCA_INDICADOR, secundaria=True)
        self.quadro(Gesto.MOVER, secundaria=True)
        self.quadro(Gesto.PINCA_INDICADOR, montar_mao(y=-0.2), passo=1, secundaria=True)
        self.assertEqual(self.sistema.ajustes, [])

    def test_cursor_de_verdade_comeca_no_tamanho_da_tela(self):
        self.assertEqual((Controlador(novo_mouse(), self.sistema).cursor.largura), 1000)


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

    def test_clique_duplo_fora_do_mac_e_um_clique_a_mais(self):
        mouse = mock.Mock()
        sistema.Windows(mouse).clique_duplo(10, 20)
        mouse.click.assert_called_once_with(10, 20)

    def test_clique_duplo_no_mac_marca_o_segundo_clique(self):
        quartz = mock.Mock()
        with mock.patch.dict(sys.modules, {"Quartz": quartz}):
            sistema.MacOS(None).clique_duplo(10, 20)
        self.assertEqual(quartz.CGEventPost.call_count, 2)
        quartz.CGEventSetIntegerValueField.assert_called_with(mock.ANY, quartz.kCGMouseEventClickState, 2)

    def test_rolagem_na_unidade_do_sistema(self):
        mouse = mock.Mock()
        sistema.MacOS(mouse).rolar_vertical(-1)
        mouse.scroll.assert_called_once_with(-2)
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
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.destino = self.pasta / "hand_landmarker.task"

    def test_pasta_de_cache_por_sistema(self):
        with mock.patch.dict(camera.os.environ, {"LOCALAPPDATA": "C:/local", "XDG_CACHE_HOME": "/cache"}):
            self.assertEqual(camera.pasta_cache("win32"), Path("C:/local/AutoDoc"))
            self.assertEqual(camera.pasta_cache("linux"), Path("/cache/autodoc"))
        self.assertEqual(camera.pasta_cache("darwin"), Path.home() / "Library" / "Caches" / "AutoDoc")
        self.assertIsInstance(camera.pasta_cache(), Path)

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
        self.baixar()
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
        with mock.patch.dict(sys.modules, {"cv2": None, "pyautogui": None}):
            with self.assertRaisesRegex(GestosIndisponiveis, "requirements-gestos"):
                camera.importar_visao()
            with self.assertRaisesRegex(GestosIndisponiveis, "pyautogui"):
                camera.importar_mouse()

    def test_com_dependencias(self):
        falsos = {nome: mock.MagicMock() for nome in ("cv2", "mediapipe", "pyautogui", "mediapipe.tasks", "mediapipe.tasks.python")}
        with mock.patch.dict(sys.modules, falsos):
            self.assertEqual(len(camera.importar_visao()), 4)
            self.assertIs(camera.importar_mouse(), falsos["pyautogui"])


class FalhaSegura(Exception):
    pass


class CameraFalsa:
    def __init__(self, leituras, aberta=True):
        self.leituras = list(leituras)
        self.aberta = aberta
        self.solta = False

    def isOpened(self):
        return self.aberta

    def read(self):
        return self.leituras.pop(0)

    def release(self):
        self.solta = True


class Rotulo:
    def __init__(self, nome):
        self.category_name = nome


class ComCameraFalsa(unittest.TestCase):
    """Monta OpenCV, MediaPipe e webcam falsos, quadro a quadro.

    `maos` tem uma lista de (rotulo, pontos) por quadro lido; os pontos sao
    dados ja como a pessoa os ve — o detector falso os desespelha, porque o de
    verdade recebe a imagem crua e o codigo espelha depois.
    """

    def montar(self, maos, lidos=None, teclas=None, aberta=True, janela=True):
        lidos = [True] * len(maos) if lidos is None else lidos
        imagem = mock.MagicMock(shape=(100, 200, 3))
        self.webcam = CameraFalsa([(lido, imagem) for lido in lidos], aberta)

        cv2 = mock.MagicMock()
        cv2.error = type("error", (Exception,), {})
        cv2.VideoCapture.return_value = self.webcam
        cv2.flip.side_effect = lambda imagem, _: imagem
        teclas = list(teclas if teclas is not None else [-1] * (len(maos) - 1) + [27])
        cv2.waitKey.side_effect = lambda _: teclas.pop(0)
        cv2.getWindowProperty.return_value = 1.0
        if janela is not True:
            cv2.getWindowProperty.side_effect = janela
        self.cv2 = cv2

        fila = list(maos)

        def detectar(_imagem, _ms):
            quadro = fila.pop(0)
            return SimpleNamespace(
                handedness=[[Rotulo(rotulo)] for rotulo, _ in quadro],
                hand_landmarks=[espelhar(pontos) for _, pontos in quadro],
            )

        self.detector = mock.Mock(detect_for_video=mock.Mock(side_effect=detectar))
        vision = mock.MagicMock()
        vision.HandLandmarker.create_from_options.return_value = self.detector
        vision.HandLandmarksConnections.HAND_CONNECTIONS = [SimpleNamespace(start=0, end=1)]
        self.visao = (cv2, mock.MagicMock(), mock.MagicMock(), vision)

        pilha = contextlib.ExitStack()
        self.addCleanup(pilha.close)
        pilha.enter_context(mock.patch.object(camera, "obter_modelo", return_value=Path("modelo.task")))
        pilha.enter_context(contextlib.redirect_stdout(io.StringIO()))
        # O relogio anda 0,1 s por quadro, para tocar e segurar terem duracao.
        relogio = iter(i / 10 for i in range(1000))
        pilha.enter_context(mock.patch.object(camera.time, "monotonic", lambda: next(relogio)))
        return pilha


class TestSessao(ComCameraFalsa):
    def sessao(self):
        return camera.Sessao(*self.visao, 0, "teste")

    def test_camera_que_nao_abre(self):
        self.montar([], aberta=False)
        with self.assertRaisesRegex(GestosIndisponiveis, "camera 0"):
            self.sessao()

    def test_modelo_que_falha_solta_a_camera(self):
        self.montar([])
        with mock.patch.object(camera, "obter_modelo", side_effect=GestosIndisponiveis("sem rede")):
            with self.assertRaises(GestosIndisponiveis):
                self.sessao()
        self.assertTrue(self.webcam.solta)

    def test_quadros_espelhados_e_maos_com_rotulo(self):
        direita = montar_mao(x=0.2)
        self.montar([[("Right", direita)]])
        with self.sessao() as sessao:
            imagem, maos, agora = next(sessao.quadros())
        self.cv2.flip.assert_called_once()
        self.assertEqual(maos[0][0], "Right")
        self.assertAlmostEqual(maos[0][1][0].x, direita[0].x)
        self.assertTrue(self.webcam.solta)
        self.detector.close.assert_called_once_with()

    def test_camera_que_para_de_mandar_imagem(self):
        self.montar([], lidos=[False] * (camera.FALHAS_TOLERADAS + 1))
        with self.sessao() as sessao:
            with self.assertRaisesRegex(GestosIndisponiveis, "parou"):
                list(sessao.quadros())

    def test_mostrar(self):
        self.montar([], teclas=[ord("c"), 27, -1, -1], janela=[1.0, 1.0, 0.0])
        sessao = self.sessao()
        self.assertEqual(sessao.mostrar(None), ord("c"))
        self.assertIsNone(sessao.mostrar(None))  # Esc
        self.assertEqual(sessao.mostrar(None), 255)
        self.assertIsNone(sessao.mostrar(None))  # janela fechada pelo botao

    def test_janela_que_some_no_macos(self):
        self.montar([], teclas=[-1])
        self.cv2.getWindowProperty.side_effect = self.cv2.error("NULL window")
        self.assertIsNone(self.sessao().mostrar(None))


class TestExecutar(ComCameraFalsa):
    def montar_mouse(self, maos, permissoes=(), **opcoes):
        self.montar(maos, **opcoes)
        self.mouse = novo_mouse()
        self.mouse.FailSafeException = FalhaSegura
        self.sistema = SistemaFalso(self.mouse)
        self.sistema.permissoes_faltando = lambda: list(permissoes)
        pilha = contextlib.ExitStack()
        self.addCleanup(pilha.close)
        pilha.enter_context(mock.patch.object(camera, "importar_visao", return_value=self.visao))
        pilha.enter_context(mock.patch.object(camera, "importar_mouse", return_value=self.mouse))
        pilha.enter_context(mock.patch.object(camera, "sistema_atual", return_value=self.sistema))

    def test_mao_direita_sozinha_move_o_cursor(self):
        self.montar_mouse([[("Right", montar_mao())]] * 3)
        self.assertEqual(camera.executar(), 0)
        self.mouse.moveTo.assert_called()
        self.assertEqual(self.mouse.PAUSE, 0)
        self.assertTrue(self.webcam.solta)

    def test_toque_com_a_mao_principal_clica(self):
        maos = [[("Right", montar_mao())]] + [[("Right", montar_mao(pinca="indicador"))]] * 2 + [[("Right", montar_mao())]] * 3
        self.montar_mouse(maos)
        camera.executar()
        self.mouse.click.assert_called_once()

    def test_pinca_da_secundaria_ajusta_volume(self):
        direita = montar_mao(x=0.2)
        maos = [[("Right", direita), ("Left", montar_mao(pinca="indicador", x=-0.2))]] * 3
        maos += [[("Right", direita), ("Left", montar_mao(pinca="indicador", x=-0.2, y=-0.06))]] * 4
        self.montar_mouse(maos)
        camera.executar()
        self.assertIn(("volume", 0.05), self.sistema.ajustes)

    def test_permissao_faltando(self):
        self.montar_mouse([], permissoes=["libere a Acessibilidade"])
        with self.assertRaisesRegex(GestosIndisponiveis, "Acessibilidade"):
            camera.executar()

    def test_freio_do_canto_solta_o_botao(self):
        maos = [[("Right", montar_mao())]] + [[("Right", montar_mao(pinca="indicador"))]] * 6
        self.montar_mouse(maos)
        self.mouse.dragTo.side_effect = FalhaSegura
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(camera.executar(), 0)
        self.assertIn("freio", saida.getvalue())
        self.mouse.mouseUp.assert_called_once_with(button="left")

    def test_legenda(self):
        self.assertEqual(camera.legenda(Gesto.NENHUM, None), "sem mao")
        self.assertIn("pinca indicador 0.00", camera.legenda(Gesto.PINCA_INDICADOR, montar_mao(pinca="indicador")))

    def test_desenha_a_principal_de_outra_cor(self):
        cv2 = mock.MagicMock()
        principal, outra = montar_mao(), montar_mao(x=0.1)
        camera.desenhar(cv2, mock.MagicMock(shape=(100, 200, 3)), [("Right", principal), ("Left", outra)], [(0, 1)], principal, ["oi"])
        cores = {chamada.args[3] for chamada in cv2.circle.call_args_list}
        self.assertEqual(cores, {camera.COR_PRINCIPAL, camera.COR_SECUNDARIA})


class NumpyFalso:
    uint8 = "uint8"

    @staticmethod
    def full(forma, valor, dtype):
        return mock.MagicMock(name="tela")


class TestFolha(unittest.TestCase):
    def setUp(self):
        self.cv2 = mock.MagicMock()
        self.folha = quadro.Folha(self.cv2, NumpyFalso)

    def tracos(self):
        return [(c.args[1], c.args[2], c.args[3]) for c in self.cv2.line.call_args_list]

    def test_desenha_ligando_os_pontos(self):
        for x in (10, 20, 30):
            self.folha.aplicar(Gesto.PINCA_INDICADOR, (x, 5))
        self.assertEqual(self.tracos(), [((10, 5), (10, 5), quadro.TINTA), ((10, 5), (20, 5), quadro.TINTA), ((20, 5), (30, 5), quadro.TINTA)])

    def test_mover_levanta_a_caneta(self):
        self.folha.aplicar(Gesto.PINCA_INDICADOR, (10, 5))
        self.folha.aplicar(Gesto.MOVER, (50, 50))
        self.folha.aplicar(Gesto.PINCA_INDICADOR, (90, 5))
        self.assertEqual(self.tracos()[-1][:2], ((90, 5), (90, 5)))

    def test_borracha_e_traco_branco_grosso(self):
        self.folha.aplicar(Gesto.PINCA_INDICADOR, (10, 5))
        self.folha.aplicar(Gesto.PINCA_MEDIO, (20, 5))
        chamada = self.cv2.line.call_args
        self.assertEqual(chamada.args[1:5], ((20, 5), (20, 5), quadro.BRANCO, quadro.RAIO_BORRACHA * 2))

    def test_sem_mao_nao_risca(self):
        self.folha.aplicar(Gesto.PINCA_INDICADOR, None)
        self.cv2.line.assert_not_called()

    def test_limpar_troca_a_tela(self):
        antes = self.folha.tela
        self.folha.limpar()
        self.assertIsNot(self.folha.tela, antes)

    def test_compor_mostra_o_cursor_de_cada_gesto(self):
        for gesto in (Gesto.MOVER, Gesto.PINCA_INDICADOR, Gesto.PINCA_MEDIO):
            self.folha.compor(mock.MagicMock(), gesto, (5, 5), "")
        raios = [c.args[2] for c in self.cv2.circle.call_args_list]
        self.assertEqual(raios, [10, quadro.ESPESSURA, quadro.RAIO_BORRACHA])
        self.folha.compor(mock.MagicMock(), Gesto.NENHUM, None, "")
        self.assertEqual(self.cv2.circle.call_count, 3)


class TestQuadro(ComCameraFalsa):
    def test_desenha_apaga_e_limpa(self):
        maos = [[("Left", montar_mao())]]
        maos += [[("Left", montar_mao(pinca="indicador", x=dx))] for dx in (0, 0.01, 0.02)]
        maos += [[]]
        teclas = [-1, -1, -1, ord("c"), 27]
        self.montar(maos, teclas=teclas)
        with (
            mock.patch.object(quadro, "importar_visao", return_value=self.visao),
            mock.patch.object(quadro, "Folha") as Folha,
            mock.patch.dict(sys.modules, {"numpy": NumpyFalso}),
        ):
            self.assertEqual(quadro.executar_quadro(), 0)
        folha = Folha.return_value
        gestos = [c.args[0] for c in folha.aplicar.call_args_list]
        self.assertEqual(gestos, [Gesto.MOVER, Gesto.MOVER, Gesto.PINCA_INDICADOR, Gesto.PINCA_INDICADOR, Gesto.NENHUM])
        self.assertIsNone(folha.aplicar.call_args_list[-1].args[1])
        folha.limpar.assert_called_once_with()


class TestComando(unittest.TestCase):
    def test_gestos_nao_cria_pasta(self):
        with (
            mock.patch.object(main.camera_gestos, "executar", return_value=0) as executar,
            mock.patch.object(main.Config, "carregar") as carregar,
        ):
            self.assertEqual(main.main(["gestos", "--camera", "1", "--canhoto"]), 0)
        executar.assert_called_once_with(1, False)
        carregar.assert_not_called()

    def test_quadro(self):
        with mock.patch.object(main.quadro_gestos, "executar_quadro", return_value=0) as executar:
            self.assertEqual(main.main(["gestos", "--quadro"]), 0)
        executar.assert_called_once_with(0, True)

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
