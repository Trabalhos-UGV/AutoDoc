"""Instalador do AutoDoc.

    python3 instalar.py

Um comando so. Ele descobre o sistema (macOS, Linux ou Windows), instala os
programas do sistema que faltarem — o Tesseract com o portugues para ler fotos
e, no Linux, o motor da janela —, prepara o ambiente virtual com as
dependencias e entao abre o instalador grafico, que executa as seis etapas e
cria o atalho no sistema.

Programa do sistema precisa de permissao de administrador, e e por isso que ele
e instalado aqui, no terminal, antes de haver tela: e no terminal que o `sudo`
pede a senha. Nada disso e obrigatorio — o que nao instalar e avisado, com o
comando para fazer a mao, e a instalacao continua.

Este arquivo roda com o Python do sistema, sem depender de nada instalado. O
resto do AutoDoc roda dentro do venv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
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


def abrir_venv_ao_sistema(venv: Path | None = None) -> bool:
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
    # Resolvido aqui, e nao no valor padrao do parametro: um padrao e avaliado
    # na definicao da funcao e ficaria preso ao VENV daquele instante.
    configuracao = (venv or VENV) / "pyvenv.cfg"
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


# ------------------------------------------------- programas do sistema

# Por gerenciador de pacotes do Linux: como instalar sem perguntar, os pacotes
# do OCR em portugues e os do motor da janela. Os do motor repetem
# `PACOTES_DO_MOTOR` de autodoc/web/janela.py, que este arquivo nao pode
# importar; um teste compara os dois.
GERENCIADORES_LINUX = {
    "pacman": (["pacman", "-S", "--needed", "--noconfirm"],
               ["tesseract", "tesseract-data-por"], ["python-gobject", "webkit2gtk-4.1"]),
    "apt-get": (["apt-get", "install", "-y"],
                ["tesseract-ocr", "tesseract-ocr-por"], ["python3-gi", "gir1.2-webkit2-4.1"]),
    "dnf": (["dnf", "install", "-y"],
            ["tesseract", "tesseract-langpack-por"], ["python3-gobject", "webkit2gtk4.1"]),
    "zypper": (["zypper", "--non-interactive", "install"],
               ["tesseract-ocr", "tesseract-ocr-traineddata-portuguese"],
               ["python3-gobject", "typelib-1_0-WebKit2-4_1"]),
}

# Ubuntu 20.04 e Debian 11 ainda nao tem o WebKitGTK 4.1.
ALTERNATIVAS_APT = {"gir1.2-webkit2-4.1": "gir1.2-webkit2-4.0"}

BREW = ("/opt/homebrew/bin/brew", "/usr/local/bin/brew")
INSTALADOR_HOMEBREW = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

# O pacote do Tesseract no winget e o do UB Mannheim, que instala so o ingles.
# O portugues vai para uma pasta da propria pessoa, que nao pede administrador;
# o AutoDoc aponta o Tesseract para ela (ver `extrator._achar_tesseract_no_windows`).
WINGET_TESSERACT = "UB-Mannheim.TesseractOCR"
PORTUGUES_TESSERACT = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata"
PASTAS_TESSERACT_WINDOWS = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR",
    Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
    / "Programs" / "Tesseract-OCR",
)


def tessdata_do_usuario() -> Path:
    local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(local) / "AutoDoc" / "tessdata"


def achar_tesseract() -> str | None:
    """O executavel do Tesseract, tambem onde o instalador do Windows o deixa."""
    if shutil.which("tesseract"):
        return shutil.which("tesseract")
    if sys.platform.startswith("win"):
        for pasta in PASTAS_TESSERACT_WINDOWS:
            if (pasta / "tesseract.exe").is_file():
                return str(pasta / "tesseract.exe")
    return None


def le_portugues(tesseract: str) -> bool:
    ambiente = dict(os.environ)
    if sys.platform.startswith("win") and (tessdata_do_usuario() / "por.traineddata").is_file():
        ambiente["TESSDATA_PREFIX"] = str(tessdata_do_usuario())
    saida = subprocess.run([tesseract, "--list-langs"], capture_output=True, text=True, env=ambiente)
    # Versoes antigas listam os idiomas no stderr.
    idiomas = (saida.stdout + saida.stderr).split()
    return "por" in idiomas


def tem_motor_da_janela() -> bool:
    """O `gi` com o WebKitGTK, que e o que a janela nativa usa no Linux."""
    for versao in ("4.1", "4.0"):
        teste = f"import gi; gi.require_version('WebKit2', '{versao}'); from gi.repository import WebKit2"
        if subprocess.run([sys.executable, "-c", teste], capture_output=True).returncode == 0:
            return True
    return False


def perguntar(pergunta: str) -> bool:
    """Sim por padrao; sem terminal para responder, nao."""
    if not sys.stdin.isatty():
        return False
    try:
        resposta = input(f"{pergunta} [S/n] ").strip().lower()
    except EOFError:
        return False
    return resposta in ("", "s", "sim", "y", "yes")


def _rodar(comando: list[str]) -> bool:
    print("  $ " + " ".join(comando))
    try:
        return subprocess.run(comando).returncode == 0
    except OSError as erro:
        print(f"  não deu para rodar: {erro}")
        return False


def _como_administrador(comando: list[str]) -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return comando
    return ["sudo", *comando] if shutil.which("sudo") else comando


def _instalar_no_linux(faltando: dict[str, bool]) -> list[str]:
    gerenciador = next((g for g in GERENCIADORES_LINUX if shutil.which(g)), None)
    if gerenciador is None:
        return ["não reconheci o gerenciador de pacotes desta distribuição"]

    instalar, ocr, janela = GERENCIADORES_LINUX[gerenciador]
    pacotes = (ocr if faltando["ocr"] else []) + (janela if faltando["janela"] else [])
    print(f"Instalando pelo {gerenciador} (o sudo pode pedir a sua senha): {' '.join(pacotes)}")

    if gerenciador == "apt-get":
        # Num sistema recem-instalado a lista de pacotes esta vazia.
        _rodar(_como_administrador(["apt-get", "update"]))
    if _rodar(_como_administrador([*instalar, *pacotes])):
        return []

    trocados = [ALTERNATIVAS_APT.get(p, p) for p in pacotes] if gerenciador == "apt-get" else pacotes
    if trocados != pacotes and _rodar(_como_administrador([*instalar, *trocados])):
        return []
    return [f"o {gerenciador} não instalou: sudo {' '.join([*instalar, *pacotes])}"]


def _achar_brew() -> str | None:
    return shutil.which("brew") or next((b for b in BREW if Path(b).is_file()), None)


def _instalar_no_macos(faltando: dict[str, bool]) -> list[str]:
    brew = _achar_brew()
    if brew is None:
        print("O Tesseract no macOS vem pelo Homebrew, que não está instalado.")
        if not perguntar("Instalar o Homebrew agora (pede a senha do Mac)?"):
            return ["sem Homebrew: instale-o em https://brew.sh e rode este instalador de novo"]
        script = subprocess.run(["curl", "-fsSL", INSTALADOR_HOMEBREW],
                                capture_output=True, text=True)
        if script.returncode != 0 or not _rodar_script_homebrew(script.stdout):
            return ["o Homebrew não instalou: veja https://brew.sh"]
        brew = _achar_brew()
        if brew is None:
            return ["o Homebrew instalou, mas não o achei: abra um terminal novo e rode de novo"]

    print("Instalando o Tesseract com o português pelo Homebrew...")
    if _rodar([brew, "install", "tesseract", "tesseract-lang"]):
        return []
    return ["o Homebrew não instalou: brew install tesseract tesseract-lang"]


def _rodar_script_homebrew(script: str) -> bool:
    print("  $ /bin/bash -c \"$(curl -fsSL " + INSTALADOR_HOMEBREW + ")\"")
    return subprocess.run(["/bin/bash", "-c", script]).returncode == 0


def baixar(url: str, destino: Path) -> bool:
    """Baixa um arquivo. O curl vem no Windows 10 e no macOS, e tem a cadeia de
    certificados do sistema — o urllib do Python do python.org nao tem."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        return _rodar(["curl", "-fsSL", "-o", str(destino), url])
    try:
        urllib.request.urlretrieve(url, destino)
    except OSError as erro:
        print(f"  não deu para baixar {url}: {erro}")
        return False
    return True


