"""Baixa o three.js para uso local, sem CDN.

O avatar 3D do Tetris e desenhado com three.js (licenca MIT). O AutoDoc roda
offline, entao o modulo fica versionado junto com o projeto, como as fontes.

A versao e fixa de proposito: a 0.169 e a ultima distribuida num arquivo so; a
partir da 0.171 o modulo se divide em dois. Trocar de versao e decisao, nao
atualizacao automatica.

    python3 ferramentas/baixar_three.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "autodoc" / "web" / "estatico" / "vendor" / "three"

VERSAO = "0.169.0"
BASE = f"https://cdn.jsdelivr.net/npm/three@{VERSAO}"

ARQUIVOS = {
    "three.module.min.js": "build/three.module.min.js",
    # O "estudio" que reflete nos materiais: sem ele tudo fica fosco e chapado.
    "RoomEnvironment.js": "examples/jsm/environments/RoomEnvironment.js",
    "LICENCA-three.txt": "LICENSE",
}


def buscar(url: str) -> bytes:
    """Baixa via curl.

    O Python distribuido pelo python.org nao instala a cadeia de certificados
    no macOS, entao urllib falha no handshake TLS. O curl do sistema resolve.
    """
    return subprocess.run(["curl", "-sSfL", url], capture_output=True, check=True).stdout


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, caminho in ARQUIVOS.items():
        dados = buscar(f"{BASE}/{caminho}")
        (DESTINO / nome).write_bytes(dados)
        print(f"{nome:<22} {len(dados) // 1024:>4} KB")


if __name__ == "__main__":
    main()
