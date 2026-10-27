"""Dos 21 pontos da mao ao gesto.

O MediaPipe devolve 21 pontos por mao, normalizados entre 0 e 1 em relacao ao
quadro. Os que importam aqui:

    0 pulso          4 ponta do polegar
    5  9 13 17       base do indicador, medio, anelar e minimo
    6 10 14 18       junta do meio de cada um
    8 12 16 20       ponta de cada um

Sao quatro gestos, e todos se fazem sem tirar a mao do lugar:

    nada             so move
    pinca indicador  polegar encostado na ponta do indicador
    pinca medio      polegar encostado na ponta do medio
    punho            os quatro dedos fechados

**Toda medida e relativa ao tamanho da mao.** A primeira versao media a pinca
em fracao do quadro (0,05): longe da camera a mao inteira cabia nisso e a mao
aberta virava pinca; perto, a pinca nunca fechava. Dividir pela palma (pulso ate
a base do medio) deixa a medida igual a 30 cm ou a 1 m.

**Dedo aberto e ponta mais longe do pulso que a junta.** A versao anterior
comparava so a altura dos pontos, e bastava inclinar a mao para errar.

**A pinca tem histerese.** Fecha abaixo de um limiar e so abre acima de outro,
maior. Com um limiar so, a medida oscilando na fronteira picotava o traco.

**Vale o dedo claramente mais perto.** As pontas do indicador e do medio ficam a
dois centimetros uma da outra, e para chegar ao medio o polegar passa pelo
indicador. Na primeira versao a histerese segurava essa pinca de passagem: o
polegar colado no medio continuava "perto o bastante" do indicador, e guardar
a peca no Tetris nunca funcionava. Agora uma pinca so vale — e so se mantem —
enquanto o outro dedo nao estiver bem mais perto.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Protocol, Sequence


class Ponto(Protocol):
    x: float
    y: float
    z: float


class Gesto(Enum):
    NENHUM = "sem mao"
    MOVER = "mover"
    PINCA_INDICADOR = "pinca indicador"
    PINCA_MEDIO = "pinca medio"
    PUNHO = "punho"


# Os ossos da mao: que ponto se liga a qual, para desenhar o esqueleto. Sao os
# mesmos do MediaPipe, copiados aqui para quem desenha (a tela do Tetris) nao
# depender de o MediaPipe estar instalado.
CONEXOES = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)

# (ponta, junta do meio) de indicador, medio, anelar e minimo.
DEDOS = ((8, 6), (12, 10), (16, 14), (20, 18))

# Pinca, em fracao do tamanho da palma.
PINCA_FECHA = 0.25
PINCA_ABRE = 0.40

# Para um dedo vencer, o polegar precisa estar a menos disto da distancia ate o outro.
VANTAGEM = 0.7

# Folga para o dedo contar como aberto: a ponta precisa passar da junta.
FOLGA_DEDO = 1.1

# Quadros seguidos com o mesmo gesto antes de ele valer. Pouco, porque a
# histerese da pinca ja segura a oscilacao — cada quadro a mais e atraso.
QUADROS_PARA_CONFIRMAR = 2


def distancia(pontos: Sequence[Ponto], a: int, b: int) -> float:
    return math.hypot(pontos[a].x - pontos[b].x, pontos[a].y - pontos[b].y)


def tamanho_da_mao(pontos: Sequence[Ponto]) -> float:
    """Do pulso a base do medio: a regua de todas as outras medidas."""
    return distancia(pontos, 0, 9) or 1e-6


def dedos_abertos(pontos: Sequence[Ponto]) -> list[bool]:
    """Indicador, medio, anelar e minimo, nesta ordem."""
    return [distancia(pontos, 0, ponta) > distancia(pontos, 0, junta) * FOLGA_DEDO for ponta, junta in DEDOS]


def aberturas(pontos: Sequence[Ponto]) -> tuple[float, float]:
    """Distancia do polegar ate o indicador e ate o medio, em palmas."""
    tamanho = tamanho_da_mao(pontos)
    return distancia(pontos, 4, 8) / tamanho, distancia(pontos, 4, 12) / tamanho


def centro_da_palma(pontos: Sequence[Ponto]) -> tuple[float, float]:
    """Media do pulso e das quatro bases.

    E o ponto que guia o cursor. A ponta do dedo seria mais intuitiva, mas e
    ela que se mexe ao fazer a pinca: o cursor pularia bem na hora do clique.
    """
    indices = (0, 5, 9, 13, 17)
    return (
        sum(pontos[i].x for i in indices) / len(indices),
        sum(pontos[i].y for i in indices) / len(indices),
    )


def _vence(este: float, outro: float) -> bool:
    """Se o polegar esta encostado neste dedo, e claramente nao no outro."""
    return este < PINCA_FECHA and este < outro * VANTAGEM


def classificar(pontos: Sequence[Ponto], anterior: Gesto = Gesto.MOVER) -> Gesto:
    """O gesto de um quadro. `anterior` decide de que lado da histerese esta."""
    indicador, medio = aberturas(pontos)

    if anterior == Gesto.PINCA_INDICADOR and indicador < PINCA_ABRE and not _vence(medio, indicador):
        return Gesto.PINCA_INDICADOR
    if anterior == Gesto.PINCA_MEDIO and medio < PINCA_ABRE and not _vence(indicador, medio):
        return Gesto.PINCA_MEDIO

    if not any(dedos_abertos(pontos)):
        return Gesto.PUNHO

    if _vence(indicador, medio):
        return Gesto.PINCA_INDICADOR
    if _vence(medio, indicador):
        return Gesto.PINCA_MEDIO
    return Gesto.MOVER


class Mao:
    """Uma mao acompanhada ao longo dos quadros."""

    def __init__(self) -> None:
        self.pontos: Sequence[Ponto] | None = None
        self.gesto = Gesto.NENHUM
        self._candidato = Gesto.NENHUM
        self._repeticoes = 0

    def atualizar(self, pontos: Sequence[Ponto] | None) -> Gesto:
        """Registra o quadro novo e devolve o gesto confirmado."""
        self.pontos = pontos
        if pontos is None:
            self.gesto = self._candidato = Gesto.NENHUM
            self._repeticoes = 0
            return self.gesto

        atual = classificar(pontos, self.gesto)
        self._repeticoes = self._repeticoes + 1 if atual == self._candidato else 1
        self._candidato = atual
        # A mao que acabou de aparecer comeca movendo, sem esperar confirmacao.
        if self.gesto == Gesto.NENHUM:
            self.gesto = Gesto.MOVER
        if self._repeticoes >= QUADROS_PARA_CONFIRMAR:
            self.gesto = atual
        return self.gesto


def espelhar(pontos: Sequence[Ponto]) -> list[Ponto]:
    """Os mesmos pontos, como num espelho.

    O MediaPipe precisa da imagem original da camera: e por ela que ele diz se
    a mao e direita ou esquerda. Espelhar a imagem antes de detectar — como a
    primeira versao fazia, herdada do projeto original — invertia o rotulo, e a
    mao direita virava a secundaria. Agora so os pontos sao espelhados, depois.
    """
    return [_Espelhado(1 - p.x, p.y, p.z) for p in pontos]


class _Espelhado:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float) -> None:
        self.x, self.y, self.z = x, y, z


def separar_maos(maos: Sequence[tuple[str, Sequence[Ponto]]], destro: bool = True):
    """Separa as maos (ja espelhadas) em (principal, secundaria).

    `maos` sao pares (rotulo, pontos), com rotulo "Right" ou "Left". Uma mao
    sozinha e sempre a principal: ninguem quer descobrir que levantou a mao
    "errada". Com duas, vale o rotulo; se o MediaPipe der o mesmo para as duas,
    decide a posicao — na imagem espelhada a mao direita fica a direita.
    """
    if not maos:
        return None, None
    if len(maos) == 1:
        return maos[0][1], None

    (rotulo_a, a), (rotulo_b, b) = maos[:2]
    if rotulo_a != rotulo_b:
        direita, esquerda = (a, b) if rotulo_a == "Right" else (b, a)
    else:
        direita, esquerda = (a, b) if a[0].x > b[0].x else (b, a)
    return (direita, esquerda) if destro else (esquerda, direita)
