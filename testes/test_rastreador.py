"""Rosto e corpo para o avatar 3D, com o MediaPipe trocado por falsos."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from autodoc.gestos import GestosIndisponiveis, rastreador
from autodoc.gestos.rastreador import AUSENCIA, Rastreador, abrir_rastreador
from testes.test_pose_avatar import corpo


class Matriz(list):
    """Uma matriz que, como a do numpy, sabe virar lista."""

    def tolist(self):
        return [list(linha) for linha in self]


def resultado_do_rosto(com_rosto=True):
    if not com_rosto:
        return SimpleNamespace(face_blendshapes=[], facial_transformation_matrixes=[])
    nomes = [SimpleNamespace(category_name="jawOpen", score=0.55)]
    return SimpleNamespace(face_blendshapes=[nomes], facial_transformation_matrixes=[Matriz([[1, 0, 0], [0, 1, 0], [0, 0, 1]])])


class TestRastreador(unittest.TestCase):
    def montar(self, rostos, corpos):
        self.rosto = mock.Mock(detect_for_video=mock.Mock(side_effect=rostos))
        self.corpo = mock.Mock(detect_for_video=mock.Mock(side_effect=corpos))
        vision = mock.MagicMock()
        vision.FaceLandmarker.create_from_options.return_value = self.rosto
        vision.PoseLandmarker.create_from_options.return_value = self.corpo
        return Rastreador(mock.MagicMock(), mock.MagicMock(), vision, "rosto.task", "corpo.task")

    def test_pose_com_rosto_e_corpo(self):
        alguem = self.montar([resultado_do_rosto()], [SimpleNamespace(pose_world_landmarks=[corpo()])])
        pose = alguem.calcular("rgb", [], 1.0)
        self.assertTrue(pose["presente"])
        self.assertEqual(pose["expressoes"]["boca"], 1.0)
        self.assertNotEqual(pose["bracos"]["direito"]["pulso"], [0.27, -0.13, 0.14])

    def test_ninguem_por_mais_de_um_segundo(self):
        vazio = SimpleNamespace(pose_world_landmarks=[])
        alguem = self.montar([resultado_do_rosto(), resultado_do_rosto(False), resultado_do_rosto(False)], [vazio] * 3)
        self.assertTrue(alguem.calcular("rgb", [], 0.0)["presente"])
        self.assertTrue(alguem.calcular("rgb", [], AUSENCIA - 0.1)["presente"])
        self.assertFalse(alguem.calcular("rgb", [], AUSENCIA + 0.1)["presente"])

    def test_tempo_sempre_crescente_e_fechar(self):
        alguem = self.montar([resultado_do_rosto(False)] * 2, [SimpleNamespace(pose_world_landmarks=[])] * 2)
        alguem.calcular("rgb", [], 1.0)
        alguem.calcular("rgb", [], 1.0)
        self.assertEqual([c.args[1] for c in self.rosto.detect_for_video.call_args_list], [1000, 1001])
        alguem.fechar()
        self.rosto.close.assert_called_once_with()
        self.corpo.close.assert_called_once_with()

    def test_matriz_que_ja_e_lista(self):
        rosto = resultado_do_rosto()
        rosto.facial_transformation_matrixes = [[[1, 0, 0], [0, 1, 0], [0, 0, 1]]]
        alguem = self.montar([rosto], [SimpleNamespace(pose_world_landmarks=[])])
        self.assertEqual(alguem.calcular("rgb", [], 0.0)["cabeca"]["rotacao"], [0.0, 0.0, 0.0, 1.0])


class TestAbrir(unittest.TestCase):
    def test_baixa_os_dois_modelos(self):
        vision = mock.MagicMock()
        with mock.patch.object(rastreador, "obter_modelo", side_effect=lambda destino, url, descricao: destino) as obter:
            self.assertIsInstance(abrir_rastreador(mock.MagicMock(), mock.MagicMock(), vision), Rastreador)
        urls = [chamada.args[1] for chamada in obter.call_args_list]
        self.assertEqual(urls, [rastreador.URL_ROSTO, rastreador.URL_CORPO])
        self.assertTrue(all(isinstance(chamada.args[0], Path) for chamada in obter.call_args_list))

    def test_sem_os_modelos_fica_sem_avatar(self):
        with (
            mock.patch.object(rastreador, "obter_modelo", side_effect=GestosIndisponiveis("sem internet")),
            self.assertLogs("autodoc.gestos.rastreador", "WARNING"),
        ):
            self.assertIsNone(abrir_rastreador(None, None, None))


if __name__ == "__main__":
    unittest.main()
