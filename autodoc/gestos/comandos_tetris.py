"""Dos gestos (e do teclado) aos comandos do Tetris.

E aqui que se decide se o jogo e bom de jogar com a mao. As regras sao do
`tetris.py`; isto so traduz.

    mao para os lados      a peca vai para a coluna da mao
    pinca indicador        gira, ao soltar
    pinca medio            guarda a peca
    punho                  despenca
    mao no terco de baixo  cai mais rapido
    sem mao                pausa; volta com contagem
    pinca no fim           recomeca

**A mao aponta a coluna; a peca anda ate la.** Teleportar a peca para a coluna
da mao atravessaria os blocos no caminho. Andando uma coluna por quadro, ela
bate onde bateria no teclado, e a 30 quadros por segundo o caminho inteiro leva
um terco de segundo — rapido o bastante para parecer que segue a mao.

**Coluna magnetica.** Com a mao parada na fronteira entre duas colunas, a
tremida faria a peca pular de uma para a outra. A coluna so troca depois de a
mao entrar 30% na vizinha, e so volta depois de entrar 30% de volta.

**Comandos so uma vez por gesto.** Fechar e abrir a pinca gira uma vez;
segurar nao continua girando. E o que um botao faz, e e o que a pessoa espera
sem ninguem explicar.

**Girar acontece ao soltar a pinca, como um clique.** Para encostar o polegar
no medio — guardar a peca — ele passa pela ponta do indicador, e girar na hora
em que a pinca do indicador aparecia fazia a peca girar toda vez que alguem
tentava guarda-la. Esperando a pinca abrir, da para saber se ela era mesmo do
indicador ou so caminho para o medio.

**O punho precisa se firmar.** Despencar nao tem volta, entao o punho tem que
aparecer em alguns quadros seguidos — uma mao saindo da camera passa por
formas que parecem punho por um instante. E depois de despencar a peca nova
espera um pouco antes de seguir a mao: o punho ainda fechado nao deve arrastar
a proxima peca para o canto.
"""

from __future__ import annotations

import math
from typing import Sequence

from autodoc.gestos.cursor import FiltroUmEuro
from autodoc.gestos.reconhecimento import Gesto, Ponto, centro_da_palma
from autodoc.gestos.tetris import Jogo

# Fatia horizontal da camera que cobre as 10 colunas. Mais estreita que a do
# mouse: o tabuleiro tem so 10 posicoes, e atravessa-lo nao deve pedir que a mao
# va de um lado ao outro do corpo.
AREA_X = (0.30, 0.70)

# Quanto a mao precisa entrar na coluna vizinha para a peca trocar.
MAGNETISMO = 0.3

# Palma abaixo disto, em fracao da altura do quadro, liga a descida rapida.
ZONA_DESCIDA = 0.72

# Quadros seguidos de punho para despencar.
QUADROS_PUNHO = 3

# Depois de despencar, a peca nova espera isto antes de seguir a mao.
ESPERA_APOS_DESPENCAR = 0.3

# Contagem quando a mao volta depois de sumir, para ninguem perder a peca no susto.
CONTAGEM_AO_VOLTAR = 1.0

# O teclado, pelos nomes do `event.key` do navegador. Letras valem maiusculas
# ou minusculas.
TECLAS = {
    "ArrowLeft": "esquerda",
    "ArrowRight": "direita",
    "ArrowUp": "girar",
    "x": "girar",
    "z": "girar_ao_contrario",
    "ArrowDown": "descer",
    " ": "despencar",
    "c": "guardar",
    "p": "pausar",
    "r": "recomecar",
}


class ColunaDaMao:
    """O x da palma (0 a 1) vira uma coluna, com filtro e magnetismo."""

    def __init__(self, colunas: int = 10, area: tuple[float, float] = AREA_X, magnetismo: float = MAGNETISMO) -> None:
        self.colunas = colunas
        self.area = area
        self.magnetismo = magnetismo
        # O filtro foi ajustado para pixels de tela; mil "pixels" por quadro
        # inteiro deixa a mesma regulagem servir aqui.
        self._filtro = FiltroUmEuro()
        self.coluna: int | None = None

    def reiniciar(self) -> None:
        self._filtro.reiniciar()
        self.coluna = None

    def atualizar(self, x: float, agora: float) -> int:
        x = self._filtro(x * 1000, agora) / 1000
        esquerda, direita = self.area
        posicao = (x - esquerda) / (direita - esquerda) * self.colunas
        posicao = min(max(posicao, 0.0), self.colunas - 1e-9)

        if self.coluna is None:
            self.coluna = int(posicao)
        while posicao >= self.coluna + 1 + self.magnetismo:
            self.coluna += 1
        while posicao < self.coluna - self.magnetismo:
            self.coluna -= 1
        self.coluna = min(max(self.coluna, 0), self.colunas - 1)
        return self.coluna


