"""O Tetris: pecas, tabuleiro e regras, sem camera e sem tela."""

from __future__ import annotations

import random
import unittest

from autodoc.gestos import tetris
from autodoc.gestos.tetris import ROTACOES, TIPOS, Jogo, Peca, Saco, Tabuleiro, intervalo_de_queda, kicks


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


def jogo_com(peca: Peca, *desenhadas: str) -> Jogo:
    """Uma partida com a peca e o fundo do tabuleiro escolhidos a dedo."""
    jogo = Jogo(semente=1)
    jogo.tabuleiro = montar_tabuleiro(*desenhadas)
    jogo.peca = peca
    jogo._mais_baixa = peca.linha
    jogo.tirar_eventos()
    return jogo


def avancar(jogo: Jogo, ate: float, desde: float = 0.0, quadros_por_segundo: int = 60) -> None:
    """O relogio andando como no jogo de verdade: um quadro de cada vez."""
    quadros = round((ate - desde) * quadros_por_segundo)
    for quadro in range(quadros + 1):
        jogo.atualizar(desde + quadro / quadros_por_segundo)


def tipos_dos_eventos(jogo: Jogo) -> list[str]:
    return [evento["tipo"] for evento in jogo.tirar_eventos()]


class TestSorteio(unittest.TestCase):
    def test_cada_saco_tem_as_sete(self):
        saco = Saco(random.Random(3))
        for _ in range(3):
            self.assertEqual(sorted(saco.tirar() for _ in range(7)), sorted(TIPOS))

    def test_espiar_nao_tira(self):
        saco = Saco(random.Random(3))
        proximas = saco.espiar(10)
        self.assertEqual([saco.tirar() for _ in range(10)], proximas)

    def test_mesma_semente_mesma_partida(self):
        self.assertEqual(Jogo(semente=7).saco.espiar(14), Jogo(semente=7).saco.espiar(14))


