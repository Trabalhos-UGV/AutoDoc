"""Do gesto confirmado a acao no computador.

    V (indicador e medio abertos e afastados)  move o cursor e arma o clique
    medio, com o clique armado                  clique esquerdo
    indicador, com o clique armado              clique direito
    dois dedos juntos, com o clique armado      clique duplo
    punho                                       segura o botao e arrasta
    pinca da mao principal                      brilho (lado) e volume (cima/baixo)
    pinca da mao secundaria                     rolagem (lado e cima/baixo)
    mao aberta                                  nada — e a posicao de descanso

O clique precisa ser armado pelo V para que abrir e fechar a mao no meio de um
movimento nao clique sem querer.

**O cursor anda pelo deslocamento da mao, nao pela posicao dela.** Tremidas
pequenas sao ignoradas, movimentos medios sao amortecidos e os grandes
ampliados. E o que torna possivel acertar um botao pequeno com a mao no ar.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from autodoc.gestos.reconhecimento import Gesto, Ponto
from autodoc.gestos.sistema import RecursoIndisponivel, Sistema

logger = logging.getLogger(__name__)

# Ponto da mao que guia o cursor: a base do dedo medio, o mais estavel.
PONTO_CURSOR = 9

# Deslocamento minimo da pinca (em decimos do quadro) para contar como gesto.
LIMIAR_PINCA = 0.3

# Quadros com a pinca parada no mesmo nivel antes de repetir a acao.
QUADROS_PINCA = 5


class Controlador:
    def __init__(self, mouse, sistema: Sistema) -> None:
        self.mouse = mouse
        self.sistema = sistema
        self.largura, self.altura = mouse.size()

        self._mao_anterior: tuple[float, float] | None = None
        self._clique_armado = False
        self._arrastando = False
        self._pinca_ativa: int | None = None
        self._pinca_inicio = (0.0, 0.0)
        self._pinca_horizontal: bool | None = None
        self._pinca_nivel = 0.0
        self._pinca_quadros = 0
        self._avisados: set[str] = set()

    def aplicar(self, gesto: int, pontos: Sequence[Ponto]) -> None:
        if gesto != Gesto.PUNHO:
            self._soltar()
        if gesto not in (Gesto.PINCA_PRINCIPAL, Gesto.PINCA_SECUNDARIA):
            self._pinca_ativa = None

        destino = self._destino(pontos) if gesto != Gesto.PALMA else None

        if gesto == Gesto.V:
            self._clique_armado = True
            self.mouse.moveTo(*destino)
        elif gesto == Gesto.PUNHO:
            if not self._arrastando:
                self._arrastando = True
                self.mouse.mouseDown(button="left")
            self.mouse.moveTo(*destino)
        elif gesto == Gesto.MEDIO and self._clique_armado:
            self._clique_armado = False
            self.mouse.click()
        elif gesto == Gesto.INDICADOR and self._clique_armado:
            self._clique_armado = False
            self.mouse.click(button="right")
        elif gesto == Gesto.DOIS_JUNTOS and self._clique_armado:
            self._clique_armado = False
            self.mouse.doubleClick()
        elif gesto == Gesto.PINCA_SECUNDARIA:
            self._pinca(gesto, pontos, self._rolar_horizontal, self._rolar_vertical)
        elif gesto == Gesto.PINCA_PRINCIPAL:
            self._pinca(gesto, pontos, self._brilho, self._volume)

    def mao_sumiu(self) -> None:
        """A mao saiu do quadro: esquece a posicao e larga o que segurava.

        Sem soltar aqui, perder a mao de vista no meio de um arrasto deixava o
        botao do mouse preso.
        """
        self._mao_anterior = None
        self._soltar()

    def _soltar(self) -> None:
        if self._arrastando:
            self._arrastando = False
            self.mouse.mouseUp(button="left")

    def _destino(self, pontos: Sequence[Ponto]) -> tuple[int, int]:
        mao = (pontos[PONTO_CURSOR].x * self.largura, pontos[PONTO_CURSOR].y * self.altura)
        anterior = self._mao_anterior or mao
        self._mao_anterior = mao

        dx, dy = mao[0] - anterior[0], mao[1] - anterior[1]
        quadrado = dx * dx + dy * dy
        if quadrado <= 25:
            fator = 0.0
        elif quadrado <= 900:
            fator = 0.07 * quadrado ** 0.5
        else:
            fator = 2.1

        x, y = self.mouse.position()
        # Um pixel longe dos cantos: o canto e o freio de emergencia do
        # PyAutoGUI, reservado para a mao no mouse de verdade.
        return (
            round(min(max(x + dx * fator, 1), self.largura - 2)),
            round(min(max(y + dy * fator, 1), self.altura - 2)),
        )

    def _pinca(
        self,
        gesto: int,
        pontos: Sequence[Ponto],
        horizontal: Callable[[float], None],
        vertical: Callable[[float], None],
    ) -> None:
        """Pinca e arrastar: o eixo escolhe a acao, a distancia a intensidade.

        A acao so dispara depois de a mao ficar alguns quadros no mesmo nivel,
        e repete enquanto ela continuar la — segurar a pinca acima do ponto de
        partida continua subindo o volume.
        """
        if self._pinca_ativa != gesto:
            self._pinca_ativa = gesto
            self._pinca_inicio = (pontos[8].x, pontos[8].y)
            self._pinca_horizontal = None
            self._pinca_nivel = 0.0
            self._pinca_quadros = 0

        if self._pinca_quadros == QUADROS_PINCA:
            self._pinca_quadros = 0
            if self._pinca_horizontal is True:
                horizontal(self._pinca_nivel)
            elif self._pinca_horizontal is False:
                vertical(self._pinca_nivel)

        nivel_x = round((pontos[8].x - self._pinca_inicio[0]) * 10, 1)
        nivel_y = round((self._pinca_inicio[1] - pontos[8].y) * 10, 1)

        if abs(nivel_y) > abs(nivel_x) and abs(nivel_y) > LIMIAR_PINCA:
            self._pinca_horizontal, nivel = False, nivel_y
        elif abs(nivel_x) > LIMIAR_PINCA:
            self._pinca_horizontal, nivel = True, nivel_x
        else:
            return

        if abs(self._pinca_nivel - nivel) < LIMIAR_PINCA:
            self._pinca_quadros += 1
        else:
            self._pinca_nivel = nivel
            self._pinca_quadros = 0

    def _rolar_vertical(self, nivel: float) -> None:
        self.sistema.rolar_vertical(1 if nivel > 0 else -1)

    def _rolar_horizontal(self, nivel: float) -> None:
        self.sistema.rolar_horizontal(1 if nivel > 0 else -1)

    def _volume(self, nivel: float) -> None:
        self._ajustar(self.sistema.ajustar_volume, nivel / 50)

    def _brilho(self, nivel: float) -> None:
        self._ajustar(self.sistema.ajustar_brilho, nivel / 50)

    def _ajustar(self, ajuste: Callable[[float], None], delta: float) -> None:
        """Volume e brilho podem faltar sem derrubar o mouse. Avisa uma vez so."""
        try:
            ajuste(delta)
        except RecursoIndisponivel as erro:
            if str(erro) not in self._avisados:
                self._avisados.add(str(erro))
                logger.warning("%s", erro)
