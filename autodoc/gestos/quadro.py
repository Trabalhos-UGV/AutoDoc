"""Quadro de desenho: os mesmos gestos do mouse, sem mexer no mouse.

    nada             so move o cursor
    pinca indicador  desenha
    pinca medio      apaga a regiao debaixo do cursor
    c                limpa o quadro
    Esc              fecha

Serve para treinar e calibrar os gestos antes de entregar o mouse do sistema a
eles. Um traco que picota mostra a pinca abrindo sem querer; um cursor que
treme mostra o filtro fraco demais. E, por nao tocar no mouse, nao precisa da
permissao de Acessibilidade no macOS — so da camera.

A imagem da camera fica num canto, com a mao desenhada e as medidas da pinca:
e por elas que se acertam os limiares de `reconhecimento.py`.
"""

from __future__ import annotations

from autodoc.gestos.camera import Sessao, desenhar, importar_visao, legenda
from autodoc.gestos.cursor import Cursor
from autodoc.gestos.reconhecimento import Gesto, Mao, centro_da_palma, separar_maos

LARGURA, ALTURA = 1280, 720
MINIATURA = (320, 180)

ESPESSURA = 6
RAIO_BORRACHA = 40

# BGR
BRANCO = (255, 255, 255)
TINTA = (60, 40, 30)
COR_CURSOR = (230, 120, 0)
COR_BORRACHA = (40, 40, 220)
COR_TEXTO = (120, 120, 120)

INSTRUCOES = "pinca indicador: desenha   pinca medio: apaga   c: limpa   Esc: sai"


class Folha:
    """O desenho em si. Separado da camera para poder ser testado sem ela."""

    def __init__(self, cv2, numpy) -> None:
        self.cv2 = cv2
        self.numpy = numpy
        self.tela = None
        self.limpar()
        self._ultimo: tuple[int, int] | None = None
        self._gesto: Gesto | None = None

    def limpar(self) -> None:
        self.tela = self.numpy.full((ALTURA, LARGURA, 3), 255, dtype=self.numpy.uint8)

    def aplicar(self, gesto: Gesto, ponto: tuple[int, int] | None) -> None:
        """Risca ou apaga do ponto anterior ate este.

        Ligar os pontos, e nao so marcar cada um, e o que faz um movimento
        rapido sair como traco continuo em vez de uma fileira de bolinhas.
        """
        if ponto is None or gesto not in (Gesto.PINCA_INDICADOR, Gesto.PINCA_MEDIO):
            self._ultimo = None
            self._gesto = None
            return
        if self._ultimo is None or self._gesto != gesto:
            self._ultimo = ponto
        if gesto == Gesto.PINCA_INDICADOR:
            self.cv2.line(self.tela, self._ultimo, ponto, TINTA, ESPESSURA, self.cv2.LINE_AA)
        else:
            self.cv2.line(self.tela, self._ultimo, ponto, BRANCO, RAIO_BORRACHA * 2)
        self._ultimo, self._gesto = ponto, gesto

    def compor(self, camera, gesto: Gesto, ponto: tuple[int, int] | None, texto: str):
        """O quadro, o cursor por cima, a camera no canto e as legendas."""
        cv2 = self.cv2
        imagem = self.tela.copy()
        if ponto is not None:
            if gesto == Gesto.PINCA_MEDIO:
                cv2.circle(imagem, ponto, RAIO_BORRACHA, COR_BORRACHA, 2, cv2.LINE_AA)
            elif gesto == Gesto.PINCA_INDICADOR:
                cv2.circle(imagem, ponto, ESPESSURA, TINTA, -1, cv2.LINE_AA)
            else:
                cv2.circle(imagem, ponto, 10, COR_CURSOR, 2, cv2.LINE_AA)

        largura, altura = MINIATURA
        imagem[ALTURA - altura :, LARGURA - largura :] = cv2.resize(camera, MINIATURA)

        cv2.putText(imagem, INSTRUCOES, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COR_TEXTO, 1, cv2.LINE_AA)
        cv2.putText(imagem, texto, (16, ALTURA - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COR_TEXTO, 1, cv2.LINE_AA)
        return imagem


def executar_quadro(camera: int = 0, destro: bool = True) -> int:
    cv2, mediapipe, BaseOptions, vision = importar_visao()
    import numpy  # vem junto com o OpenCV

    folha = Folha(cv2, numpy)
    cursor = Cursor(LARGURA, ALTURA)
    mao = Mao()
    with Sessao(cv2, mediapipe, BaseOptions, vision, camera, "AutoDoc - quadro de desenho") as sessao:
        for imagem, maos, agora in sessao.quadros():
            pontos, _ = separar_maos(maos, destro)
            gesto = mao.atualizar(pontos)
            if pontos is None:
                cursor.reiniciar()
                ponto = None
            else:
                ponto = cursor.posicionar(*centro_da_palma(pontos), agora)
            folha.aplicar(gesto, ponto)

            desenhar(cv2, imagem, maos, sessao.conexoes, pontos, [])
            tecla = sessao.mostrar(folha.compor(imagem, gesto, ponto, legenda(gesto, pontos)))
            if tecla is None:
                break
            if tecla == ord("c"):
                folha.limpar()
    return 0
