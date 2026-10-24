"""Baixa os personagens do Tetris (Fluent Emoji 3D, da Microsoft) para uso local.

O AutoDoc roda offline, entao os PNGs ficam versionados junto com o projeto,
como as fontes. Fluent Emoji e licenca MIT, que permite redistribuir; a licenca
vai junto, na mesma pasta.

Rode uma vez; o resultado e versionado. So precisa rodar de novo para mudar a
lista em autodoc/gestos/personagens.py.

    python3 ferramentas/baixar_personagens.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from autodoc.gestos.personagens import PASTA, PERSONAGENS, arquivo  # noqa: E402

BASE = "https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@main"


def buscar(url: str) -> bytes:
    """Baixa via curl.

    O Python distribuido pelo python.org nao instala a cadeia de certificados
    no macOS, entao urllib falha no handshake TLS. O curl do sistema resolve.
    """
    return subprocess.run(["curl", "-sSfL", url], capture_output=True, check=True).stdout


def main() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    for nome, _, pasta in PERSONAGENS:
        # As pastas do Fluent tem espaco ("Dog face"); os arquivos, sublinhado.
        url = f"{BASE}/assets/{quote(pasta)}/3D/{pasta.lower().replace(' ', '_')}_3d.png"
        dados = buscar(url)
        arquivo(nome).write_bytes(dados)
        print(f"{nome:<10} {len(dados) // 1024:>3} KB")
    (PASTA / "LICENCA-fluent-emoji.txt").write_bytes(buscar(f"{BASE}/LICENSE"))
    print("licença MIT salva")


if __name__ == "__main__":
    main()
