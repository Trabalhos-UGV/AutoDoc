"""Da pessoa na camera a pose do personagem 3D, com dados sinteticos."""

from __future__ import annotations

import json
import math
import unittest
from types import SimpleNamespace

from autodoc.gestos import pose_avatar
from autodoc.gestos.pose_avatar import (
    OMBROS,
    PALMO,
    PoseDoAvatar,
    angulos_da_matriz,
    braco,
    expressoes,
    mao,
    mao_em_repouso,
    para_o_avatar,
    quaternion,
)


def p(x, y, z, visibilidade=1.0):
    return SimpleNamespace(x=x, y=y, z=z, visibility=visibilidade)


def girar_z(graus):
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def girar_y(graus):
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def girar_x(graus):
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def vezes(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def matriz_do_quaternion(x, y, z, w):
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def espelhar(r):
    sinais = (-1, 1, 1)
    return [[sinais[i] * sinais[j] * r[i][j] for j in range(3)] for i in range(3)]


def corpo(braco_direito_para_cima=False, cotovelo_visivel=1.0):
    """Os 33 pontos do corpo: ombros 0,4 m afastados, bracos para baixo.

    Na imagem crua da camera: o ombro direito da pessoa fica a ESQUERDA da
    imagem (x menor), y cresce para baixo, z cresce para longe.
    """
    pontos = [p(0, 0, 0) for _ in range(33)]
    pontos[12], pontos[11] = p(-0.2, -0.5, 0), p(0.2, -0.5, 0)  # ombros direito e esquerdo
    pontos[14], pontos[13] = p(-0.22, -0.25, 0, cotovelo_visivel), p(0.22, -0.25, 0)
    pontos[16], pontos[15] = p(-0.22, 0.0, -0.1), p(0.22, 0.0, -0.1)
    if braco_direito_para_cima:
        pontos[14], pontos[16] = p(-0.35, -0.65, 0), p(-0.35, -0.9, -0.05)
    return pontos


def mao_real(palmo=0.09):
    """21 pontos de mao de mundo: pulso na origem, dedos para cima (y negativo na camera)."""
    pontos = [p(0, 0, 0) for _ in range(21)]
    for i in range(1, 21):
        pontos[i] = p(0.01 * (i % 5), -palmo * (0.5 + i / 20), 0)
    pontos[9] = p(0, -palmo, 0)
    return pontos


ROSTO_NEUTRO = ({"eyeBlinkLeft": 0.05, "eyeBlinkRight": 0.05, "jawOpen": 0.0}, girar_z(0))


class TestConversoes(unittest.TestCase):
    def test_espelho_e_eixos_do_avatar(self):
        self.assertEqual(para_o_avatar(p(0.1, 0.2, 0.3)), (-0.1, -0.2, -0.3))

    def test_expressoes_reescaladas_da_faixa_real(self):
        cara = expressoes({"eyeBlinkLeft": 0.05, "eyeBlinkRight": 0.7, "jawOpen": 0.3, "mouthSmileLeft": 0.6, "mouthSmileRight": 0.6})
        self.assertEqual(cara["piscar_esquerdo"], 0.0)  # olho aberto ja da 0,05
        self.assertEqual(cara["piscar_direito"], 1.0)
        self.assertAlmostEqual(cara["boca"], 0.5)
        self.assertEqual(cara["sorriso"], 1.0)
        self.assertEqual(cara["sobrancelhas"], 0.0)

    def test_sobrancelha_vem_da_maior(self):
        self.assertEqual(expressoes({"browOuterUpLeft": 0.6, "browOuterUpRight": 0.6})["sobrancelhas"], 1.0)


class TestCabeca(unittest.TestCase):
    def test_de_frente(self):
        self.assertEqual(angulos_da_matriz(girar_z(0)), (0.0, 0.0, 0.0))
        self.assertEqual(quaternion(0, 0, 0), [0.0, 0.0, 0.0, 1.0])

    def test_o_espelho_troca_inclinar_e_virar_mas_nao_olhar_para_cima(self):
        self.assertAlmostEqual(angulos_da_matriz(girar_z(20))[2], -20)
        self.assertAlmostEqual(angulos_da_matriz(girar_y(30))[0], -30)
        self.assertAlmostEqual(angulos_da_matriz(girar_x(15))[1], 15)

    def test_decompor_e_recompor_da_a_mesma_rotacao_espelhada(self):
        """Cabeca virada, inclinada e olhando para cima ao mesmo tempo."""
        real = vezes(girar_y(25), vezes(girar_x(-15), girar_z(20)))
        recomposta = matriz_do_quaternion(*quaternion(*angulos_da_matriz(real)))
        esperada = espelhar(real)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(recomposta[i][j], esperada[i][j], places=6)

    def test_o_pescoco_tem_limite(self):
        limitado = quaternion(90, 0, 0)
        self.assertAlmostEqual(limitado[1], math.sin(math.radians(pose_avatar.LIMITE_GUINADA) / 2))


class TestBracoEMao(unittest.TestCase):
    def test_braco_com_a_direcao_da_pessoa_e_o_tamanho_do_boneco(self):
        direito = braco(corpo(), "direito")
        self.assertEqual(direito["ombro"], OMBROS["direito"])
        self.assertAlmostEqual(math.dist(direito["ombro"], direito["cotovelo"]), pose_avatar.BRACO)
        self.assertAlmostEqual(math.dist(direito["cotovelo"], direito["pulso"]), pose_avatar.ANTEBRACO)
        # O cotovelo da pessoa fica abaixo e um pouco para fora do ombro.
        self.assertLess(direito["cotovelo"][1], direito["ombro"][1])
        self.assertGreater(direito["cotovelo"][0], direito["ombro"][0])
        # O pulso vem para perto da camera: no avatar, para fora da tela.
        self.assertGreater(direito["pulso"][2], 0)

    def test_ombros_medidos_errado_nao_esticam_o_braco(self):
        """Na foto de teste o MediaPipe pos os ombros a 4 cm um do outro."""
        juntos = corpo()
        juntos[11] = p(-0.16, -0.5, 0)
        direito = braco(juntos, "direito")
        self.assertAlmostEqual(math.dist(direito["ombro"], direito["pulso"]), pose_avatar.BRACO + pose_avatar.ANTEBRACO, places=1)

    def test_braco_sem_tamanho_nao_vira_pose(self):
        dobrado = corpo()
        dobrado[14] = dobrado[12]
        self.assertIsNone(braco(dobrado, "direito"))

    def test_braco_levantado_vai_para_cima(self):
        self.assertGreater(braco(corpo(braco_direito_para_cima=True), "direito")["pulso"][1], 0.6)

    def test_braco_que_nao_aparece(self):
        self.assertIsNone(braco(corpo(cotovelo_visivel=0.2), "direito"))
        self.assertIsNotNone(braco(corpo(cotovelo_visivel=0.2), "esquerdo"))

    def test_mao_vira_pata_de_tamanho_fixo_presa_no_pulso(self):
        for palmo in (0.07, 0.1):  # crianca e adulto
            pontos = mao(mao_real(palmo), (0.3, 0.1, 0.2))
            self.assertEqual(pontos[0], (0.3, 0.1, 0.2))
            self.assertAlmostEqual(math.dist(pontos[0], pontos[9]), PALMO)
            self.assertGreater(pontos[9][1], pontos[0][1])  # dedos para cima

    def test_mao_em_repouso_e_espelhada(self):
        esquerda = mao_em_repouso("esquerda", (0, 0, 0))
        direita = mao_em_repouso("direita", (0, 0, 0))
        self.assertEqual(esquerda[4][0], -direita[4][0])
        self.assertLess(esquerda[12][1], 0)  # pendurada


class TestPoseCompleta(unittest.TestCase):
    def test_tudo_visto(self):
        pose = PoseDoAvatar().atualizar(ROSTO_NEUTRO, corpo(), [("Right", mao_real())], 0.0)
        self.assertEqual(set(pose), {"cabeca", "expressoes", "bracos", "maos"})
        self.assertEqual(len(pose["maos"]["direita"]), 21)
        self.assertEqual(pose["maos"]["direita"][0], pose["bracos"]["direito"]["pulso"])
        self.assertEqual(json.loads(json.dumps(pose)), pose)

    def test_sem_ninguem_e_a_pose_de_descanso(self):
        pose = PoseDoAvatar().atualizar(None, None, [], 0.0)
        self.assertEqual(pose["cabeca"]["rotacao"], [0.0, 0.0, 0.0, 1.0])
        self.assertEqual(pose["bracos"]["esquerdo"]["pulso"], list(pose_avatar.BRACO_EM_REPOUSO["esquerdo"]["pulso"]))
        self.assertAlmostEqual(pose["expressoes"]["sorriso"], 0.25)

    def test_parte_perdida_fica_meio_segundo_e_volta_aos_poucos(self):
        avatar = PoseDoAvatar()
        levantado = avatar.atualizar(None, corpo(braco_direito_para_cima=True), [], 0.0)["bracos"]["direito"]["pulso"]
        lembrado = avatar.atualizar(None, None, [], 0.4)["bracos"]["direito"]["pulso"]
        self.assertEqual(lembrado, levantado)
        voltando = avatar.atualizar(None, None, [], 0.6)["bracos"]["direito"]["pulso"]
        repouso = list(pose_avatar.BRACO_EM_REPOUSO["direito"]["pulso"])
        # Nem mais onde estava, nem ainda no repouso: no caminho.
        self.assertLess(voltando[1], levantado[1])
        self.assertGreater(voltando[1], repouso[1])
        for i in range(1, 60):
            final = avatar.atualizar(None, None, [], 0.6 + i / 30)["bracos"]["direito"]["pulso"]
        self.assertAlmostEqual(final[1], repouso[1], places=2)

    def test_mao_esquerda_da_pessoa_fica_a_esquerda_da_tela(self):
        pose = PoseDoAvatar().atualizar(None, corpo(), [("Left", mao_real())], 0.0)
        self.assertLess(pose["maos"]["esquerda"][0][0], 0)
        # A outra mao, sem dado, fica relaxada no proprio pulso.
        self.assertEqual(pose["maos"]["direita"][0], pose["bracos"]["direito"]["pulso"])


if __name__ == "__main__":
    unittest.main()
