"""Da posicao da mao na camera a posicao na tela.

**Absoluto, e nao relativo.** A primeira versao andava pelo deslocamento da mao
entre dois quadros e descartava deslocamentos pequenos como tremida — so que
num movimento lento todo deslocamento e pequeno, e o cursor simplesmente nao
andava. Agora cada ponto de uma area central da camera corresponde a um ponto
da tela: a mao no mesmo lugar sempre leva o cursor ao mesmo lugar.

**A area e menor que o quadro.** Perto da borda da camera a mao sai do quadro
e o MediaPipe a perde; com a margem, os cantos da tela ficam alcancaveis com a
mao inteira a vista.

**O filtro One Euro** (Casiez, Roussel e Vogel, CHI 2012) segura a tremida sem
atrasar o movimento: com a mao parada ele filtra forte, e quanto mais rapida
ela se move, menos ele filtra. Uma media movel faria o contrario do que se quer
— o cursor ficaria sempre atrasado, sobretudo nos movimentos rapidos.
"""

from __future__ import annotations

import math

# Fatia da camera, em fracao do quadro, que cobre a tela inteira:
# (esquerda, topo, direita, base). Mais baixa que alta porque a mao levantada
# fica na metade de cima do quadro, e o pulso precisa caber.
AREA = (0.20, 0.12, 0.80, 0.72)

# Parametros do filtro, para coordenadas em pixels de tela.
CORTE_MINIMO = 1.0  # Hz: quanto filtra com a mao parada
BETA = 0.008  # quanto a velocidade afrouxa o filtro
CORTE_DERIVADA = 1.0


def _alfa(corte: float, intervalo: float) -> float:
    tau = 1 / (2 * math.pi * corte)
    return 1 / (1 + tau / intervalo)


class FiltroUmEuro:
    def __init__(self, corte_minimo=CORTE_MINIMO, beta=BETA, corte_derivada=CORTE_DERIVADA) -> None:
        self.corte_minimo = corte_minimo
        self.beta = beta
        self.corte_derivada = corte_derivada
        self.reiniciar()

    def reiniciar(self) -> None:
        self._valor: float | None = None
        self._derivada = 0.0
        self._tempo = 0.0

    def __call__(self, valor: float, tempo: float) -> float:
        if self._valor is None:
            self._valor, self._tempo = valor, tempo
            return valor

        intervalo = max(tempo - self._tempo, 1e-3)
        derivada = (valor - self._valor) / intervalo
        self._derivada += _alfa(self.corte_derivada, intervalo) * (derivada - self._derivada)

        corte = self.corte_minimo + self.beta * abs(self._derivada)
        self._valor += _alfa(corte, intervalo) * (valor - self._valor)
        self._tempo = tempo
        return self._valor


class Cursor:
    """Converte um ponto da camera (0 a 1) num ponto de uma superficie em pixels."""

    def __init__(self, largura: int, altura: int, area=AREA) -> None:
        self.largura, self.altura = largura, altura
        self.area = area
        self._x, self._y = FiltroUmEuro(), FiltroUmEuro()

    def reiniciar(self) -> None:
        """A mao sumiu: o proximo ponto nao deve ser suavizado contra o ultimo."""
        self._x.reiniciar()
        self._y.reiniciar()

    def posicionar(self, x: float, y: float, tempo: float) -> tuple[int, int]:
        esquerda, topo, direita, base = self.area
        x = (x - esquerda) / (direita - esquerda) * self.largura
        y = (y - topo) / (base - topo) * self.altura
        x, y = self._x(x, tempo), self._y(y, tempo)
        # Um pixel longe da borda: o canto e o freio de emergencia do
        # PyAutoGUI, reservado para a mao no mouse de verdade.
        return (
            round(min(max(x, 1), self.largura - 2)),
            round(min(max(y, 1), self.altura - 2)),
        )
