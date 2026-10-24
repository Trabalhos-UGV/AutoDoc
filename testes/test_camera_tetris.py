"""A camera comandando o Tetris, com camera, MediaPipe e janela falsos."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest import mock

from autodoc.gestos import camera, camera_tetris
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

    def test_parar_sai_no_quadro_seguinte(self):
        self.preparar([[("Right", mao(4))]] * 3)
        parar = threading.Event()
        parar.set()
        rodar_com_camera(self.sessao, self.partida, self.servidor, parar, self.cv2)
        self.assertEqual(self.servidor.retratos, [])


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
        with (
            mock.patch.object(camera_tetris, "importar_visao", return_value=(cv2, None, None, None)),
            mock.patch.object(camera_tetris, "Sessao", SessaoFalsa),
            mock.patch("autodoc.web.janela.abrir", side_effect=abrir),
        ):
            self.assertEqual(camera_tetris.jogar_com_camera(camera=2, porta=18788), 0)

        sessao = SessaoFalsa.abertas[0]
        self.assertEqual((sessao.indice, sessao.fechada), (2, True))
        self.assertTrue(visto["estado"]["camera"])
        self.assertEqual(visto["titulo"], "AutoDoc — Tetris")
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(visto["url"] + "api/estado", timeout=1)


if __name__ == "__main__":
    unittest.main()
