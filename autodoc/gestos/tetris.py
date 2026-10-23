"""O Tetris em si: pecas, tabuleiro e regras. Sem camera, sem tela.

Tudo que pensa mora aqui, em Python, onde da para testar. A tela so desenha o
retrato que `Jogo.estado()` devolve — o JavaScript do projeto nao tem teste, e
regra de jogo sem teste e regra que quebra calada.

**A rotacao e a do Tetris moderno (SRS).** Quem ja jogou sente na hora quando a
peca gira "errado": a T que nao entra no buraco, a I que nao gira encostada na
parede. O SRS resolve isso com os *wall kicks* — se a peca girada bate em algo,
tenta alguns deslocamentos padronizados antes de desistir. As tabelas abaixo
sao as oficiais.

Coordenadas sempre em (linha, coluna), com a linha crescendo para baixo, como
na tela. As tabelas oficiais de kick vem em (x, y) com y para cima; a conversao
e feita uma vez, em `_kicks()`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# Cada peca na rotacao de nascimento, dentro da sua caixa (3x3, ou 4x4 para I e O).
FORMAS: dict[str, tuple[int, tuple[tuple[int, int], ...]]] = {
    "I": (4, ((1, 0), (1, 1), (1, 2), (1, 3))),
    "O": (4, ((0, 1), (0, 2), (1, 1), (1, 2))),
    "T": (3, ((0, 1), (1, 0), (1, 1), (1, 2))),
    "S": (3, ((0, 1), (0, 2), (1, 0), (1, 1))),
    "Z": (3, ((0, 0), (0, 1), (1, 1), (1, 2))),
    "J": (3, ((0, 0), (1, 0), (1, 1), (1, 2))),
    "L": (3, ((0, 2), (1, 0), (1, 1), (1, 2))),
}

TIPOS = tuple(FORMAS)

# Kicks oficiais, em (x, y) com y para cima, por (rotacao de, rotacao para).
# Rotacoes: 0 nascimento, 1 direita, 2 de cabeca para baixo, 3 esquerda.
_KICKS_JLSTZ = {
    (0, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (1, 0): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (1, 2): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (2, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (2, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (3, 2): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (3, 0): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (0, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
}
_KICKS_I = {
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
}


def _girar_celulas(celulas, tamanho: int):
    """Um quarto de volta no sentido horario, dentro da caixa."""
    return tuple(sorted((coluna, tamanho - 1 - linha) for linha, coluna in celulas))


def _rotacoes(tipo: str) -> tuple[tuple[tuple[int, int], ...], ...]:
    tamanho, celulas = FORMAS[tipo]
    if tipo == "O":
        return (tuple(sorted(celulas)),) * 4
    estados = [tuple(sorted(celulas))]
    for _ in range(3):
        estados.append(_girar_celulas(estados[-1], tamanho))
    return tuple(estados)


ROTACOES = {tipo: _rotacoes(tipo) for tipo in TIPOS}


def kicks(tipo: str, de: int, para: int) -> tuple[tuple[int, int], ...]:
    """Os deslocamentos (linhas, colunas) a tentar, em ordem, ao girar."""
    if tipo == "O":
        return ((0, 0),)
    tabela = _KICKS_I if tipo == "I" else _KICKS_JLSTZ
    # y para cima vira linha para baixo: troca o sinal.
    return tuple((-y, x) for x, y in tabela[(de, para)])


@dataclass(frozen=True)
class Peca:
    """Uma peca em jogo: tipo, rotacao e o canto superior esquerdo da caixa."""

    tipo: str
    rotacao: int = 0
    linha: int = 0
    coluna: int = 0

    @property
    def celulas(self) -> tuple[tuple[int, int], ...]:
        return tuple((self.linha + l, self.coluna + c) for l, c in ROTACOES[self.tipo][self.rotacao])

    def movida(self, linhas: int = 0, colunas: int = 0) -> "Peca":
        return replace(self, linha=self.linha + linhas, coluna=self.coluna + colunas)

    def girada(self, sentido: int = 1) -> "Peca":
        """So a rotacao, sem kick. `sentido` 1 e horario, -1 anti-horario."""
        return replace(self, rotacao=(self.rotacao + sentido) % 4)

    def tentativas_de_giro(self, sentido: int = 1):
        """As posicoes que o SRS tenta, em ordem, ao girar esta peca."""
        girada = self.girada(sentido)
        for linhas, colunas in kicks(self.tipo, self.rotacao, girada.rotacao):
            yield girada.movida(linhas, colunas)


# Tamanho oficial: 10 colunas e 20 linhas a vista, mais 2 escondidas em cima,
# onde a peca nasce. Sem elas a peca nasceria ja dentro do campo, e uma pilha
# alta acabaria o jogo antes da hora.
LARGURA = 10
ALTURA = 20
ESCONDIDAS = 2


class Tabuleiro:
    """As celulas ja fixadas. Vazio e `None`; ocupado guarda o tipo da peca."""

    def __init__(self, largura: int = LARGURA, altura: int = ALTURA + ESCONDIDAS) -> None:
        self.largura = largura
        self.altura = altura
        self.celulas: list[list[str | None]] = [[None] * largura for _ in range(altura)]

    def livre(self, linha: int, coluna: int) -> bool:
        """Acima do tabuleiro conta como livre: um kick pode levantar a peca."""
        if not 0 <= coluna < self.largura or linha >= self.altura:
            return False
        return linha < 0 or self.celulas[linha][coluna] is None

    def cabe(self, peca: Peca) -> bool:
        return all(self.livre(linha, coluna) for linha, coluna in peca.celulas)

    def fixar(self, peca: Peca) -> list[int]:
        """Grava a peca e apaga as linhas que ela completou. Devolve quais foram.

        As linhas vem na numeracao de antes de apagar, de cima para baixo — e
        o que a tela precisa para piscar o lugar certo.
        """
        for linha, coluna in peca.celulas:
            if linha >= 0:
                self.celulas[linha][coluna] = peca.tipo
        completas = [i for i, linha in enumerate(self.celulas) if all(linha)]
        for i in completas:
            del self.celulas[i]
            self.celulas.insert(0, [None] * self.largura)
        return completas
