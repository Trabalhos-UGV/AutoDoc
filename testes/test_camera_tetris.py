"""A camera comandando o Tetris, com camera, MediaPipe e janela falsos."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest import mock

from pathlib import Path

from autodoc.gestos import GestosIndisponiveis, camera, camera_tetris
from autodoc.gestos.camera_tetris import codificar, maos_para_tela, rodar_com_camera
from autodoc.gestos.comandos_tetris import coluna_da_peca
from autodoc.gestos.servidor_tetris import Partida
from autodoc.gestos.tetris import Jogo, Peca
from testes.apoio_gestos import montar_mao
from testes.test_comandos_tetris import mao
from testes.test_gestos import ComCameraFalsa
from testes.test_servidor_tetris import EventoContado


class ServidorFalso:
    def __init__(self):
        self.retratos = []
        self.imagens = []

    def publicar(self, retrato):
        self.retratos.append(retrato)

    def publicar_imagem(self, jpeg):
        self.imagens.append(jpeg)


def partida_com_o():
    partida = Partida(Jogo(semente=3))
    partida.jogo.peca = Peca("O", linha=5, coluna=3)
    partida.camera = True
    return partida


class TestConversoes(unittest.TestCase):
    def test_maos_para_tela(self):
        principal, outra = montar_mao(x=0.1234), montar_mao()
        tela = maos_para_tela([("Right", principal), ("Left", outra)], principal)
        self.assertEqual([m["principal"] for m in tela], [True, False])
        self.assertEqual(tela[0]["pontos"][0], [0.623, 0.9])
        self.assertEqual(len(tela[1]["pontos"]), 21)

    def test_codificar_reduz_mantendo_a_proporcao(self):
        cv2 = mock.MagicMock()
        cv2.imencode.return_value = (True, SimpleNamespace(tobytes=lambda: b"jpeg"))
        jpeg, tamanho = codificar(cv2, mock.MagicMock(shape=(720, 1280, 3)))
        self.assertEqual((jpeg, tamanho), (b"jpeg", (480, 270)))
        self.assertEqual(cv2.resize.call_args.args[1], (480, 270))


class TestLaco(ComCameraFalsa):
    def preparar(self, maos, lidos=None):
        self.montar(maos, lidos=lidos)
        self.cv2.imencode.return_value = (True, SimpleNamespace(tobytes=lambda: b"\xff\xd8jpeg"))
        self.sessao = camera.Sessao(*self.visao, 0, "teste")
        self.partida = partida_com_o()
        self.servidor = ServidorFalso()

    def test_a_mao_leva_a_peca_e_tudo_vai_para_a_tela(self):
        quadros = [[("Right", mao(8))]] * 8
        self.preparar(quadros, lidos=[True] * 8 + [False] * (camera.FALHAS_TOLERADAS + 1))
        rodar_com_camera(self.sessao, self.partida, self.servidor, EventoContado(3), self.cv2)

        self.assertEqual(coluna_da_peca(self.partida.jogo), 8)
        # Um retrato por quadro da camera (mais os do teclado, depois que ela parou)...
        self.assertGreaterEqual(len(self.servidor.retratos), 8)
        self.assertTrue(self.servidor.retratos[0]["camera"])
        self.assertTrue(self.servidor.retratos[0]["maos"][0]["principal"])
        # ...e uma imagem a cada dois.
        self.assertEqual(len(self.servidor.imagens), 4)
        self.assertEqual(self.partida.camera_tamanho, (480, 240))

    def test_camera_que_para_cai_para_o_teclado(self):
        self.preparar([[("Right", mao(4))]], lidos=[True] + [False] * (camera.FALHAS_TOLERADAS + 1))
        with self.assertLogs("autodoc.gestos.camera_tetris", "WARNING"):
            rodar_com_camera(self.sessao, self.partida, self.servidor, EventoContado(3), self.cv2)
        self.assertFalse(self.partida.camera)
        self.assertEqual(self.partida.maos, [])
        self.assertFalse(self.servidor.retratos[-1]["camera"])

    def test_a_mascara_cobre_antes_de_codificar(self):
        self.preparar([[("Right", mao(4))]] * 2, lidos=[True] * 2 + [False] * (camera.FALHAS_TOLERADAS + 1))
        mascara = mock.Mock(aplicar=mock.Mock(side_effect=lambda imagem, personagem, agora: imagem))
        self.partida.personagem = "panda"
        rodar_com_camera(self.sessao, self.partida, self.servidor, EventoContado(1), self.cv2, mascara=mascara)
        self.assertEqual(mascara.aplicar.call_args.args[1], "panda")
        self.assertIs(self.cv2.resize.call_args.args[0], mascara.aplicar.call_args.args[0])

    def test_mascara_que_falha_segura_a_imagem(self):
        """Sem mascara, nenhum quadro sai: o rosto nao pode aparecer descoberto."""
        self.preparar([[("Right", mao(4))]] * 4, lidos=[True] * 4 + [False] * (camera.FALHAS_TOLERADAS + 1))
        mascara = mock.Mock(aplicar=mock.Mock(side_effect=RuntimeError("modelo quebrado")))
        with self.assertLogs("autodoc.gestos.camera_tetris", "ERROR") as registro:
            rodar_com_camera(self.sessao, self.partida, self.servidor, EventoContado(1), self.cv2, mascara=mascara)
        self.assertEqual(self.servidor.imagens, [])
        self.assertEqual(len([l for l in registro.output if "mascara" in l]), 1)  # avisa uma vez so
        self.assertGreaterEqual(len(self.servidor.retratos), 4)  # o jogo seguiu, quadro a quadro

    def test_falha_inesperada_cai_para_o_teclado(self):
        self.preparar([[("Right", mao(4))]] * 2)
        original = self.partida.passo
        falhas = [ValueError("defeito")]

        def passo(*argumentos):
            # Falha uma vez, no laco da camera; o do teclado segue normal.
            if falhas:
                raise falhas.pop()
            return original(*argumentos)

        self.partida.passo = passo
        with self.assertLogs("autodoc.gestos.camera_tetris", "ERROR"):
            rodar_com_camera(self.sessao, self.partida, self.servidor, EventoContado(2), self.cv2)
        self.assertFalse(self.partida.camera)

    def test_parar_sai_no_quadro_seguinte(self):
        self.preparar([[("Right", mao(4))]] * 3)
        parar = threading.Event()
        parar.set()
        rodar_com_camera(self.sessao, self.partida, self.servidor, parar, self.cv2)
        self.assertEqual(self.servidor.retratos, [])


class TestAbrirMascara(unittest.TestCase):
    def test_abre_com_o_modelo_do_rosto(self):
        vision = mock.MagicMock()
        with mock.patch.object(camera_tetris, "obter_modelo", return_value=Path("rosto.tflite")) as obter:
            mascara = camera_tetris.abrir_mascara(mock.MagicMock(), mock.MagicMock(), mock.MagicMock(), vision)
        self.assertIsNotNone(mascara)
        self.assertEqual(obter.call_args.args[1], camera_tetris.URL_MODELO_ROSTO)
        vision.FaceDetector.create_from_options.assert_called_once()

    def test_sem_o_modelo_o_jogo_abre_sem_mascara(self):
        with (
            mock.patch.object(camera_tetris, "obter_modelo", side_effect=GestosIndisponiveis("sem internet")),
            self.assertLogs("autodoc.gestos.camera_tetris", "WARNING"),
        ):
            self.assertIsNone(camera_tetris.abrir_mascara(None, None, None, None))


class SessaoFalsa:
    """Uma `Sessao` que entrega uns quadros e termina."""

    abertas = []

    def __init__(self, cv2, mediapipe, BaseOptions, vision, indice, titulo):
        self.indice, self.titulo = indice, titulo
        self.fechada = False
        SessaoFalsa.abertas.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechada = True

    def quadros(self):
        imagem = mock.MagicMock(shape=(480, 640, 3))
        for i in range(3):
            yield imagem, [("Right", mao(4))], i / 30


class TestJanela(unittest.TestCase):
    def test_abre_camera_janela_e_fecha_tudo(self):
        cv2 = mock.MagicMock()
        cv2.imencode.return_value = (True, SimpleNamespace(tobytes=lambda: b"\xff\xd8"))
        visto = {}

        def abrir(url, titulo):
            with urllib.request.urlopen(url + "api/estado", timeout=5) as resposta:
                visto["estado"] = json.loads(resposta.read())
            visto["titulo"] = titulo
            visto["url"] = url
            return "nativa"

        SessaoFalsa.abertas.clear()
        mascara = mock.Mock(aplicar=lambda imagem, personagem, agora: imagem)
        with (
            mock.patch.object(camera_tetris, "importar_visao", return_value=(cv2, None, None, None)),
            mock.patch.object(camera_tetris, "Sessao", SessaoFalsa),
            mock.patch.object(camera_tetris, "abrir_mascara", return_value=mascara),
            mock.patch("autodoc.web.janela.abrir", side_effect=abrir),
        ):
            self.assertEqual(camera_tetris.jogar_com_camera(camera=2, porta=18788), 0)

        sessao = SessaoFalsa.abertas[0]
        self.assertEqual((sessao.indice, sessao.fechada), (2, True))
        self.assertTrue(visto["estado"]["camera"])
        # Comeca escolhendo, e ja com um personagem: o rosto nunca aparece descoberto.
        self.assertTrue(visto["estado"]["escolhendo"])
        self.assertEqual(visto["estado"]["personagem"], "cachorro")
        self.assertEqual(visto["titulo"], "AutoDoc — Tetris")
        mascara.fechar.assert_called_once_with()
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(visto["url"] + "api/estado", timeout=1)


if __name__ == "__main__":
    unittest.main()
