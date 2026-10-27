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

import random
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


# Gravidade: a curva das diretrizes oficiais, em segundos por linha, mas 25%
# mais lenta. O gesto tem atraso — a mao demora mais que um dedo no teclado —,
# e quem nunca jogou assim precisa de folga nos primeiros niveis.
LENTIDAO = 1.25
QUEDA_MINIMA = 0.05
DESCIDA_RAPIDA = 20  # quantas vezes mais rapido cai com a descida rapida ligada

# A peca encostada no chao espera isto antes de travar, e cada movimento
# reinicia a espera — ate este limite, para ninguem empurrar a peca para sempre.
ATRASO_DA_TRAVA = 0.5
MOVIMENTOS_NA_TRAVA = 15

PONTOS_POR_LINHAS = {1: 100, 2: 300, 3: 500, 4: 800}
LINHAS_POR_NIVEL = 10

# Maior passo de tempo aceito num quadro. Sem isto, uma janela que travou um
# segundo faria a peca despencar de uma vez quando voltasse.
PASSO_MAXIMO = 0.25


def intervalo_de_queda(nivel: int) -> float:
    return max((0.8 - (nivel - 1) * 0.007) ** (nivel - 1) * LENTIDAO, QUEDA_MINIMA)


class Saco:
    """Sorteio em "saco de 7": as sete pecas embaralhadas, uma de cada, e de novo.

    Sorteio puro deixa passar vinte pecas sem uma I; com o saco, a maior espera
    possivel por qualquer peca e de 12. E o que o Tetris oficial faz.
    """

    def __init__(self, sorteio: random.Random) -> None:
        self._sorteio = sorteio
        self._fila: list[str] = []

    def espiar(self, quantas: int) -> list[str]:
        while len(self._fila) < quantas:
            saco = list(TIPOS)
            self._sorteio.shuffle(saco)
            self._fila.extend(saco)
        return self._fila[:quantas]

    def tirar(self) -> str:
        self.espiar(1)
        return self._fila.pop(0)


