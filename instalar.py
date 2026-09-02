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

ESSENCIAIS = RAIZ / "requirements-essenciais.txt"
COMPLETO = RAIZ / "requirements.txt"


def python_do_venv() -> Path:
    if sys.platform.startswith("win"):
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def opcoes_do_venv() -> list[str]:
    """Opcoes extras na criacao do ambiente virtual.

    **No Linux o venv precisa enxergar os pacotes do sistema.** O motor da
    janela nativa la e o WebKitGTK, alcancado pelo `gi` (PyGObject), e os dois
    vem do gerenciador da distribuicao — `pacman -S python-gobject`,
    `apt install python3-gi`. Um venv comum e isolado e nao ve nada disso, entao
    o pywebview instalado por dentro dele nunca acha motor e a janela nao abre,
    por mais que os pacotes certos estejam no sistema.

    Quem tenta resolver isso pelo pip cai em `pywebview[gtk]`, que compila o
    PyGObject do zero e falha sem gobject-introspection, cairo e pkgconf. Era
    esse o beco.

    O que o venv instala continua vindo antes do que o sistema tem: o
    `site-packages` do proprio ambiente vem primeiro no caminho de busca.
    """
    if sys.platform.startswith("linux"):
        return ["--system-site-packages"]
    return []


CHAVE_SISTEMA = "include-system-site-packages"


def abrir_venv_ao_sistema(venv: Path = VENV) -> bool:
    """Faz um ambiente virtual ja existente enxergar os pacotes do sistema.

    Um venv criado antes desta correcao esta isolado, e no Linux isso e o que
    impede o pywebview de achar o `gi` que o gerenciador da distribuicao
    instalou. Sem isto, quem instalasse o `python-gobject` continuaria sem
    janela e sem entender por que — o conserto pedia apagar o venv e comecar
    de novo, que e um passo facil de esquecer e chato de descobrir.

    O `pyvenv.cfg` e lido pelo interpretador a cada partida, entao virar a
    chave ali equivale a ter criado o ambiente com `--system-site-packages`.
    Nada e reinstalado. O que o venv tem continua vindo antes do sistema.

    Devolve True quando mudou alguma coisa.
    """
    configuracao = venv / "pyvenv.cfg"
    if not configuracao.exists():
        return False

    linhas = configuracao.read_text(encoding="utf-8").splitlines()
    mudou = False
    for indice, linha in enumerate(linhas):
        chave, separador, valor = linha.partition("=")
        if separador and chave.strip() == CHAVE_SISTEMA:
            if valor.strip().lower() != "true":
                linhas[indice] = f"{CHAVE_SISTEMA} = true"
                mudou = True
            break
    else:
        linhas.append(f"{CHAVE_SISTEMA} = true")
        mudou = True

    if mudou:
        configuracao.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return mudou


def preparar_ambiente() -> Path:
    """Garante um venv com as dependencias, e devolve o Python dele.

    A tela do instalador precisa de uma janela nativa para aparecer, e a
    janela precisa do pywebview — que so existe depois do pip install. Por
    isso este preparo acontece no terminal, antes de haver tela.
    """
    python = python_do_venv()

    if not python.exists():
        print("Criando o ambiente virtual...")
        subprocess.run(
            [sys.executable, "-m", "venv", *opcoes_do_venv(), str(VENV)], check=True
        )
        python = python_do_venv()
    elif sys.platform.startswith("linux") and abrir_venv_ao_sistema():
        # Ambiente criado por uma versao anterior, quando o venv nascia
        # isolado. Sem isto o pywebview nunca acharia o motor do sistema.
        print("Ambiente virtual ajustado para enxergar os pacotes do sistema.")

    def tem(modulos: str) -> bool:
        return subprocess.run(
            [str(python), "-c", f"import {modulos}"], capture_output=True
        ).returncode == 0

    # Primeiro o que o AutoDoc nao dispensa. Falhar aqui e falhar de verdade.
    if not tem("watchdog, pypdf"):
        print("Instalando as dependências (pode levar um minuto)...")
        subprocess.run(
            [str(python), "-m", "pip", "install", "-q", "-r", str(ESSENCIAIS)],
            check=True,
        )

    # Depois o resto, no melhor esforco. A janela nativa e o OCR sao recursos,
    # nao requisitos: uma dessas falhando nao pode impedir alguem de instalar o
    # programa — foi o que aconteceu no Linux, onde a instalacao inteira
    # abortava por causa da parte grafica.
    if not tem("webview") or not tem("pytesseract"):
        print("Instalando os recursos opcionais...")
        resultado = subprocess.run(
            [str(python), "-m", "pip", "install", "-q", "-r", str(COMPLETO)],
            capture_output=True, text=True,
        )
        if resultado.returncode != 0:
            print("  Nem tudo pôde ser instalado — o AutoDoc funciona assim mesmo.")
            print(f"  {_ultima_linha(resultado.stderr or resultado.stdout)}")
            if not tem("webview"):
                print("  A janela nativa não estará disponível; as telas abrem no navegador.")

    return python


def _ultima_linha(saida: str) -> str:
    """A ultima linha util do pip — a que diz o que aconteceu de fato."""
    linhas = [l.strip() for l in (saida or "").splitlines() if l.strip()]
    return linhas[-1][:160] if linhas else "sem detalhes"


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
