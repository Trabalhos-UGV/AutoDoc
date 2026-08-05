"""Copia os assets compartilhados para dentro de site/.

A landing precisa ser autocontida para poder ser publicada sozinha (GitHub
Pages, Netlify Drop), entao ela nao consegue referenciar arquivos que vivem em
autodoc/web/estatico/. A fonte da verdade continua sendo aquela pasta; aqui so
copiamos, para as duas nao sairem do lugar uma da outra.

    python3 ferramentas/sincronizar_site.py
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "autodoc" / "web" / "estatico"
DESTINO = RAIZ / "site"

# (caminho relativo dentro de estatico/, e dentro de site/)
COMPARTILHADOS = [
    Path("css/base.css"),
    Path("css/fontes.css"),
    Path("fontes"),
]


def copiar(relativo: Path) -> list[str]:
    origem, destino = ORIGEM / relativo, DESTINO / relativo
    mudou = []

    if origem.is_dir():
        destino.mkdir(parents=True, exist_ok=True)
        for arquivo in sorted(origem.iterdir()):
            if arquivo.is_file():
                alvo = destino / arquivo.name
                if not alvo.exists() or not filecmp.cmp(arquivo, alvo, shallow=False):
                    shutil.copy2(arquivo, alvo)
                    mudou.append(str((relativo / arquivo.name)))
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists() or not filecmp.cmp(origem, destino, shallow=False):
            shutil.copy2(origem, destino)
            mudou.append(str(relativo))

    return mudou


def main() -> None:
    mudou = [m for rel in COMPARTILHADOS for m in copiar(rel)]
    if mudou:
        for caminho in mudou:
            print(f"  atualizado  site/{caminho}")
        print(f"\n{len(mudou)} arquivo(s) sincronizado(s)")
    else:
        print("site/ ja esta em dia com autodoc/web/estatico/")


if __name__ == "__main__":
    main()