class Jogo:
    """Uma partida. O tempo vem sempre de fora, por `atualizar(agora)`.

    Os comandos (`mover`, `girar`, `despencar`...) valem tanto para o gesto
    quanto para o teclado; quem os chama nao precisa saber de regra nenhuma.
    O que acontece de notavel vira um evento em `eventos`, que a tela recolhe
    com `tirar_eventos()` para animar — piscar a linha, sacudir no despencar.
    O resto ela le de `estado()`.
    """

    # Quantas pecas da fila a tela mostra.
    FILA_VISIVEL = 3

    def __init__(self, semente: int | None = None) -> None:
        self._semente = semente
        self.recomecar()

    def recomecar(self) -> None:
        self.tabuleiro = Tabuleiro()
        self.saco = Saco(random.Random(self._semente))
        self.pontos = 0
        self.linhas = 0
        self.nivel = 1
        self.situacao = "jogando"
        self.descendo_rapido = False
        self.guardada: str | None = None
        self.pode_guardar = True
        self.eventos: list[dict] = []
        self._agora: float | None = None
        self._queda = 0.0
        self._nascer()

    # ------------------------------------------------------------ comandos

    def mover(self, colunas: int) -> bool:
        return self._jogando() and self._tentar(self.peca.movida(colunas=colunas))

    def girar(self, sentido: int = 1) -> bool:
        if not self._jogando():
            return False
        for tentativa in self.peca.tentativas_de_giro(sentido):
            if self._tentar(tentativa):
                self.eventos.append({"tipo": "girou"})
                return True
        return False

    def despencar(self) -> None:
        if not self._jogando():
            return
        descidas = 0
        while self._descer():
            descidas += 1
        self.pontos += 2 * descidas
        self.eventos.append({"tipo": "despencou", "linhas": descidas})
        self._travar()

    def guardar(self) -> bool:
        """Troca a peca atual pela guardada — uma vez so por peca.

        Sem o limite, guardar e trazer de volta sem parar seguraria a peca no
        alto para sempre.
        """
        if not self._jogando() or not self.pode_guardar:
            return False
        # Na primeira vez nao ha o que trazer de volta: vem a proxima da fila.
        trazida, self.guardada = self.guardada, self.peca.tipo
        self._nascer(trazida)
        self.pode_guardar = False
        self.eventos.append({"tipo": "guardou", "peca": self.guardada})
        return True

    def descer(self) -> bool:
        """Uma linha para baixo, valendo um ponto — a seta para baixo."""
        if not self._jogando() or not self._descer():
            return False
        self.pontos += 1
        self._queda = 0.0
        return True

    def descer_rapido(self, ligado: bool) -> None:
        self.descendo_rapido = ligado

    def pausar(self, ligado: bool) -> None:
        if self.situacao == "fim" or (self.situacao == "pausado") == ligado:
            return
        self.situacao = "pausado" if ligado else "jogando"
        self.eventos.append({"tipo": self.situacao})

    def sombra(self) -> Peca:
        """Onde a peca cairia se despencasse agora."""
        peca = self.peca
        while self.tabuleiro.cabe(peca.movida(1)):
            peca = peca.movida(1)
        return peca

    def estado(self) -> dict:
        """O retrato da partida para a tela, so com tipos que o JSON aceita.

        As linhas vem na numeracao da tela: 0 e a primeira a vista, e as duas
        escondidas ficam negativas. O tabuleiro vai como texto, uma string por
        linha, com "." no vazio e a letra da peca no ocupado — legivel num log.
        """
        return {
            "largura": LARGURA,
            "altura": ALTURA,
            "tabuleiro": [
                "".join(celula or "." for celula in linha) for linha in self.tabuleiro.celulas[ESCONDIDAS:]
            ],
            "peca": {"tipo": self.peca.tipo, "celulas": _na_tela(self.peca.celulas)},
            "sombra": _na_tela(self.sombra().celulas),
            "proximas": self.saco.espiar(self.FILA_VISIVEL),
            "guardada": self.guardada,
            "pode_guardar": self.pode_guardar,
            "pontos": self.pontos,
            "nivel": self.nivel,
            "linhas": self.linhas,
            "situacao": self.situacao,
        }

    def tirar_eventos(self) -> list[dict]:
        eventos, self.eventos = self.eventos, []
        return eventos

    # ------------------------------------------------------------ tempo

    def intervalo(self) -> float:
        """Segundos para a peca descer uma linha, agora."""
        base = intervalo_de_queda(self.nivel)
        return base / DESCIDA_RAPIDA if self.descendo_rapido else base

    def atualizar(self, agora: float) -> None:
        passo = 0.0 if self._agora is None else min(agora - self._agora, PASSO_MAXIMO)
        self._agora = agora
        if not self._jogando():
            return

        self._queda += passo
        while self._queda >= self.intervalo():
            self._queda -= self.intervalo()
            if not self._descer():
                self._queda = 0.0
                break
            if self.descendo_rapido:
                self.pontos += 1

        if self._no_chao():
            self._trava += passo
            if self._trava >= ATRASO_DA_TRAVA:
                self._travar()
        else:
            self._trava = 0.0

    # ------------------------------------------------------------ por dentro

    def _jogando(self) -> bool:
        return self.situacao == "jogando"

    def _nascer(self, tipo: str | None = None) -> None:
        """A proxima peca, centralizada nas linhas escondidas.

        Desce uma linha logo ao nascer, se der, como manda o Tetris oficial:
        assim a peca ja aparece na beirada de cima do campo.
        """
        tipo = tipo or self.saco.tirar()
        peca = Peca(tipo, coluna=(LARGURA - FORMAS[tipo][0]) // 2)
        if not self.tabuleiro.cabe(peca):
            self._acabar()
            return
        if self.tabuleiro.cabe(peca.movida(1)):
            peca = peca.movida(1)
        self.peca = peca
        self._trava = 0.0
        self._movimentos_na_trava = 0
        self._mais_baixa = peca.linha

    def _no_chao(self) -> bool:
        return not self.tabuleiro.cabe(self.peca.movida(1))

    def _tentar(self, nova: Peca) -> bool:
        """Poe a peca na posicao nova se couber, reiniciando a espera da trava."""
        if not self.tabuleiro.cabe(nova):
            return False
        no_chao = self._no_chao()
        self.peca = nova
        if no_chao and self._movimentos_na_trava < MOVIMENTOS_NA_TRAVA:
            self._movimentos_na_trava += 1
            self._trava = 0.0
        return True

    def _descer(self) -> bool:
        nova = self.peca.movida(1)
        if not self.tabuleiro.cabe(nova):
            return False
        self.peca = nova
        # Chegar mais baixo que nunca devolve os movimentos da trava.
        if nova.linha > self._mais_baixa:
            self._mais_baixa = nova.linha
            self._movimentos_na_trava = 0
        return True

    def _travar(self) -> None:
        peca = self.peca
        completas = self.tabuleiro.fixar(peca)
        self.eventos.append({"tipo": "travou", "celulas": [[l - ESCONDIDAS, c] for l, c in peca.celulas]})

        if completas:
            self.pontos += PONTOS_POR_LINHAS[len(completas)] * self.nivel
            self.linhas += len(completas)
            self.eventos.append({"tipo": "linhas", "linhas": [l - ESCONDIDAS for l in completas]})
            nivel = 1 + self.linhas // LINHAS_POR_NIVEL
            if nivel > self.nivel:
                self.nivel = nivel
                self.eventos.append({"tipo": "subiu_nivel", "nivel": nivel})

        self.pode_guardar = True
        # Travar inteira nas linhas escondidas tambem acaba o jogo.
        if all(linha < ESCONDIDAS for linha, _ in peca.celulas):
            self._acabar()
            return
        self._queda = 0.0
        self._nascer()

    def _acabar(self) -> None:
        self.situacao = "fim"
        self.eventos.append({"tipo": "fim", "pontos": self.pontos})


def _na_tela(celulas) -> list[list[int]]:
    return [[linha - ESCONDIDAS, coluna] for linha, coluna in celulas]