def _instalar_no_windows(faltando: dict[str, bool]) -> list[str]:
    if faltando["tesseract"]:
        winget = shutil.which("winget")
        if winget is None:
            return ["sem o winget: baixe o Tesseract em https://github.com/UB-Mannheim/tesseract/wiki"]
        print("Instalando o Tesseract pelo winget (o Windows pode pedir permissão)...")
        if not _rodar([winget, "install", "-e", "--id", WINGET_TESSERACT,
                       "--accept-package-agreements", "--accept-source-agreements"]):
            return ["o winget não instalou: winget install -e --id " + WINGET_TESSERACT]

    tesseract = achar_tesseract()
    if tesseract is None:
        return ["o Tesseract instalou, mas não o achei: rode este instalador de novo"]
    if le_portugues(tesseract):
        return []

    # Os idiomas que ja vieram vao junto, porque o Tesseract le todos de uma
    # pasta so — apontado para a pasta nova, ele perderia o ingles.
    destino = tessdata_do_usuario()
    destino.mkdir(parents=True, exist_ok=True)
    for idioma in (Path(tesseract).parent / "tessdata").glob("*.traineddata"):
        shutil.copy2(idioma, destino / idioma.name)
    print("Baixando o português do Tesseract...")
    if baixar(PORTUGUES_TESSERACT, destino / "por.traineddata"):
        return []
    return [f"o português não baixou: salve {PORTUGUES_TESSERACT} em {destino}"]


def o_que_falta() -> dict[str, bool]:
    tesseract = achar_tesseract()
    return {
        "tesseract": tesseract is None,
        "ocr": tesseract is None or not le_portugues(tesseract),
        "janela": sys.platform.startswith("linux") and not tem_motor_da_janela(),
    }


def instalar_programas_do_sistema() -> list[str]:
    """Instala o que falta fora do Python. Devolve o que ficou pendente.

    Nunca interrompe a instalacao: o AutoDoc funciona sem OCR (as fotos
    esperam) e sem janela nativa (as telas abrem no navegador).
    """
    faltando = o_que_falta()
    if not faltando["ocr"] and not faltando["janela"]:
        print("Tesseract com português" + (" e motor da janela" if sys.platform.startswith("linux") else "")
              + ": já instalados.")
        return []

    if sys.platform.startswith("linux"):
        pendente = _instalar_no_linux(faltando)
    elif sys.platform == "darwin":
        pendente = _instalar_no_macos(faltando)
    elif sys.platform.startswith("win"):
        pendente = _instalar_no_windows(faltando)
    else:
        pendente = [f"não sei instalar programas em {sys.platform}"]

    for aviso in pendente:
        print(f"  Ficou faltando — {aviso}. O AutoDoc funciona assim mesmo.")
    return pendente


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

    instalar_programas_do_sistema()

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
