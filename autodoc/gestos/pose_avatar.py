"""Da pessoa na camera a pose do personagem 3D.

O MediaPipe da tres coisas, todas da imagem crua da camera:

    rosto   52 expressoes (piscar, abrir a boca, sorrir...) e a matriz 4x4 que
            leva o rosto "de frente" ate a posicao dele — dai sai a rotacao da
            cabeca
    corpo   33 pontos em metros, com origem no quadril; servem os ombros,
            cotovelos e pulsos
    maos    21 pontos em metros por mao, com a rotacao da mao embutida

Este modulo junta isso numa pose no espaco do avatar, que e o que a tela
desenha (ver js/avatar/construtor.js):

    metros, origem no meio do peito, y para cima, x para a direita DA TELA,
    z para fora da tela

**O personagem e um espelho.** A mao direita de quem joga aparece do lado
direito da tela, como num espelho — e como a imagem da camera aparecia. Na
imagem crua, x cresce para a direita da camera, y para baixo e z para longe;
o espelho troca o x, e o espaco do avatar troca y e z.

**O corpo do personagem nao e o da pessoa.** Os ombros dele ficam sempre no
mesmo lugar; dos braços da pessoa vem so a direcao e a proporcao, escalada
pela largura dos ombros. A mao vira pata: escalada pelo palmo, para todo mundo
ter a mesma pata, de crianca ou de adulto.

**Nada some de uma vez.** Parte que o MediaPipe perde (braco fora do quadro,
rosto virado) fica no ultimo lugar por meio segundo e depois volta, aos
poucos, para a pose de descanso — em vez de o boneco travar ou se desmontar.
"""

from __future__ import annotations

import math
from typing import Sequence

from autodoc.gestos.cursor import FiltroUmEuro

# O esqueleto fixo do personagem, no espaco dele.
OMBROS = {"esquerdo": (-0.23, 0.30, 0.0), "direito": (0.23, 0.30, 0.0)}
LARGURA_DOS_OMBROS = OMBROS["direito"][0] - OMBROS["esquerdo"][0]

# O palmo da pata (pulso ate a base do medio). Fixo: crianca e adulto ganham a
# mesma pata.
PALMO = 0.17

# Pontos do corpo no MediaPipe: (ombro, cotovelo, pulso) de cada lado DA PESSOA.
# No espelho, o lado direito da pessoa e o lado direito da tela.
BRACOS_MEDIAPIPE = {"direito": (12, 14, 16), "esquerdo": (11, 13, 15)}
LADO_DA_MAO = {"Right": "direita", "Left": "esquerda"}

# Visibilidade minima para confiar num ponto do corpo.
VISIBILIDADE = 0.5

# Quanto tempo uma parte perdida fica no ultimo lugar antes de descansar.
MEMORIA = 0.5

# Limites da cabeca, em graus: alem disto o pescoco do boneco quebraria.
LIMITE_GUINADA = 60
LIMITE_ARFAGEM = 35
LIMITE_ROLAGEM = 40

# As expressoes do MediaPipe nao vao de 0 a 1 certinho: olho aberto ja da 0,05
# e fechado raramente passa de 0,7. Cada uma e reescalada da faixa real (de,
# ate) para 0 a 1.
FAIXAS = {
    "piscar": (0.25, 0.6),
    "boca": (0.05, 0.55),
    "sorriso": (0.1, 0.6),
    "sobrancelhas": (0.1, 0.6),
}

# Para os pontos, o filtro One Euro (o mesmo do cursor), regulado para metros.
CORTE_MINIMO = 1.5
BETA = 8.0


Vetor = tuple[float, float, float]


def para_o_avatar(ponto) -> Vetor:
    """Um ponto em metros da camera crua, nos eixos do avatar, ja espelhado."""
    return (-ponto.x, -ponto.y, -ponto.z)


def _menos(a: Vetor, b: Vetor) -> Vetor:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mais(a: Vetor, b: Vetor) -> Vetor:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vezes(a: Vetor, k: float) -> Vetor:
    return (a[0] * k, a[1] * k, a[2] * k)


def _faixa(valor: float, de: float, ate: float) -> float:
    return min(max((valor - de) / (ate - de), 0.0), 1.0)


# ----------------------------------------------------------------- rosto


