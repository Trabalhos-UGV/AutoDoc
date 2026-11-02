"""Registro do que o AutoDoc faz, no terminal e num arquivo.

Aberto pelo atalho, o AutoDoc nao tem terminal: o aviso de um arquivo que nao
pode ser movido, ou do OCR que falhou, era escrito para ninguem. Agora tambem
vai para um arquivo, no lugar onde cada sistema guarda registro de programa.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

NOME_ARQUIVO = "autodoc.log"

# Um arquivo de 1 MB e mais tres antigos: o bastante para entender um problema
# da semana, sem nunca crescer sem limite.
TAMANHO_MAXIMO = 1_000_000
ARQUIVOS_ANTIGOS = 3


def pasta_de_registro() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "AutoDoc"
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(local) / "AutoDoc" / "logs"
    estado = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(estado) / "autodoc"


def configurar(pasta: Path | None = None) -> Path | None:
    """Liga o registro no terminal e no arquivo. Devolve o arquivo, se deu.

    Nao conseguir criar o arquivo (disco cheio, pasta sem permissao) nao
    impede o programa de abrir: o terminal continua recebendo tudo.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    caminho = (pasta or pasta_de_registro()) / NOME_ARQUIVO
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = RotatingFileHandler(caminho, maxBytes=TAMANHO_MAXIMO,
                                      backupCount=ARQUIVOS_ANTIGOS, encoding="utf-8")
    except OSError:
        logging.getLogger(__name__).warning("sem registro em arquivo em %s", caminho)
        return None

    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(arquivo)
    return caminho
