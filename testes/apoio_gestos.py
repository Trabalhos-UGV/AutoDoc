"""Maos sinteticas para os testes de gestos e do Tetris.

O MediaPipe so entrega os 21 pontos da mao; aqui eles sao montados a mao, para
testar o reconhecimento sem camera, sem modelo e sem ninguem na frente dela.
"""

from __future__ import annotations

from types import SimpleNamespace

from autodoc.gestos.reconhecimento import tamanho_da_mao

# x da base, de cada dedo: (base, junta, ponta)
DEDOS = {"indicador": (5, 6, 8, 0.44), "medio": (9, 10, 12, 0.48), "anelar": (13, 14, 16, 0.52), "minimo": (17, 18, 20, 0.56)}


def ponto(x, y, z=0.0):
    return SimpleNamespace(x=x, y=y, z=z)


def montar_mao(abertos=tuple(DEDOS), pinca=None, afastamento=0.0, escala=1.0, girar=False, x=0.0, y=0.0):
    """Uma mao de pe, pulso embaixo, palma para a camera.

    `pinca` encosta o polegar na ponta do "indicador" ou do "medio";
    `afastamento` o afasta dela, em palmas. `escala` aproxima ou afasta a mao
    da camera, `girar` a deita, e `x`/`y` a deslocam no quadro.
    """
    pontos = [ponto(0.5, 0.9) for _ in range(21)]
    for nome, (base, junta, ponta, base_x) in DEDOS.items():
        pontos[base] = ponto(base_x, 0.6)
        pontos[junta] = ponto(base_x, 0.5)
        pontos[ponta] = ponto(base_x, 0.4 if nome in abertos else 0.62)
    pontos[4] = ponto(0.30, 0.70)
    if pinca:
        alvo = pontos[DEDOS[pinca][2]]
        # Afasta para cima, e nao para o lado, para nao chegar perto do dedo vizinho.
        pontos[4] = ponto(alvo.x, alvo.y - afastamento * tamanho_da_mao(pontos))

    pulso = pontos[0]
    resultado = []
    for p in pontos:
        dx, dy = (p.x - pulso.x) * escala, (p.y - pulso.y) * escala
        if girar:
            dx, dy = -dy, dx
        resultado.append(ponto(pulso.x + dx + x, pulso.y + dy + y))
    return resultado
