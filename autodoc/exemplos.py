"""Os documentos de exemplo, copiados para a pasta vigiada.

`exemplos/` fica no repositorio como fonte: e versionada, vai para o GitHub e
nunca e vigiada direto — o AutoDoc tira da pasta vigiada o que organiza, e foi
assim que `exemplos/` se esvaziou uma vez. O que vai para a pasta vigiada e uma
**copia**, feita pelo instalador na primeira vez (para o AutoDoc abrir ja com
algo a mostrar) e por `python main.py exemplos` quando se quiser apresentar de
novo.

Vai tudo, inclusive a pasta de projeto e o `.zip`: eles estao ali para mostrar
que o AutoDoc nao mexe no que nao e documento solto.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .catalogo import PASTA_CATALOGO

PASTA_EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"

# O leia-me e para quem abre o repositorio, nao um documento da demonstracao.
FORA_DA_COPIA = {"LEIA-ME.md"}

# Marca, dentro da pasta organizada, de que a copia da instalacao ja foi feita:
# reinstalar nao pode encher a pasta de novo com o que ja foi organizado.
MARCA = "exemplos-copiados"


def copiar(destino: Path, origem: Path = PASTA_EXEMPLOS) -> list[Path]:
    """Copia os exemplos para `destino`, sem sobrescrever nada que ja esteja la."""
    copiados = []
    if not origem.is_dir():
        return copiados
    destino.mkdir(parents=True, exist_ok=True)
    for item in sorted(origem.iterdir()):
        if item.name in FORA_DA_COPIA or item.name.startswith("."):
            continue
        alvo = destino / item.name
        if alvo.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, alvo)
        else:
            shutil.copy2(item, alvo)
        copiados.append(alvo)
    return copiados


def copiar_na_instalacao(pasta_entrada: Path, pasta_saida: Path,
                         origem: Path = PASTA_EXEMPLOS) -> list[Path] | None:
    """A copia da primeira instalacao. None se ela ja foi feita antes."""
    marca = pasta_saida / PASTA_CATALOGO / MARCA
    if marca.exists():
        return None
    copiados = copiar(pasta_entrada, origem)
    marca.parent.mkdir(parents=True, exist_ok=True)
    marca.write_text("\n".join(c.name for c in copiados) + "\n", encoding="utf-8")
    return copiados
