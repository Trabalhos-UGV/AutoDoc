"""O Tetris: pecas, tabuleiro e regras, sem camera e sem tela."""

from __future__ import annotations

import unittest

from autodoc.gestos import tetris
from autodoc.gestos.tetris import ROTACOES, TIPOS, Peca, Tabuleiro, kicks


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


def montar_tabuleiro(*desenhadas: str) -> Tabuleiro:
    """Um tabuleiro com as linhas dadas embaixo; `#` e ocupado, `.` e livre."""
    tabuleiro = Tabuleiro()
    for deslocamento, texto in enumerate(reversed(desenhadas)):
        linha = tabuleiro.altura - 1 - deslocamento
        tabuleiro.celulas[linha] = [None if marca == "." else "Z" for marca in texto]
    return tabuleiro


def linhas_de_baixo(tabuleiro: Tabuleiro, quantas: int) -> list[str]:
    return ["".join("." if c is None else "#" for c in linha) for linha in tabuleiro.celulas[-quantas:]]


class TestTabuleiro(unittest.TestCase):
    def test_tamanho_oficial_com_duas_linhas_escondidas(self):
        tabuleiro = Tabuleiro()
        self.assertEqual((tabuleiro.largura, tabuleiro.altura), (10, 22))

    def test_paredes_chao_e_ceu(self):
        tabuleiro = Tabuleiro()
        self.assertFalse(tabuleiro.livre(5, -1))
        self.assertFalse(tabuleiro.livre(5, 10))
        self.assertFalse(tabuleiro.livre(22, 5))
        self.assertTrue(tabuleiro.livre(-2, 5))  # acima: livre, para o kick poder levantar

    def test_cabe(self):
        tabuleiro = montar_tabuleiro("#.........")
        self.assertTrue(tabuleiro.cabe(Peca("O", linha=19, coluna=0)))
        self.assertFalse(tabuleiro.cabe(Peca("O", linha=20, coluna=-1)))
        self.assertFalse(tabuleiro.cabe(Peca("O", linha=20, coluna=8)))

    def test_fixar_sem_completar(self):
        tabuleiro = Tabuleiro()
        self.assertEqual(tabuleiro.fixar(Peca("O", linha=20, coluna=0)), [])
        self.assertEqual(linhas_de_baixo(tabuleiro, 2), [".##.......", ".##......."])
        self.assertEqual(tabuleiro.celulas[21][1], "O")

    def test_linha_completa_some_e_o_resto_desce(self):
        tabuleiro = montar_tabuleiro("#.........", "########..")
        self.assertEqual(tabuleiro.fixar(Peca("O", linha=20, coluna=7)), [21])
        self.assertEqual(linhas_de_baixo(tabuleiro, 2), ["..........", "#.......##"])

    def test_quatro_linhas_de_uma_vez(self):
        tabuleiro = montar_tabuleiro(*["#########."] * 4)
        self.assertEqual(tabuleiro.fixar(Peca("I", rotacao=1, linha=18, coluna=7)), [18, 19, 20, 21])
        self.assertEqual(linhas_de_baixo(tabuleiro, 4), [".........."] * 4)

    def test_linhas_separadas(self):
        tabuleiro = montar_tabuleiro("#########.", "#.#######.", "#########.")
        self.assertEqual(tabuleiro.fixar(Peca("I", rotacao=1, linha=18, coluna=7)), [19, 21])
        # Sobra a ponta da I nas duas linhas que nao completaram.
        self.assertEqual(linhas_de_baixo(tabuleiro, 2), [".........#", "#.########"])

    def test_celula_acima_do_tabuleiro_nao_e_gravada(self):
        tabuleiro = Tabuleiro()
        tabuleiro.fixar(Peca("I", rotacao=1, linha=-2, coluna=0))
        self.assertEqual(sum(c is not None for linha in tabuleiro.celulas for c in linha), 2)


if __name__ == "__main__":
    unittest.main()
