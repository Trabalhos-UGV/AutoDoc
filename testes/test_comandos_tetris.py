"""Gestos e teclado virando comandos do Tetris.

As maos sao sinteticas (`apoio_gestos.montar_mao`) e o tempo anda um quadro de
cada vez, a 30 por segundo, como a camera de verdade.
"""

from __future__ import annotations

import unittest

from autodoc.gestos.comandos_tetris import (
    AREA_X,
    CONTAGEM_AO_VOLTAR,
    ESPERA_APOS_DESPENCAR,
    QUADROS_PUNHO,
    ColunaDaMao,
    Comandos,
    coluna_da_peca,
)
from autodoc.gestos.reconhecimento import Gesto, Mao
from autodoc.gestos.tetris import Jogo, Peca
from testes.apoio_gestos import montar_mao
from testes.test_tetris import jogo_com

QUADRO = 1 / 30


def x_da_coluna(coluna: float) -> float:
    """O x da palma que aponta para o meio da coluna."""
    esquerda, direita = AREA_X
    return esquerda + (coluna + 0.5) * (direita - esquerda) / 10


def mao(coluna: float = 4, **opcoes):
    """Uma mao com a palma apontando a coluna. A palma de `montar_mao` fica em x=0,5."""
    return montar_mao(x=x_da_coluna(coluna) - 0.5, **opcoes)


def alcancavel(colunas_da_peca, alvo: int) -> int:
    """A coluna mais perto do alvo que a peca consegue representar.

    Peca de largura 3 deitada nunca tem o meio na coluna 0 nem na 9: a borda
    para ela antes.
    """
    largura = len(set(colunas_da_peca))
    meio = (largura - 1) // 2
    return min(max(alvo, meio), 10 - largura + meio)


class TestColunaDaMao(unittest.TestCase):
    def firmar(self, coluna_da_mao: ColunaDaMao, x: float, desde: float = 0.0, quadros: int = 60) -> int:
        for i in range(quadros):
            resultado = coluna_da_mao.atualizar(x, desde + i * QUADRO)
        return resultado

    def test_cada_coluna_no_seu_lugar(self):
        for coluna in range(10):
            self.assertEqual(ColunaDaMao().atualizar(x_da_coluna(coluna), 0.0), coluna)

    def test_fora_da_area_fica_na_borda(self):
        self.assertEqual(ColunaDaMao().atualizar(0.0, 0.0), 0)
        self.assertEqual(ColunaDaMao().atualizar(1.0, 0.0), 9)

    def test_varrer_a_mao_passa_por_todas_as_colunas_em_ordem(self):
        coluna_da_mao, visitadas = ColunaDaMao(), []
        quadros = 90
        for i in range(quadros + 30):
            x = x_da_coluna(-0.5 + 10 * min(i, quadros) / quadros)
            coluna = coluna_da_mao.atualizar(x, i * QUADRO)
            if not visitadas or visitadas[-1] != coluna:
                visitadas.append(coluna)
        self.assertEqual(visitadas, list(range(10)))

    def test_magnetismo(self):
        coluna_da_mao = ColunaDaMao()
        self.assertEqual(self.firmar(coluna_da_mao, x_da_coluna(4)), 4)
        # Meio caminho para a 5 mais um pouco: ainda nao basta.
        self.assertEqual(self.firmar(coluna_da_mao, x_da_coluna(4.7), desde=2), 4)
        self.assertEqual(self.firmar(coluna_da_mao, x_da_coluna(4.9), desde=4), 5)
        # E para voltar tambem precisa passar da fronteira com folga.
        self.assertEqual(self.firmar(coluna_da_mao, x_da_coluna(4.3), desde=6), 5)
        self.assertEqual(self.firmar(coluna_da_mao, x_da_coluna(4.1), desde=8), 4)

    def test_reiniciar_esquece(self):
        coluna_da_mao = ColunaDaMao()
        self.firmar(coluna_da_mao, x_da_coluna(9))
        coluna_da_mao.reiniciar()
        self.assertEqual(coluna_da_mao.atualizar(x_da_coluna(0), 10.0), 0)


class Partida(unittest.TestCase):
    def setUp(self):
        self.agora = 0.0

    def preparar(self, peca: Peca, *fundo: str) -> None:
        self.jogo = jogo_com(peca, *fundo)
        self.comandos = Comandos(self.jogo)

    def quadros(self, gesto: Gesto, pontos=None, quantos: int = 1) -> None:
        for _ in range(quantos):
            self.agora += QUADRO
            self.comandos.aplicar(gesto, mao() if pontos is None else pontos, self.agora)