def expressoes(nomes: dict[str, float]) -> dict[str, float]:
    """As cinco expressoes que o personagem usa, de 0 a 1."""
    media = lambda *chaves: sum(nomes.get(c, 0.0) for c in chaves) / len(chaves)  # noqa: E731
    return {
        # O piscar do MediaPipe e do olho da pessoa; no espelho, o olho
        # esquerdo dela fica do lado esquerdo da tela.
        "piscar_esquerdo": _faixa(nomes.get("eyeBlinkLeft", 0.0), *FAIXAS["piscar"]),
        "piscar_direito": _faixa(nomes.get("eyeBlinkRight", 0.0), *FAIXAS["piscar"]),
        "boca": _faixa(nomes.get("jawOpen", 0.0), *FAIXAS["boca"]),
        "sorriso": _faixa(media("mouthSmileLeft", "mouthSmileRight"), *FAIXAS["sorriso"]),
        "sobrancelhas": _faixa(
            max(nomes.get("browInnerUp", 0.0), media("browOuterUpLeft", "browOuterUpRight")), *FAIXAS["sobrancelhas"]
        ),
    }


def angulos_da_matriz(matriz: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    """(guinada, arfagem, rolagem) em graus, ja espelhados, da matriz do rosto.

    O espelho e S·R·S com S = diag(-1, 1, 1): troca o sinal das entradas com
    exatamente um indice no eixo x. Os angulos saem na ordem YXZ — a mesma em
    que `quaternion()` os recompoe e em que o three.js gira. Decompor numa
    ordem e recompor em outra distorce a cabeca virada e inclinada ao mesmo
    tempo. Conferido na foto de teste: a inclinacao que sai daqui (-26,2 graus)
    bate com a da linha dos olhos na tela (-26,7).
    """
    r = matriz
    arfagem = math.degrees(math.asin(max(-1.0, min(1.0, -r[1][2]))))
    guinada = math.degrees(math.atan2(-r[0][2], r[2][2]))
    rolagem = math.degrees(math.atan2(-r[1][0], r[1][1]))
    return guinada, arfagem, rolagem


def quaternion(guinada: float, arfagem: float, rolagem: float) -> list[float]:
    """[x, y, z, w] da rotacao em graus, na ordem YXZ, como o construtor espera."""

    def limitar(angulo, limite):
        return math.radians(max(-limite, min(limite, angulo)))

    y = limitar(guinada, LIMITE_GUINADA) / 2
    x = limitar(arfagem, LIMITE_ARFAGEM) / 2
    z = limitar(rolagem, LIMITE_ROLAGEM) / 2
    cy, sy, cx, sx, cz, sz = math.cos(y), math.sin(y), math.cos(x), math.sin(x), math.cos(z), math.sin(z)
    return [
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    ]


# --------------------------------------------------------- braco e mao


def braco(pontos_do_corpo, lado: str) -> dict[str, Vetor] | None:
    """Ombro, cotovelo e pulso do personagem, ou None se o braco nao aparece."""
    indices = BRACOS_MEDIAPIPE[lado]
    if any(getattr(pontos_do_corpo[i], "visibility", 1.0) < VISIBILIDADE for i in indices[1:]):
        return None
    ombro_real, cotovelo_real, pulso_real = (para_o_avatar(pontos_do_corpo[i]) for i in indices)
    largura_real = math.dist(para_o_avatar(pontos_do_corpo[11]), para_o_avatar(pontos_do_corpo[12]))
    escala = LARGURA_DOS_OMBROS / max(largura_real, 1e-3)
    ombro = OMBROS[lado]
    cotovelo = _mais(ombro, _vezes(_menos(cotovelo_real, ombro_real), escala))
    pulso = _mais(ombro, _vezes(_menos(pulso_real, ombro_real), escala))
    return {"ombro": ombro, "cotovelo": cotovelo, "pulso": pulso}


def mao(pontos_da_mao, pulso: Vetor) -> list[Vetor]:
    """Os 21 pontos da pata, presos no pulso do personagem."""
    reais = [para_o_avatar(p) for p in pontos_da_mao]
    palmo = math.dist(reais[0], reais[9])
    escala = PALMO / max(palmo, 1e-4)
    return [_mais(pulso, _vezes(_menos(p, reais[0]), escala)) for p in reais]


# ------------------------------------------------------------ repouso

BRACO_EM_REPOUSO = {
    "esquerdo": {"ombro": OMBROS["esquerdo"], "cotovelo": (-0.31, 0.06, 0.05), "pulso": (-0.27, -0.13, 0.14)},
    "direito": {"ombro": OMBROS["direito"], "cotovelo": (0.31, 0.06, 0.05), "pulso": (0.27, -0.13, 0.14)},
}

# Mao relaxada, pendurada: no espaco da propria mao, pulso na origem e dedos
# para baixo. Ja no tamanho de pata.
_MAO_PARA_BAIXO = [
    (0.0, 0.0, 0.0),
    (0.04, -0.03, 0.02), (0.07, -0.06, 0.035), (0.09, -0.09, 0.045), (0.105, -0.115, 0.05),
    (0.04, -0.16, 0.01), (0.045, -0.21, 0.02), (0.047, -0.245, 0.03), (0.048, -0.27, 0.04),
    (0.008, -0.17, 0.01), (0.008, -0.225, 0.02), (0.008, -0.262, 0.03), (0.008, -0.29, 0.04),
    (-0.025, -0.16, 0.01), (-0.028, -0.21, 0.02), (-0.03, -0.245, 0.03), (-0.031, -0.268, 0.04),
    (-0.052, -0.14, 0.01), (-0.058, -0.178, 0.02), (-0.062, -0.204, 0.03), (-0.065, -0.226, 0.035),
]


def mao_em_repouso(lado: str, pulso: Vetor) -> list[Vetor]:
    # O polegar aponta para o meio do corpo: a mao direita espelha a esquerda.
    sinal = -1 if lado == "direita" else 1
    return [_mais(pulso, (sinal * x, y, z)) for x, y, z in _MAO_PARA_BAIXO]


# -------------------------------------------------------------- juncao


class _Parte:
    """Uma parte do personagem com filtro e memoria."""

    def __init__(self, tamanho: int) -> None:
        self._filtros = [FiltroUmEuro(CORTE_MINIMO, BETA) for _ in range(tamanho)]
        self.ultima: list[float] | None = None
        self.vista_em = -math.inf

    def atualizar(self, valores: list[float] | None, agora: float, repouso: list[float]) -> list[float]:
        if valores is not None:
            self.vista_em = agora
            self.ultima = [filtro(v, agora) for filtro, v in zip(self._filtros, valores)]
            return self.ultima
        if self.ultima is not None and agora - self.vista_em <= MEMORIA:
            return self.ultima
        # Perdida ha tempo: volta para o repouso passando pelo filtro, aos poucos.
        self.ultima = [filtro(v, agora) for filtro, v in zip(self._filtros, repouso)]
        return self.ultima


def _achatar(pontos: Sequence[Vetor]) -> list[float]:
    return [coordenada for ponto in pontos for coordenada in ponto]


def _agrupar(valores: Sequence[float]) -> list[list[float]]:
    return [[round(v, 4) for v in valores[i:i + 3]] for i in range(0, len(valores), 3)]


class PoseDoAvatar:
    """Junta rosto, corpo e maos de cada quadro na pose do personagem."""

    def __init__(self) -> None:
        self._cabeca = _Parte(3)
        self._expressoes = _Parte(5)
        self._bracos = {lado: _Parte(9) for lado in OMBROS}
        self._maos = {lado: _Parte(63) for lado in ("esquerda", "direita")}

    def atualizar(self, rosto, corpo, maos, agora: float) -> dict:
        """Uma pose completa, sempre.

        `rosto` e (expressoes por nome, matriz 4x4) ou None; `corpo`, os 33
        pontos de mundo do PoseLandmarker ou None; `maos`, pares (rotulo,
        pontos de mundo) do HandLandmarker.
        """
        angulos = list(angulos_da_matriz(rosto[1])) if rosto else None
        guinada, arfagem, rolagem = self._cabeca.atualizar(angulos, agora, [0.0, 0.0, 0.0])
        nomes = ("piscar_esquerdo", "piscar_direito", "boca", "sorriso", "sobrancelhas")
        caras = [expressoes(rosto[0])[nome] for nome in nomes] if rosto else None
        valores_cara = self._expressoes.atualizar(caras, agora, [0.0, 0.0, 0.0, 0.25, 0.0])

        bracos = {}
        for lado in OMBROS:
            medido = braco(corpo, lado) if corpo else None
            valores = _achatar(medido.values()) if medido else None
            bracos[lado] = self._bracos[lado].atualizar(valores, agora, _achatar(BRACO_EM_REPOUSO[lado].values()))

        recebidas = {LADO_DA_MAO.get(rotulo): pontos for rotulo, pontos in maos}
        pose_maos = {}
        for lado, lado_braco in (("esquerda", "esquerdo"), ("direita", "direito")):
            pulso = tuple(bracos[lado_braco][6:9])
            medida = _achatar(mao(recebidas[lado], pulso)) if lado in recebidas else None
            pose_maos[lado] = _agrupar(self._maos[lado].atualizar(medida, agora, _achatar(mao_em_repouso(lado, pulso))))

        return {
            "cabeca": {"rotacao": [round(v, 4) for v in quaternion(guinada, arfagem, rolagem)]},
            "expressoes": {nome: round(min(max(v, 0.0), 1.0), 3) for nome, v in zip(nomes, valores_cara)},
            "bracos": {
                lado: dict(zip(("ombro", "cotovelo", "pulso"), _agrupar(valores))) for lado, valores in bracos.items()
            },
            "maos": pose_maos,
        }
