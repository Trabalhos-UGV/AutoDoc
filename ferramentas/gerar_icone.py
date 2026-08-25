"""Gera o icone do AutoDoc nos formatos que cada sistema exige.

O icone e a marca do projeto: quadrado amarelo de cantos arredondados com um
"A" escuro no meio, o mesmo que aparece na landing e na barra lateral do app.

O "A" e desenhado por geometria, e nao escrito com uma fonte. As fontes do
projeto estao em .woff2, formato que as bibliotecas de imagem nao leem, e
depender de alguma fonte instalada na maquina faria o icone sair diferente em
cada computador.

    python3 ferramentas/gerar_icone.py

Os arquivos gerados sao versionados; so precisa rodar de novo se a marca mudar.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RECURSOS = RAIZ / "recursos"

LADO = 1024
AMARELO = (240, 193, 42, 255)   # --ad-acento
ESCURO = (17, 15, 11, 255)      # --ad-fundo

# Tamanhos que o macOS espera dentro de um .icns, e que o .ico do Windows
# tambem aproveita.
TAMANHOS = (16, 32, 64, 128, 256, 512, 1024)


def desenhar(lado: int = LADO):
    """Devolve a imagem do icone no tamanho pedido."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise SystemExit(
            "Pillow e necessario para gerar o icone: pip install -r requirements.txt"
        )

    imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)

    # Quadrado de cantos arredondados, na proporcao da marca (raio ~26%).
    desenho.rounded_rectangle(
        [(0, 0), (lado - 1, lado - 1)], radius=int(lado * 0.26), fill=AMARELO
    )

    # O "A": duas pernas partindo do apice e uma travessa.
    u = lado / 100  # trabalhar em porcentagem do lado deixa tudo proporcional
    apice = (50 * u, 24 * u)
    esquerda = (26 * u, 78 * u)
    direita = (74 * u, 78 * u)
    espessura = int(9 * u)

    desenho.line([esquerda, apice], fill=ESCURO, width=espessura, joint="curve")
    desenho.line([apice, direita], fill=ESCURO, width=espessura, joint="curve")
    # Cantos redondos nas pontas, para o traco nao terminar em bisel.
    for ponto in (apice, esquerda, direita):
        raio = espessura / 2
        desenho.ellipse(
            [ponto[0] - raio, ponto[1] - raio, ponto[0] + raio, ponto[1] + raio],
            fill=ESCURO,
        )

    desenho.line(
        [(35 * u, 60 * u), (65 * u, 60 * u)],
        fill=ESCURO,
        width=int(8 * u),
    )

    return imagem


def gerar_png(imagem, destino: Path, lado: int) -> None:
    imagem.resize((lado, lado)).save(destino)


def gerar_icns(imagem, destino: Path) -> bool:
    """Monta o .icns do macOS com o iconutil, que ja vem no sistema."""
    if sys.platform != "darwin" or not shutil.which("iconutil"):
        return False

    with tempfile.TemporaryDirectory() as temporario:
        conjunto = Path(temporario) / "autodoc.iconset"
        conjunto.mkdir()

        # O iconutil exige exatamente estes nomes.
        for lado in (16, 32, 128, 256, 512):
            gerar_png(imagem, conjunto / f"icon_{lado}x{lado}.png", lado)
            gerar_png(imagem, conjunto / f"icon_{lado}x{lado}@2x.png", lado * 2)

        subprocess.run(
            ["iconutil", "-c", "icns", str(conjunto), "-o", str(destino)],
            check=True,
        )
    return True


def gerar_ico(imagem, destino: Path) -> None:
    """Um .ico guarda varios tamanhos num arquivo so."""
    imagem.save(destino, sizes=[(t, t) for t in TAMANHOS if t <= 256])


def main() -> None:
    RECURSOS.mkdir(exist_ok=True)
    imagem = desenhar()

    gerar_png(imagem, RECURSOS / "autodoc.png", 512)
    print(f"  recursos/autodoc.png       {(RECURSOS / 'autodoc.png').stat().st_size // 1024} KB")

    gerar_ico(imagem, RECURSOS / "autodoc.ico")
    print(f"  recursos/autodoc.ico       {(RECURSOS / 'autodoc.ico').stat().st_size // 1024} KB")

    if gerar_icns(imagem, RECURSOS / "autodoc.icns"):
        print(f"  recursos/autodoc.icns      {(RECURSOS / 'autodoc.icns').stat().st_size // 1024} KB")
    else:
        print("  .icns nao gerado (precisa do iconutil, que so existe no macOS)")


if __name__ == "__main__":
    main()