class TestMover(Partida):
    def test_a_peca_vai_ate_a_coluna_da_mao(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.assertEqual(coluna_da_peca(self.jogo), 4)
        self.quadros(Gesto.MOVER, mao(8))
        self.assertEqual(coluna_da_peca(self.jogo), 5)  # uma coluna por quadro
        self.quadros(Gesto.MOVER, mao(8), quantos=5)
        self.assertEqual(coluna_da_peca(self.jogo), 8)

    def test_bate_no_bloco_em_vez_de_atravessar(self):
        self.preparar(Peca("O", linha=18, coluna=3), *["......#..."] * 4)
        self.quadros(Gesto.MOVER, mao(9), quantos=10)
        self.assertEqual(coluna_da_peca(self.jogo), 4)

    def test_coluna_de_cada_forma(self):
        self.preparar(Peca("I", linha=5, coluna=3))
        self.assertEqual(coluna_da_peca(self.jogo), 4)
        self.jogo.peca = Peca("T", rotacao=1, linha=5, coluna=3)
        self.assertEqual(coluna_da_peca(self.jogo), 4)


class TestGirarEGuardar(Partida):
    def test_pinca_gira_uma_vez_por_entrada(self):
        self.preparar(Peca("T", linha=5, coluna=3))
        self.quadros(Gesto.MOVER)
        self.quadros(Gesto.PINCA_INDICADOR, mao(pinca="indicador"), quantos=10)
        self.assertEqual(self.jogo.peca.rotacao, 1)
        self.quadros(Gesto.MOVER)
        self.quadros(Gesto.PINCA_INDICADOR, mao(pinca="indicador"))
        self.assertEqual(self.jogo.peca.rotacao, 2)

    def test_girar_nao_tira_a_peca_da_coluna(self):
        self.preparar(Peca("T", linha=5, coluna=3))
        self.quadros(Gesto.MOVER, quantos=5)
        for _ in range(4):
            self.quadros(Gesto.PINCA_INDICADOR, mao(pinca="indicador"), quantos=3)
            self.quadros(Gesto.MOVER, quantos=3)
            self.assertEqual(coluna_da_peca(self.jogo), 4)

    def test_pinca_do_medio_guarda_uma_vez(self):
        self.preparar(Peca("T", linha=5, coluna=3))
        self.quadros(Gesto.PINCA_MEDIO, mao(pinca="medio"), quantos=5)
        self.assertEqual(self.jogo.guardada, "T")
        self.assertFalse(self.jogo.pode_guardar)


class TestDespencar(Partida):
    def test_punho_precisa_se_firmar(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.PUNHO, mao(abertos=()), quantos=QUADROS_PUNHO - 1)
        self.assertEqual(self.jogo.peca.linha, 5)
        self.quadros(Gesto.PUNHO, mao(abertos=()))
        self.assertEqual(self.jogo.tabuleiro.celulas[21][4], "O")

    def test_punho_segurado_despenca_uma_peca_so(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.PUNHO, mao(abertos=()), quantos=QUADROS_PUNHO * 5)
        ocupadas = sum(c is not None for linha in self.jogo.tabuleiro.celulas for c in linha)
        self.assertEqual(ocupadas, 4)

    def test_peca_nova_espera_antes_de_seguir_a_mao(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.PUNHO, mao(abertos=()), quantos=QUADROS_PUNHO)
        nascida = coluna_da_peca(self.jogo)
        self.quadros(Gesto.MOVER, mao(9), quantos=int(ESPERA_APOS_DESPENCAR / QUADRO) - 1)
        self.assertEqual(coluna_da_peca(self.jogo), nascida)
        self.quadros(Gesto.MOVER, mao(9), quantos=10)
        colunas = [c for _, c in self.jogo.peca.celulas]
        self.assertEqual(coluna_da_peca(self.jogo), alcancavel(colunas, 9))

    def test_mao_baixa_desce_rapido(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.MOVER, mao(y=0.2))
        self.assertTrue(self.jogo.descendo_rapido)
        self.quadros(Gesto.MOVER)
        self.assertFalse(self.jogo.descendo_rapido)
        self.quadros(Gesto.PINCA_INDICADOR, mao(y=0.2, pinca="indicador"))
        self.assertFalse(self.jogo.descendo_rapido)  # so com a mao aberta


class TestPausa(Partida):
    def test_mao_sumida_pausa_e_volta_com_contagem(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.MOVER)
        self.quadros(Gesto.NENHUM, None)
        self.assertEqual(self.jogo.situacao, "pausado")
        self.assertIsNone(self.comandos.contagem())

        self.quadros(Gesto.MOVER)
        self.assertEqual(self.jogo.situacao, "pausado")
        self.assertAlmostEqual(self.comandos.contagem(), CONTAGEM_AO_VOLTAR)
        self.quadros(Gesto.MOVER, quantos=int(CONTAGEM_AO_VOLTAR / QUADRO) + 1)
        self.assertEqual(self.jogo.situacao, "jogando")
        self.assertIsNone(self.comandos.contagem())

    def test_mao_que_some_de_novo_reinicia_a_contagem(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.NENHUM, None)
        self.quadros(Gesto.MOVER, quantos=10)
        self.quadros(Gesto.NENHUM, None)
        self.quadros(Gesto.MOVER, quantos=10)
        self.assertEqual(self.jogo.situacao, "pausado")

    def test_pausa_do_teclado_a_mao_nao_tira(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.comandos.tecla("p")
        self.quadros(Gesto.MOVER, mao(9), quantos=60)
        self.assertEqual(self.jogo.situacao, "pausado")
        self.assertEqual(coluna_da_peca(self.jogo), 4)
        self.comandos.tecla("P")
        self.assertEqual(self.jogo.situacao, "jogando")

    def test_teclado_tira_a_pausa_da_mao(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.quadros(Gesto.NENHUM, None)
        self.comandos.tecla("p")
        self.assertEqual(self.jogo.situacao, "jogando")

    def test_pinca_no_fim_recomeca(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.jogo.situacao = "fim"
        self.quadros(Gesto.NENHUM, None)
        self.quadros(Gesto.MOVER)
        self.assertEqual(self.jogo.situacao, "fim")
        self.quadros(Gesto.PINCA_INDICADOR, mao(pinca="indicador"))
        self.assertEqual((self.jogo.situacao, self.jogo.pontos), ("jogando", 0))


class TestTeclado(Partida):
    def test_cada_tecla(self):
        self.preparar(Peca("T", linha=5, coluna=3))
        for tecla, esperado in (
            ("ArrowLeft", lambda j: j.peca.coluna == 2),
            ("ArrowRight", lambda j: j.peca.coluna == 3),
            ("ArrowUp", lambda j: j.peca.rotacao == 1),
            ("z", lambda j: j.peca.rotacao == 0),
            ("x", lambda j: j.peca.rotacao == 1),
            ("ArrowDown", lambda j: j.peca.linha == 6 and j.pontos == 1),
            ("C", lambda j: j.guardada == "T"),
            (" ", lambda j: j.tabuleiro.celulas[21] != [None] * 10),
            ("r", lambda j: j.pontos == 0 and j.guardada is None),
        ):
            self.assertTrue(self.comandos.tecla(tecla), tecla)
            self.assertTrue(esperado(self.jogo), tecla)

    def test_tecla_sem_sentido(self):
        self.preparar(Peca("T", linha=5, coluna=3))
        self.assertFalse(self.comandos.tecla("Shift"))

    def test_descer_no_chao_nao_conta_ponto(self):
        self.preparar(Peca("O", linha=20, coluna=3))
        self.comandos.tecla("ArrowDown")
        self.assertEqual(self.jogo.pontos, 0)


class TestEstado(Partida):
    def test_estado_do_controle(self):
        self.preparar(Peca("O", linha=5, coluna=3))
        self.assertEqual(self.comandos.estado(), {"gesto": "sem mao", "alvo": None, "contagem": None})
        self.quadros(Gesto.MOVER, mao(7))
        self.assertEqual(self.comandos.estado(), {"gesto": "mover", "alvo": 7, "contagem": None})


class TestComReconhecimentoDeVerdade(unittest.TestCase):
    """Do desenho da mao ao comando, passando pelo `Mao` real."""

    def jogar(self, jogo: Jogo, pontos_por_quadro) -> None:
        mao_reconhecida, comandos = Mao(), Comandos(jogo)
        for i, pontos in enumerate(pontos_por_quadro):
            agora = i * QUADRO
            comandos.aplicar(mao_reconhecida.atualizar(pontos), pontos, agora)
            jogo.atualizar(agora)

    def test_pinca_de_verdade_gira_uma_vez(self):
        jogo = jogo_com(Peca("T", linha=5, coluna=3))
        self.jogar(jogo, [mao()] * 3 + [mao(pinca="indicador")] * 8 + [mao()] * 3)
        self.assertEqual(jogo.peca.rotacao, 1)

    def test_partida_mirando_e_socando(self):
        """Cada peca: mirar uma coluna, esperar chegar, fechar o punho."""
        jogo = Jogo(semente=11)
        alvos = [0, 9, 4, 2, 7]
        quadros = []
        for alvo in alvos:
            quadros += [mao(alvo)] * 25 + [mao(alvo, abertos=())] * 6 + [mao(alvo)] * 4
        travadas = []
        mao_reconhecida, comandos = Mao(), Comandos(jogo)
        for i, pontos in enumerate(quadros):
            agora = i * QUADRO
            comandos.aplicar(mao_reconhecida.atualizar(pontos), pontos, agora)
            jogo.atualizar(agora)
            travadas += [e for e in jogo.tirar_eventos() if e["tipo"] == "travou"]

        self.assertEqual(len(travadas), len(alvos))
        for alvo, travada in zip(alvos, travadas):
            colunas = sorted({c for _, c in travada["celulas"]})
            self.assertEqual(colunas[(len(colunas) - 1) // 2], alcancavel(colunas, alvo), travada)


if __name__ == "__main__":
    unittest.main()