class TestGravidade(unittest.TestCase):
    def test_curva(self):
        self.assertAlmostEqual(intervalo_de_queda(1), 1.25)
        self.assertLess(intervalo_de_queda(5), intervalo_de_queda(4))
        self.assertEqual(intervalo_de_queda(40), tetris.QUEDA_MINIMA)

    def test_peca_nasce_centralizada_aparecendo_no_topo(self):
        jogo = Jogo(semente=1)
        jogo.recomecar()
        largura = tetris.FORMAS[jogo.peca.tipo][0]
        self.assertEqual(jogo.peca.coluna, (10 - largura) // 2)
        self.assertEqual(jogo.peca.linha, 1)

    def test_desce_uma_linha_por_intervalo(self):
        jogo = jogo_com(Peca("T", linha=5, coluna=3))
        avancar(jogo, 1.2)
        self.assertEqual(jogo.peca.linha, 5)
        avancar(jogo, 1.3, desde=1.2)
        self.assertEqual(jogo.peca.linha, 6)
        avancar(jogo, 3.8, desde=1.3)
        self.assertEqual(jogo.peca.linha, 8)

    def test_janela_travada_nao_faz_a_peca_despencar(self):
        jogo = jogo_com(Peca("T", linha=5, coluna=3))
        jogo.nivel = 10  # 0,08 s por linha
        jogo.atualizar(0.0)
        jogo.atualizar(30.0)
        self.assertLessEqual(jogo.peca.linha, 5 + int(tetris.PASSO_MAXIMO / jogo.intervalo()))

    def test_descida_rapida_conta_ponto(self):
        jogo = jogo_com(Peca("T", linha=5, coluna=3))
        jogo.descer_rapido(True)
        avancar(jogo, 0.25)  # 0,0625 s por linha
        self.assertEqual(jogo.peca.linha, 9)
        self.assertEqual(jogo.pontos, 4)
        jogo.descer_rapido(False)
        self.assertAlmostEqual(jogo.intervalo(), 1.25)


class TestTrava(unittest.TestCase):
    def no_chao(self):
        jogo = jogo_com(Peca("O", linha=20, coluna=3))
        jogo.atualizar(0.0)
        return jogo

    def test_trava_depois_do_atraso(self):
        jogo = self.no_chao()
        avancar(jogo, 0.45)
        self.assertEqual(tipos_dos_eventos(jogo), [])
        avancar(jogo, 0.55, desde=0.45)
        self.assertEqual(tipos_dos_eventos(jogo), ["travou"])
        self.assertEqual(jogo.tabuleiro.celulas[21][4], "O")

    def test_mover_no_chao_reinicia_a_espera(self):
        jogo = self.no_chao()
        avancar(jogo, 0.4)
        jogo.mover(1)
        avancar(jogo, 0.8, desde=0.4)
        self.assertEqual(tipos_dos_eventos(jogo), [])

    def test_espera_nao_reinicia_para_sempre(self):
        jogo = self.no_chao()
        for i in range(tetris.MOVIMENTOS_NA_TRAVA + 1):
            jogo.mover(1 if i % 2 else -1)
            avancar(jogo, 0.3 * (i + 1), desde=0.3 * i)
        self.assertIn("travou", tipos_dos_eventos(jogo))

    def test_chegar_mais_baixo_devolve_os_movimentos(self):
        jogo = jogo_com(Peca("O", linha=10, coluna=3))
        jogo._movimentos_na_trava = tetris.MOVIMENTOS_NA_TRAVA
        jogo._descer()
        self.assertEqual(jogo._movimentos_na_trava, 0)

    def test_peca_que_deixa_o_chao_zera_a_espera(self):
        jogo = jogo_com(Peca("O", linha=19, coluna=-1), "##........")  # apoiada no degrau
        avancar(jogo, 0.3)
        self.assertGreater(jogo._trava, 0)
        jogo.mover(2)  # saiu de cima do degrau: pode cair de novo
        avancar(jogo, 0.32, desde=0.3)
        self.assertEqual(jogo._trava, 0.0)


class TestComandos(unittest.TestCase):
    def test_parede_barra_o_movimento(self):
        jogo = jogo_com(Peca("O", linha=5, coluna=-1))
        self.assertFalse(jogo.mover(-1))
        self.assertTrue(jogo.mover(1))

    def test_kick_tira_a_peca_da_parede(self):
        # T apontando para a direita, encostada na parede esquerda: girar a
        # deixaria uma coluna para fora, e o segundo kick (x+1) resolve.
        jogo = jogo_com(Peca("T", rotacao=1, linha=5, coluna=-1))
        self.assertTrue(jogo.girar())
        self.assertEqual((jogo.peca.rotacao, jogo.peca.coluna), (2, 0))
        self.assertEqual(tipos_dos_eventos(jogo), ["girou"])

    def test_vale_a_primeira_tentativa_que_cabe(self):
        jogo = jogo_com(Peca("T", linha=5, coluna=3))
        quarta = list(jogo.peca.tentativas_de_giro())[3]
        jogo.tabuleiro.cabe = lambda peca: peca == quarta or peca == jogo.peca
        self.assertTrue(jogo.girar())
        self.assertEqual(jogo.peca, quarta)

    def test_giro_impossivel(self):
        jogo = jogo_com(Peca("I", linha=5, coluna=3))
        jogo.tabuleiro.cabe = lambda peca: peca.rotacao == 0
        self.assertFalse(jogo.girar())
        self.assertEqual(tipos_dos_eventos(jogo), [])

    def test_despencar(self):
        jogo = jogo_com(Peca("O", linha=2, coluna=3))
        jogo.despencar()
        self.assertEqual(jogo.pontos, 2 * 18)
        self.assertEqual(tipos_dos_eventos(jogo), ["despencou", "travou"])
        self.assertEqual(jogo.tabuleiro.celulas[21][4], "O")
        self.assertEqual(jogo.peca.linha, 1)  # a proxima ja nasceu

    def test_tirar_eventos_esvazia(self):
        jogo = jogo_com(Peca("O", linha=2, coluna=3))
        jogo.girar()
        self.assertEqual(len(jogo.tirar_eventos()), 1)
        self.assertEqual(jogo.tirar_eventos(), [])


class TestPontos(unittest.TestCase):
    def test_tabela_por_linhas(self):
        for quantas, pontos in ((1, 100), (2, 300), (3, 500), (4, 800)):
            fundo = ["#########."] * quantas
            jogo = jogo_com(Peca("I", rotacao=1, linha=18, coluna=7), *fundo)
            jogo.despencar()
            self.assertEqual(jogo.pontos, pontos, quantas)  # a I ja estava no chao
            self.assertEqual(jogo.linhas, quantas)

    def test_pontos_multiplicam_pelo_nivel(self):
        jogo = jogo_com(Peca("I", rotacao=1, linha=18, coluna=7), *["#########."] * 4)
        jogo.nivel = 3
        jogo.despencar()
        self.assertEqual(jogo.pontos, 2400)

    def test_eventos_das_linhas_na_numeracao_da_tela(self):
        jogo = jogo_com(Peca("I", rotacao=1, linha=18, coluna=7), "#########.", "#########.")
        jogo.despencar()
        linhas = [e for e in jogo.tirar_eventos() if e["tipo"] == "linhas"]
        self.assertEqual(linhas, [{"tipo": "linhas", "linhas": [18, 19]}])

    def test_sobe_de_nivel_a_cada_dez_linhas(self):
        jogo = jogo_com(Peca("I", rotacao=1, linha=18, coluna=7), "#########.")
        jogo.linhas = 9
        jogo.despencar()
        self.assertEqual(jogo.nivel, 2)
        self.assertIn({"tipo": "subiu_nivel", "nivel": 2}, jogo.tirar_eventos())


class TestFimEPausa(unittest.TestCase):
    def test_fim_quando_a_peca_nova_nao_cabe(self):
        jogo = jogo_com(Peca("O", linha=10, coluna=3))
        for linha in range(4):
            # Uma falha na ponta, senao a linha estaria completa e sumiria.
            jogo.tabuleiro.celulas[linha] = ["Z"] * 9 + [None]
        jogo.despencar()
        self.assertEqual(jogo.situacao, "fim")
        self.assertEqual(tipos_dos_eventos(jogo)[-1], "fim")

    def test_fim_quando_trava_toda_escondida(self):
        jogo = jogo_com(Peca("O", linha=0, coluna=0), *[".##......."] * 20)
        jogo.despencar()
        self.assertEqual(jogo.situacao, "fim")

    def test_sem_comandos_depois_do_fim(self):
        jogo = jogo_com(Peca("O", linha=5, coluna=3))
        jogo.situacao = "fim"
        self.assertFalse(jogo.mover(1))
        self.assertFalse(jogo.girar())
        jogo.despencar()
        jogo.pausar(True)
        self.assertEqual((jogo.situacao, jogo.pontos), ("fim", 0))

    def test_pausa_congela_o_tempo(self):
        jogo = jogo_com(Peca("T", linha=5, coluna=3))
        jogo.atualizar(0.0)
        jogo.pausar(True)
        jogo.pausar(True)
        for segundo in range(1, 10):
            jogo.atualizar(segundo)
        jogo.pausar(False)
        self.assertEqual(jogo.peca.linha, 5)
        self.assertEqual(tipos_dos_eventos(jogo), ["pausado", "jogando"])

    def test_recomecar_zera(self):
        jogo = jogo_com(Peca("O", linha=5, coluna=3))
        jogo.pontos, jogo.situacao = 900, "fim"
        jogo.recomecar()
        self.assertEqual((jogo.pontos, jogo.situacao, jogo.nivel), (0, "jogando", 1))


if __name__ == "__main__":
    unittest.main()