def coluna_da_peca(jogo: Jogo) -> int:
    """A coluna que representa a peca: a do meio, puxando para a esquerda.

    E a que a pessoa olha quando mira. Para a I deitada, a segunda das quatro;
    para a O, a esquerda das duas.
    """
    colunas = sorted({coluna for _, coluna in jogo.peca.celulas})
    return colunas[(len(colunas) - 1) // 2]


class Comandos:
    def __init__(self, jogo: Jogo) -> None:
        self.jogo = jogo
        self.coluna = ColunaDaMao(colunas=jogo.tabuleiro.largura)
        self.gesto = Gesto.NENHUM
        self.alvo: int | None = None
        self._quadros_punho = 0
        self._despencou_em = -math.inf
        self._pausado_pela_mao = False
        self._voltou_em: float | None = None
        self._agora = 0.0

    # ------------------------------------------------------------ mao

    def aplicar(self, gesto: Gesto, pontos: Sequence[Ponto] | None, agora: float) -> None:
        """O gesto confirmado da mao principal neste quadro."""
        anterior, self.gesto = self.gesto, gesto
        self._agora = agora
        jogo = self.jogo

        if jogo.situacao == "fim":
            if gesto == Gesto.PINCA_INDICADOR and anterior != Gesto.PINCA_INDICADOR:
                jogo.recomecar()
            return

        if gesto == Gesto.NENHUM:
            self._sumiu()
            return
        if not self._voltou(agora) or jogo.situacao != "jogando":
            return

        x, y = centro_da_palma(pontos)
        self.alvo = self.coluna.atualizar(x, agora)
        firme = gesto != Gesto.PUNHO and agora - self._despencou_em >= ESPERA_APOS_DESPENCAR
        if firme:
            self._andar_para(self.alvo)
        jogo.descer_rapido(gesto == Gesto.MOVER and y > ZONA_DESCIDA)

        if anterior == Gesto.PINCA_INDICADOR and gesto not in (Gesto.PINCA_INDICADOR, Gesto.PINCA_MEDIO):
            jogo.girar()
        if gesto == Gesto.PINCA_MEDIO and anterior != Gesto.PINCA_MEDIO:
            jogo.guardar()

        self._quadros_punho = self._quadros_punho + 1 if gesto == Gesto.PUNHO else 0
        if self._quadros_punho == QUADROS_PUNHO:
            jogo.despencar()
            self._despencou_em = agora

    def contagem(self) -> float | None:
        """Segundos que faltam para voltar a jogar, enquanto a mao volta."""
        if self._voltou_em is None:
            return None
        return max(CONTAGEM_AO_VOLTAR - (self._agora - self._voltou_em), 0.0)

    def _sumiu(self) -> None:
        self.coluna.reiniciar()
        self.alvo = None
        self._quadros_punho = 0
        self._voltou_em = None
        self.jogo.descer_rapido(False)
        if self.jogo.situacao == "jogando":
            self.jogo.pausar(True)
            self._pausado_pela_mao = True

    def _voltou(self, agora: float) -> bool:
        """Se ja pode jogar: so depois da contagem, quando a pausa foi da mao."""
        if not self._pausado_pela_mao:
            return True
        if self._voltou_em is None:
            self._voltou_em = agora
        if agora - self._voltou_em < CONTAGEM_AO_VOLTAR:
            return False
        self._pausado_pela_mao = False
        self._voltou_em = None
        self.jogo.pausar(False)
        return True

    def _andar_para(self, alvo: int) -> None:
        atual = coluna_da_peca(self.jogo)
        if atual != alvo:
            self.jogo.mover(1 if alvo > atual else -1)

    # ------------------------------------------------------------ teclado

    def tecla(self, nome: str) -> bool:
        """Uma tecla apertada na tela. Devolve se ela significa alguma coisa."""
        comando = TECLAS.get(nome) or TECLAS.get(nome.lower())
        if comando is None:
            return False
        jogo = self.jogo
        if comando == "esquerda":
            jogo.mover(-1)
        elif comando == "direita":
            jogo.mover(1)
        elif comando == "girar":
            jogo.girar()
        elif comando == "girar_ao_contrario":
            jogo.girar(-1)
        elif comando == "descer":
            jogo.descer()
        elif comando == "despencar":
            jogo.despencar()
        elif comando == "guardar":
            jogo.guardar()
        elif comando == "pausar":
            # Pausa do teclado so o teclado tira; a volta da mao nao.
            self._pausado_pela_mao = False
            self._voltou_em = None
            jogo.pausar(jogo.situacao != "pausado")
        elif comando == "recomecar":
            jogo.recomecar()
        return True

    def estado(self) -> dict:
        """O que a tela mostra sobre o controle, alem do jogo."""
        return {
            "gesto": self.gesto.value,
            "alvo": self.alvo,
            "contagem": self.contagem(),
            "descendo": self.jogo.descendo_rapido,
            # A altura da palma que liga a descida rapida, para a tela marcar na camera.
            "zona_descida": ZONA_DESCIDA,
        }
