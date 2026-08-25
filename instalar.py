"""Instalador do AutoDoc.

    python3 instalar.py

Prepara o minimo necessario para a tela de instalacao poder aparecer — o
ambiente virtual e as dependencias — e entao abre o instalador grafico, que
executa as seis etapas e cria o atalho no sistema.

Este arquivo roda com o Python do sistema, sem depender de nada instalado. O
resto do AutoDoc roda dentro do venv.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / "venv"
PYTHON_MINIMO = (3, 10)


def python_do_venv() -> Path:
    if sys.platform.startswith("win"):
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def preparar_ambiente() -> Path:
    """Garante um venv com as dependencias, e devolve o Python dele.

    A tela do instalador precisa de uma janela nativa para aparecer, e a
    janela precisa do pywebview — que so existe depois do pip install. Por
    isso este preparo acontece no terminal, antes de haver tela.
    """
    python = python_do_venv()

    if not python.exists():
        print("Criando o ambiente virtual...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        python = python_do_venv()

    pronto = subprocess.run(
        [str(python), "-c", "import webview, watchdog"], capture_output=True
    )
    if pronto.returncode != 0:
        print("Instalando as dependências (pode levar um minuto)...")
        subprocess.run(
            [str(python), "-m", "pip", "install", "-q", "-r",
             str(RAIZ / "requirements.txt")],
            check=True,
        )

    return python


def main() -> int:
    if sys.version_info[:2] < PYTHON_MINIMO:
        exigido = ".".join(str(n) for n in PYTHON_MINIMO)
        atual = ".".join(str(n) for n in sys.version_info[:3])
        print(f"O AutoDoc precisa do Python {exigido} ou mais novo (aqui é o {atual}).")
        return 1

    try:
        python = preparar_ambiente()
    except subprocess.CalledProcessError as erro:
        print(f"Não foi possível preparar o ambiente: {erro}")
        return 1

    # A partir daqui quem manda e o Python do venv, que tem as dependencias.
    return subprocess.run(
        [str(python), "-m", "autodoc.instalacao.principal"], cwd=str(RAIZ)
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
