"""Dos 21 pontos da mao ao gesto.

O MediaPipe devolve 21 pontos por mao, normalizados entre 0 e 1 em relacao ao
quadro. Os que importam aqui:

    0 pulso   4 ponta do polegar
    5 base do indicador   8 ponta do indicador
    9 base do medio      12 ponta do medio
   13 base do anelar     16 ponta do anelar
   17 base do minimo     20 ponta do minimo

**Cada dedo aberto e um bit.** Indicador vale 8, medio 4, anelar 2, minimo 1;
a soma diz quais estao abertos. Punho e 0, os quatro abertos e 15. O polegar
fica de fora da conta — ele so entra na pinca, medido pela distancia ate o
indicador.

**Um gesto so vale depois de se repetir.** A deteccao oscila de um quadro para
o outro; sem exigir alguns quadros seguidos iguais, uma mao parada dispararia
cliques sozinha.
"""

from __future__ import annotations

import math
from enum import IntEnum
from typing import Protocol, Sequence


class Ponto(Protocol):
    x: float
    y: float
    z: float


class Gesto(IntEnum):
    PUNHO = 0
    MEDIO = 4
    INDICADOR = 8
    DOIS_DEDOS = 12
    QUATRO_DEDOS = 15
    # Valores fora da soma de bits, para gestos que a soma nao distingue.
    PALMA = 31
    V = 33
    DOIS_JUNTOS = 34
    PINCA_PRINCIPAL = 35
    PINCA_SECUNDARIA = 36


# (ponta, junta do meio, base) de indicador, medio, anelar e minimo.
DEDOS = ((8, 5, 0), (12, 9, 0), (16, 13, 0), (20, 17, 0))

# Quantos quadros seguidos o mesmo gesto precisa aparecer para valer.
QUADROS_PARA_CONFIRMAR = 5

# Ponta do polegar a menos disto da ponta do indicador e pinca.
LIMIAR_PINCA = 0.05

# Indicador e medio mais afastados que 1,7x a distancia das bases formam um V.
LIMIAR_V = 1.7


def distancia(pontos: Sequence[Ponto], a: int, b: int) -> float:
    return math.hypot(pontos[a].x - pontos[b].x, pontos[a].y - pontos[b].y)


def distancia_com_sinal(pontos: Sequence[Ponto], a: int, b: int) -> float:
    """Positiva quando `a` esta acima de `b` no quadro (y cresce para baixo)."""
    sinal = 1 if pontos[a].y < pontos[b].y else -1
    return sinal * distancia(pontos, a, b)


def dedos_abertos(pontos: Sequence[Ponto]) -> int:
    """Os dedos abertos, um bit por dedo.

    O dedo esta aberto quando o trecho ponta-junta e pelo menos metade do
    trecho junta-pulso, apontando para o mesmo lado. Medir pela razao, e nao
    pela distancia, faz o resultado nao depender de quao perto da camera a mao
    esta.
    """
    bits = 0
    for ponta, junta, base in DEDOS:
        trecho = distancia_com_sinal(pontos, ponta, junta)
        palma = distancia_com_sinal(pontos, junta, base) or 0.01
        bits = bits << 1 | (round(trecho / palma, 1) > 0.5)
    return bits


def classificar(pontos: Sequence[Ponto], secundaria: bool = False) -> int:
    """O gesto de um unico quadro, ainda sem filtrar oscilacao."""
    bits = dedos_abertos(pontos)

    if bits in (7, Gesto.QUATRO_DEDOS) and distancia(pontos, 8, 4) < LIMIAR_PINCA:
        return Gesto.PINCA_SECUNDARIA if secundaria else Gesto.PINCA_PRINCIPAL

    if bits == Gesto.DOIS_DEDOS:
        bases = distancia(pontos, 5, 9) or 0.01
        if distancia(pontos, 8, 12) / bases > LIMIAR_V:
            return Gesto.V
        # Indicador e medio juntos e na mesma profundidade: duplo clique.
        if abs(pontos[8].z - pontos[12].z) < 0.1:
            return Gesto.DOIS_JUNTOS
        return Gesto.MEDIO

    return bits


class Mao:
    """Uma mao acompanhada ao longo dos quadros."""

    def __init__(self, secundaria: bool = False) -> None:
        self.secundaria = secundaria
        self.pontos: Sequence[Ponto] | None = None
        self.gesto: int = Gesto.PALMA
        self._ultimo: int = Gesto.PALMA
        self._repeticoes = 0

    def atualizar(self, pontos: Sequence[Ponto] | None) -> int:
        """Registra o quadro novo e devolve o gesto confirmado."""
        self.pontos = pontos
        if pontos is None:
            return Gesto.PALMA

        atual = classificar(pontos, self.secundaria)
        self._repeticoes = self._repeticoes + 1 if atual == self._ultimo else 0
        self._ultimo = atual
        if self._repeticoes >= QUADROS_PARA_CONFIRMAR - 1:
            self.gesto = atual
        return self.gesto


def separar_maos(maos: Sequence[tuple[str, Sequence[Ponto]]], destro: bool = True):
    """Separa as maos detectadas em (principal, secundaria).

    `maos` sao pares (rotulo, pontos), com rotulo "Right" ou "Left" como o
    MediaPipe devolve. A principal move o cursor e clica; a secundaria so
    rola a tela. Quem e canhoto inverte com `destro=False`.
    """
    direita = esquerda = None
    for rotulo, pontos in maos:
        if rotulo == "Right":
            direita = pontos
        else:
            esquerda = pontos
    return (direita, esquerda) if destro else (esquerda, direita)
