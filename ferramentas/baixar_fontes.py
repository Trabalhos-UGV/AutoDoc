"""Baixa Space Grotesk e JetBrains Mono do Google Fonts para uso local.

O AutoDoc roda offline, entao nada de CDN: as fontes ficam versionadas junto
com o projeto. Ambas sao SIL Open Font License 1.1, que permite redistribuir.

Rode uma vez; o resultado (os .woff2 e o fontes.css) e versionado. So precisa
rodar de novo para atualizar as fontes.

    python3 ferramentas/baixar_fontes.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "autodoc" / "web" / "estatico" / "fontes"
CSS = RAIZ / "autodoc" / "web" / "estatico" / "css" / "fontes.css"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
URL_CSS = ("https://fonts.googleapis.com/css2"
           "?family=Space+Grotesk:wght@400;500;600;700"
           "&family=JetBrains+Mono:wght@400;500;700&display=swap")

# Portugues cabe em latin + latin-ext; os demais subsets sao peso morto.
SUBSETS = ("latin", "latin-ext")

# O Google serve estas duas como fontes variaveis: um unico arquivo por subset
# cobre todos os pesos. Por isso o @font-face declara uma FAIXA de peso — com
# peso fixo o navegador ignoraria os eixos e sintetizaria o negrito.
FAMILIAS = {
    "Space Grotesk": dict(apelido="space-grotesk", faixa="300 700"),
    "JetBrains Mono": dict(apelido="jetbrains-mono", faixa="100 800"),
}

CABECALHO = """/* Fontes locais — o AutoDoc funciona sem internet, entao nada de CDN.
   Space Grotesk e JetBrains Mono, SIL Open Font License 1.1.

   Sao fontes VARIAVEIS: um arquivo por subset cobre a faixa inteira de pesos.
   Gerado por ferramentas/baixar_fontes.py — nao editar a mao. */

"""


def buscar(url: str) -> bytes:
    """Baixa via curl.

    O Python distribuido pelo python.org nao instala a cadeia de certificados
    no macOS, entao urllib falha no handshake TLS. O curl do sistema resolve.
    """
    return subprocess.run(
        ["curl", "-sSfL", "-A", UA, url], capture_output=True, check=True
    ).stdout


def main() -> None:
    FONTES.mkdir(parents=True, exist_ok=True)
    CSS.parent.mkdir(parents=True, exist_ok=True)

    css = buscar(URL_CSS).decode("utf-8")
    blocos = re.findall(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})", css)

    # (familia, subset) -> (url, unicode-range); pesos diferentes repetem a url
    encontrados: dict[tuple[str, str], tuple[str, str]] = {}
    for subset, bloco in blocos:
        if subset not in SUBSETS:
            continue
        familia = re.search(r"font-family:\s*'([^']+)'", bloco).group(1)
        url = re.search(r"url\((https://[^)]+)\)", bloco).group(1)
        faixa = re.search(r"unicode-range:\s*([^;]+);", bloco)
        encontrados.setdefault(
            (familia, subset), (url, faixa.group(1).strip() if faixa else "")
        )

    regras = []
    for (familia, subset), (url, unicode_range) in sorted(encontrados.items()):
        info = FAMILIAS[familia]
        nome = f"{info['apelido']}-{subset}.woff2"
        destino = FONTES / nome
        destino.write_bytes(buscar(url))
        print(f"  {nome:34} {destino.stat().st_size / 1024:6.1f} KB")

        regras.append(
            "@font-face {\n"
            f"  font-family: '{familia}';\n"
            "  font-style: normal;\n"
            f"  font-weight: {info['faixa']};\n"
            "  font-display: swap;\n"
            f"  src: url('../fontes/{nome}') format('woff2');\n"
            + (f"  unicode-range: {unicode_range};\n" if unicode_range else "")
            + "}"
        )

    CSS.write_text(CABECALHO + "\n\n".join(regras) + "\n", encoding="utf-8")
    total = sum(f.stat().st_size for f in FONTES.glob("*.woff2"))
    print(f"\n{len(regras)} regras @font-face -> {CSS.relative_to(RAIZ)}")
    print(f"{len(list(FONTES.glob('*.woff2')))} arquivos, {total / 1024:.1f} KB")


if __name__ == "__main__":
    main()
