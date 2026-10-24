"""Do gesto confirmado a acao no mouse do sistema.

    nada                     move o cursor
    pinca indicador, rapida  clique — duas seguidas, clique duplo
    pinca indicador, segura  segura o botao e arrasta
    pinca medio              clique direito
    punho                    rola a tela, como um joystick
    pinca da mao secundaria  volume (cima/baixo) e brilho (lados)

**Toque ou arrasto se decide depois.** Ao fechar a pinca o botao ainda nao e
apertado: se ela abrir logo, sem a mao andar, foi um clique, dado no ponto onde
a pinca fechou. Se demorar ou a mao andar, o botao desce ali e o arrasto
comeca. Apertar logo de cara faria todo clique arrastar um pouco, porque a mao
sempre se mexe ao fechar a pinca.

**O punho e um joystick.** Fechar marca a origem; afastar o punho dela rola, e
quanto mais longe, mais rapido. Voltar a origem para.
"""

from __future__ import annotations

import logging
import math
from typing import Callable, Sequence

from autodoc.gestos.cursor import Cursor
from autodoc.gestos.reconhecimento import Gesto, Ponto, centro_da_palma
from autodoc.gestos.sistema import RecursoIndisponivel, Sistema

logger = logging.getLogger(__name__)

# Pinca mais curta que isto e sem andar e um clique.
TOQUE_MAXIMO = 0.30  # segundos
ARRASTO_MINIMO = 12  # pixels de tela

# Dois cliques mais proximos que isto viram um clique duplo.
CLIQUE_DUPLO = 0.45  # segundos

# Deslocamento do joystick, em fracao do quadro, para cada nivel de velocidade.
ZONA_ALAVANCA = 0.05

INTERVALO_ROLAGEM = 0.08  # segundos entre dois passos de rolagem
INTERVALO_AJUSTE = 0.25  # segundos entre dois passos de volume ou brilho
PASSO_AJUSTE = 0.05  # 5% de volume ou brilho por passo


class Alavanca:
    """Joystick: a distancia da origem vira passos repetidos."""

    def __init__(self, intervalo: float, zona: float = ZONA_ALAVANCA) -> None:
        self.intervalo = intervalo
        self.zona = zona
        self.soltar()

    def soltar(self) -> None:
        self._origem: tuple[float, float] | None = None
        self._ultimo = 0.0

    def mover(self, x: float, y: float, agora: float) -> tuple[int, int]:
        """(horizontal, vertical): positivo e direita e cima; 0 e parado.

        So um eixo por vez — rolar na diagonal sem querer e o mais comum.
        """
        if self._origem is None:
            self._origem, self._ultimo = (x, y), agora
            return 0, 0
        if agora - self._ultimo < self.intervalo:
            return 0, 0

        dx = int((x - self._origem[0]) / self.zona)
        dy = int((self._origem[1] - y) / self.zona)
        passo = (dx, 0) if abs(dx) > abs(dy) else (0, dy)
        if passo != (0, 0):
            self._ultimo = agora
        return passo


class Controlador:
    def __init__(self, mouse, sistema: Sistema) -> None:
        self.mouse = mouse
        self.sistema = sistema
        self.cursor = Cursor(*mouse.size())

        self.gesto = Gesto.NENHUM
        self._pinca_inicio = 0.0
        self._pinca_origem = (0, 0)
        self._arrastando = False
        self._ultimo_clique = -math.inf
        self._rolagem = Alavanca(INTERVALO_ROLAGEM)
        self._ajuste = Alavanca(INTERVALO_AJUSTE)
        self._avisados: set[str] = set()

    def aplicar(self, gesto: Gesto, pontos: Sequence[Ponto] | None, agora: float) -> None:
        """O gesto da mao principal neste quadro."""
        anterior, self.gesto = self.gesto, gesto
        if anterior == Gesto.PINCA_INDICADOR and gesto != Gesto.PINCA_INDICADOR:
            # Virar pinca do medio e o polegar que passou pelo indicador a
            # caminho do medio: nao foi clique esquerdo, e sim o direito.
            self._soltar_pinca(agora, clicar=gesto != Gesto.PINCA_MEDIO)
        if gesto != Gesto.PUNHO:
            self._rolagem.soltar()
        if gesto == Gesto.NENHUM:
            self.cursor.reiniciar()
            return

        palma = centro_da_palma(pontos)
        x, y = self.cursor.posicionar(*palma, agora)

        if gesto == Gesto.MOVER:
            self.mouse.moveTo(x, y)
        elif gesto == Gesto.PINCA_INDICADOR:
            self._pinca(x, y, agora, nova=anterior != Gesto.PINCA_INDICADOR)
        elif gesto == Gesto.PINCA_MEDIO:
            if anterior != Gesto.PINCA_MEDIO:
                self.mouse.click(button="right")
        elif gesto == Gesto.PUNHO:
            horizontal, vertical = self._rolagem.mover(*palma, agora)
            if vertical:
                self.sistema.rolar_vertical(vertical)
            if horizontal:
                self.sistema.rolar_horizontal(horizontal)

    def aplicar_secundaria(self, gesto: Gesto, pontos: Sequence[Ponto] | None, agora: float) -> None:
        """A outra mao so ajusta volume e brilho, com a pinca do indicador."""
        if gesto != Gesto.PINCA_INDICADOR:
            self._ajuste.soltar()
            return
        horizontal, vertical = self._ajuste.mover(*centro_da_palma(pontos), agora)
        if vertical:
            self._ajustar(self.sistema.ajustar_volume, vertical * PASSO_AJUSTE)
        if horizontal:
            self._ajustar(self.sistema.ajustar_brilho, horizontal * PASSO_AJUSTE)

    def soltar_tudo(self) -> None:
        """Ao fechar: nenhum botao fica apertado para tras."""
        if self._arrastando:
            self._arrastando = False
            self.mouse.mouseUp(button="left")
        self.gesto = Gesto.NENHUM

    def _pinca(self, x: int, y: int, agora: float, nova: bool) -> None:
        if nova:
            self._pinca_inicio, self._pinca_origem = agora, (x, y)
            return
        if not self._arrastando:
            andou = math.dist((x, y), self._pinca_origem) > ARRASTO_MINIMO
            if not andou and agora - self._pinca_inicio <= TOQUE_MAXIMO:
                return
            self._arrastando = True
            self.mouse.mouseDown(*self._pinca_origem, button="left")
        # dragTo, e nao moveTo: no macOS mover com o botao apertado precisa
        # ser um evento de arrasto, senao o sistema nao arrasta nada.
        self.mouse.dragTo(x, y, button="left", mouseDownUp=False)

    def _soltar_pinca(self, agora: float, clicar: bool = True) -> None:
        if self._arrastando:
            self._arrastando = False
            self.mouse.mouseUp(button="left")
            return
        if not clicar:
            return
        if agora - self._ultimo_clique < CLIQUE_DUPLO:
            self.sistema.clique_duplo(*self._pinca_origem)
            self._ultimo_clique = -math.inf
        else:
            self.mouse.click(*self._pinca_origem)
            self._ultimo_clique = agora

    def _ajustar(self, ajuste: Callable[[float], None], delta: float) -> None:
        """Volume e brilho podem faltar sem derrubar o mouse. Avisa uma vez so."""
        try:
            ajuste(delta)
        except RecursoIndisponivel as erro:
            if str(erro) not in self._avisados:
                self._avisados.add(str(erro))
                logger.warning("%s", erro)
