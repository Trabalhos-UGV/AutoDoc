"""O Tetris: pecas, tabuleiro e regras, sem camera e sem tela."""

from __future__ import annotations

import unittest

from autodoc.gestos import tetris
from autodoc.gestos.tetris import ROTACOES, TIPOS, Peca, kicks


def desenho(celulas) -> list[str]:
    """As celulas numa grade minima, para comparar formas de olho."""
    linhas = [l for l, _ in celulas]
    colunas = [c for _, c in celulas]
    grade = [["." for _ in range(min(colunas), max(colunas) + 1)] for _ in range(min(linhas), max(linhas) + 1)]
    for l, c in celulas:
        grade[l - min(linhas)][c - min(colunas)] = "#"
    return ["".join(linha) for linha in grade]


class TestPecas(unittest.TestCase):
    def test_sete_pecas_de_quatro_celulas(self):
        self.assertEqual(TIPOS, ("I", "O", "T", "S", "Z", "J", "L"))
        for tipo in TIPOS:
            for rotacao in ROTACOES[tipo]:
                self.assertEqual(len(set(rotacao)), 4, tipo)

    def test_t_gira_no_sentido_horario(self):
        self.assertEqual(desenho(ROTACOES["T"][0]), [".#.", "###"])
        self.assertEqual(desenho(ROTACOES["T"][1]), ["#.", "##", "#."])
        self.assertEqual(desenho(ROTACOES["T"][2]), ["###", ".#."])
        self.assertEqual(desenho(ROTACOES["T"][3]), [".#", "##", ".#"])

    def test_i_gira_dentro_da_caixa_4x4(self):
        # As posicoes do SRS: linha 1, coluna 2, linha 2, coluna 1.
        self.assertEqual({l for l, _ in ROTACOES["I"][0]}, {1})
        self.assertEqual({c for _, c in ROTACOES["I"][1]}, {2})
        self.assertEqual({l for l, _ in ROTACOES["I"][2]}, {2})
        self.assertEqual({c for _, c in ROTACOES["I"][3]}, {1})

    def test_o_nao_muda_ao_girar(self):
        self.assertEqual(len(set(ROTACOES["O"])), 1)
        self.assertEqual(kicks("O", 0, 1), ((0, 0),))

    def test_quatro_giros_voltam_ao_inicio(self):
        for tipo in TIPOS:
            peca = Peca(tipo)
            self.assertEqual(peca.girada().girada().girada().girada(), peca)
            self.assertEqual(peca.girada(-1), peca.girada().girada().girada())


class TestKicks(unittest.TestCase):
    def test_tabela_convertida_para_linha_e_coluna(self):
        # Oficial, 0 -> direita para JLSTZ: (0,0) (-1,0) (-1,+1) (0,-2) (-1,-2), y para cima.
        self.assertEqual(kicks("T", 0, 1), ((0, 0), (0, -1), (-1, -1), (2, 0), (2, -1)))
        # Oficial, 0 -> direita para I: (0,0) (-2,0) (+1,0) (-2,-1) (+1,+2).
        self.assertEqual(kicks("I", 0, 1), ((0, 0), (0, -2), (0, 1), (1, -2), (-2, 1)))

    def test_todas_as_transicoes_tem_cinco_tentativas(self):
        for tipo in ("I", "T", "S", "Z", "J", "L"):
            for de in range(4):
                for sentido in (1, -1):
                    tentativas = kicks(tipo, de, (de + sentido) % 4)
                    self.assertEqual(len(tentativas), 5)
                    self.assertEqual(tentativas[0], (0, 0))

    def test_ida_e_volta_sao_opostas(self):
        for tabela in (tetris._KICKS_I, tetris._KICKS_JLSTZ):
            for (de, para), deslocamentos in tabela.items():
                volta = tabela[(para, de)]
                self.assertEqual([(-x, -y) for x, y in deslocamentos], list(volta))

    def test_tentativas_de_giro_em_ordem(self):
        peca = Peca("T", linha=5, coluna=4)
        tentativas = list(peca.tentativas_de_giro())
        self.assertEqual(tentativas[0], Peca("T", 1, 5, 4))
        self.assertEqual(tentativas[1], Peca("T", 1, 5, 3))
        self.assertEqual(len(tentativas), 5)

    def test_celulas_somam_a_posicao(self):
        self.assertEqual(Peca("O", linha=3, coluna=4).celulas, ((3, 5), (3, 6), (4, 5), (4, 6)))
        self.assertEqual(Peca("O").movida(1, -1), Peca("O", linha=1, coluna=-1))


if __name__ == "__main__":
    unittest.main()
