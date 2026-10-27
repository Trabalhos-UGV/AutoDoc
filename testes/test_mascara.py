"""O personagem que cobre o rosto.

A geometria e a memoria rodam em qualquer maquina. O desenho de verdade precisa
de OpenCV e numpy, e e pulado onde eles nao estao — o caso de quem so usa o
organizador de documentos.
"""

from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace
from unittest import mock

from autodoc.gestos import mascara
from autodoc.gestos.mascara import SALTO, DetectorDeRosto, Mascara, Memoria, Rosto, rosto_da_deteccao, suavizar

TEM_OPENCV = all(importlib.util.find_spec(nome) for nome in ("cv2", "numpy"))


def deteccao(x=100, y=50, lado=80, olhos=((0.40, 0.30), (0.50, 0.30))):
    return SimpleNamespace(
        bounding_box=SimpleNamespace(origin_x=x, origin_y=y, width=lado, height=lado),
        keypoints=[SimpleNamespace(x=ox, y=oy) for ox, oy in olhos],
    )


class TestGeometria(unittest.TestCase):
    def test_personagem_maior_que_o_rosto_e_um_pouco_acima(self):
        rosto = rosto_da_deteccao(deteccao(), 640, 480)
        self.assertEqual((rosto.x, rosto.lado), (140, 80 * mascara.TAMANHO))
        self.assertLess(rosto.y, 50 + 40)  # acima do meio da caixa
        self.assertEqual(rosto.angulo, 0)

    def test_inclinacao_pela_linha_dos_olhos_em_pixels(self):
        # Mesma subida nos dois eixos normalizados, quadro mais largo que alto:
        # em pixels a linha sobe menos que 45 graus.
        rosto = rosto_da_deteccao(deteccao(olhos=((0.40, 0.30), (0.50, 0.40))), 640, 480)
        self.assertAlmostEqual(rosto.angulo, 36.87, places=1)

    def test_suavizar_tremida_e_pular_movimento(self):
        antes = Rosto(100, 100, 100, 0)
        tremida = suavizar(antes, Rosto(104, 100, 100, 10))
        self.assertEqual((tremida.x, tremida.angulo), (102, 5))
        longe = Rosto(100 + 100 * SALTO + 1, 100, 100, 0)
        self.assertEqual(suavizar(antes, longe), longe)
        self.assertEqual(suavizar(None, longe), longe)


class TestMemoria(unittest.TestCase):
    def test_rosto_sumido_continua_coberto_por_um_tempo(self):
        memoria, rosto = Memoria(duracao=0.5), Rosto(10, 10, 20, 0)
        self.assertEqual(memoria.atualizar([rosto], 0.0), [rosto])
        self.assertEqual(memoria.atualizar([], 0.4), [rosto])
        self.assertEqual(memoria.atualizar([], 0.6), [])
        self.assertEqual(memoria.atualizar([], 0.7), [])

    def test_um_rosto_so_e_suavizado(self):
        memoria = Memoria()
        memoria.atualizar([Rosto(100, 100, 100, 0)], 0.0)
        self.assertEqual(memoria.atualizar([Rosto(104, 100, 100, 0)], 0.1)[0].x, 102)

    def test_varios_rostos_vao_como_vieram(self):
        memoria = Memoria()
        memoria.atualizar([Rosto(100, 100, 100, 0)], 0.0)
        dois = [Rosto(104, 100, 100, 0), Rosto(300, 100, 100, 0)]
        self.assertEqual(memoria.atualizar(dois, 0.1), dois)


class TestDetector(unittest.TestCase):
    def test_detector_em_modo_video_com_tempo_crescente(self):
        detector_mp = mock.Mock()
        detector_mp.detect_for_video.return_value = SimpleNamespace(detections=[deteccao()])
        vision = mock.MagicMock()
        vision.FaceDetector.create_from_options.return_value = detector_mp
        detector = DetectorDeRosto(mock.MagicMock(), mock.MagicMock(), vision, "rosto.tflite")

        quadro = mock.MagicMock(shape=(480, 640, 3))
        rostos = detector.detectar(quadro, 1.0)
        detector.detectar(quadro, 1.0)  # mesmo instante: o MediaPipe recusaria
        self.assertEqual(rostos[0].x, 140)
        instantes = [chamada.args[1] for chamada in detector_mp.detect_for_video.call_args_list]
        self.assertEqual(instantes, [1000, 1001])
        detector.fechar()
        detector_mp.close.assert_called_once_with()


@unittest.skipUnless(TEM_OPENCV, "precisa de OpenCV e numpy")
class TestDesenho(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy

        self.cv2, self.numpy = cv2, numpy
        # Um personagem de 4x4: metade de cima opaca e vermelha, a de baixo transparente.
        self.png = numpy.zeros((4, 4, 4), numpy.uint8)
        self.png[:2] = (0, 0, 255, 255)

    def imagem(self):
        return self.numpy.full((100, 100, 3), 200, self.numpy.uint8)

    def test_cobre_onde_e_opaco_e_deixa_onde_e_transparente(self):
        imagem = self.imagem()
        mascara.sobrepor(self.cv2, self.numpy, imagem, self.png, Rosto(50, 50, 40, 0))
        self.assertEqual(tuple(imagem[35, 50]), (0, 0, 255))  # metade de cima
        self.assertEqual(tuple(imagem[65, 50]), (200, 200, 200))  # metade de baixo
        self.assertEqual(tuple(imagem[5, 5]), (200, 200, 200))  # fora

    def test_rosto_na_borda_e_cortado_sem_quebrar(self):
        imagem = self.imagem()
        mascara.sobrepor(self.cv2, self.numpy, imagem, self.png, Rosto(2, 2, 40, 0))
        self.assertEqual(tuple(imagem[0, 0]), (0, 0, 255))

    def test_rosto_fora_do_quadro_nao_desenha(self):
        imagem = self.imagem()
        mascara.sobrepor(self.cv2, self.numpy, imagem, self.png, Rosto(500, 500, 40, 0))
        self.assertTrue((imagem == 200).all())

    def test_girar_meia_volta_poe_o_opaco_embaixo(self):
        imagem = self.imagem()
        mascara.sobrepor(self.cv2, self.numpy, imagem, self.png, Rosto(50, 50, 40, 180))
        self.assertEqual(tuple(imagem[65, 50]), (0, 0, 255))

    def test_mascara_com_personagem_de_verdade(self):
        detector = mock.Mock(detectar=lambda rgb, agora: [Rosto(50, 50, 60, 0)])
        cobertura = Mascara(self.cv2, self.numpy, detector)
        imagem = cobertura.aplicar(self.imagem(), "panda", 0.0)
        self.assertFalse((imagem == 200).all())
        self.assertIs(cobertura._figura("panda"), cobertura._figura("panda"))  # carregada uma vez
        cobertura.fechar()
        detector.fechar.assert_called_once_with()

    def test_sem_personagem_nao_mexe(self):
        detector = mock.Mock()
        imagem = self.imagem()
        self.assertIs(Mascara(self.cv2, self.numpy, detector).aplicar(imagem, None, 0.0), imagem)
        detector.detectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
