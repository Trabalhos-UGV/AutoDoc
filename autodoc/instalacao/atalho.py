"""Cria o atalho do AutoDoc no sistema.

E o que separa "um programa que roda" de "um programa instalado": depois disto
o AutoDoc aparece junto com os outros aplicativos e abre por um clique no
icone, sem ninguem precisar lembrar de um comando.

Cada sistema tem seu jeito, e nenhum deles precisa de biblioteca extra:

    macOS    um pacote .app em ~/Applications — e so uma pasta com um formato
             combinado, entao da para montar na mao
    Windows  um .lnk criado pelo Windows Script Host, via powershell
    Linux    um arquivo .desktop em ~/.local/share/applications
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
RECURSOS = RAIZ / "recursos"

NOME = "AutoDoc"
IDENTIFICADOR = "br.edu.ugv.autodoc"
DESCRICAO = "Organização automática de documentos"


@dataclass
class Atalho:
    """Onde o atalho foi criado, e se deu certo."""

    caminho: Path | None
    criado: bool
    detalhe: str


def _python_do_projeto() -> Path:
    """O interpretador que deve rodar o AutoDoc.

    Prefere o venv do projeto ao Python que estiver rodando este script: o
    atalho vai ser clicado meses depois, fora de qualquer ambiente ativado.
    """
    for relativo in ("venv/bin/python", "venv/Scripts/pythonw.exe", "venv/Scripts/python.exe"):
        candidato = RAIZ / relativo
        if candidato.exists():
            return candidato
    return Path(sys.executable)


def criar(destino_base: Path | None = None) -> Atalho:
    """Cria o atalho para o sistema atual."""
    if sys.platform == "darwin":
        return _criar_macos(destino_base)
    if sys.platform.startswith("win"):
        return _criar_windows(destino_base)
    return _criar_linux(destino_base)


# ------------------------------------------------------------------ macOS

CAMERA = "O AutoDoc usa a câmera para reconhecer os gestos da sua mão no Tetris e no controle por gestos."

# O Tetris precisa da camera, e o macOS decide a permissao pelo app
# *responsavel* pelo processo. A primeira versao do pacote tinha um script como
# executavel, e o script fazia `exec` no Python: a partir dali o responsavel era
# o proprio Python (`org.python.python`), cujo Info.plist nao declara camera — e
# o macOS recusava em silencio, sem nem perguntar.
#
# Agora o executavel e um "applet" do `osacompile`: binario nativo, assinado
# pela Apple, presente em todo Mac. Ele fica vivo, invisivel, e abre o Python
# como *filho*. Filho herda o responsavel, e o responsavel passa a ser o
# AutoDoc, com a frase de `CAMERA` no Info.plist. Quando o AutoDoc fecha, o
# applet percebe e sai junto.
APPLET = """property processo : ""

on run
	set abrir to POSIX path of (path to me) & "Contents/Resources/abrir.sh"
	set processo to do shell script quoted form of abrir & " > /dev/null 2>&1 & echo $!"
end run

on idle
	try
		do shell script "kill -0 " & processo
	on error
		quit
	end try
	return 2
end idle
"""


def _script_de_abertura() -> str:
    """O que efetivamente abre o AutoDoc, chamado pelo applet (ou pelo pacote antigo).

    `arch -arm64` porque o macOS abria o app pelo Rosetta num Mac com chip
    Apple, e os pacotes compilados so para Apple Silicon (numpy, OpenCV,
    MediaPipe) nao carregavam. `hw.optional.arm64` responde 1 no chip Apple
    mesmo de dentro do Rosetta.
    """
    python = _python_do_projeto()
    return (
        "#!/bin/bash\n"
        f'cd "{RAIZ}"\n'
        # A janela le isto para se apresentar como AutoDoc no Dock, e nao como Python.
        "export AUTODOC_PELO_ICONE=1\n"
        'if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then\n'
        f'    exec arch -arm64 "{python}" main.py app\n'
        "fi\n"
        f'exec "{python}" main.py app\n'
    )


def _e_nosso(pacote: Path) -> bool:
    try:
        dados = plistlib.loads((pacote / "Contents" / "Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return False
    return dados.get("CFBundleIdentifier") == IDENTIFICADOR


def _criar_macos(destino_base: Path | None) -> Atalho:
    base = destino_base or (Path.home() / "Applications")
    base.mkdir(parents=True, exist_ok=True)
    pacote = base / f"{NOME}.app"

    if pacote.exists():
        # So apaga o que foi o proprio AutoDoc que criou.
        if not _e_nosso(pacote):
            return Atalho(pacote, False, f"ja existe um {NOME}.app que nao e deste projeto; nada foi mudado")
        shutil.rmtree(pacote)

    com_applet = shutil.which("osacompile") is not None
    if com_applet:
        subprocess.run(["osacompile", "-s", "-o", str(pacote), "-e", APPLET], check=True, capture_output=True)

    conteudo = pacote / "Contents"
    recursos = conteudo / "Resources"
    (conteudo / "MacOS").mkdir(parents=True, exist_ok=True)
    recursos.mkdir(parents=True, exist_ok=True)

    abrir = recursos / "abrir.sh" if com_applet else conteudo / "MacOS" / NOME
    abrir.write_text(_script_de_abertura(), encoding="utf-8")
    abrir.chmod(0o755)

    caminho_plist = conteudo / "Info.plist"
    informacoes = plistlib.loads(caminho_plist.read_bytes()) if com_applet else {}
    informacoes.update({
        "CFBundleName": NOME,
        "CFBundleDisplayName": NOME,
        "CFBundleIdentifier": IDENTIFICADOR,
        "CFBundleExecutable": "applet" if com_applet else NOME,
        "CFBundleIconFile": "applet" if com_applet else "autodoc.icns",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": _versao(),
        "NSHighResolutionCapable": True,
        "LSArchitecturePriority": ["arm64", "x86_64"],
        "NSCameraUsageDescription": CAMERA,
    })
    if com_applet:
        # O applet e so o dono invisivel do processo; quem aparece no Dock,
        # com o nome e o icone do AutoDoc, e a janela.
        informacoes["LSUIElement"] = True
        # O osacompile novo guarda o icone num catalogo (Assets.car), que o
        # macOS prefere ao .icns: sem tirar, o Launchpad mostraria o icone
        # padrao do AppleScript em vez do AutoDoc.
        informacoes.pop("CFBundleIconName", None)
        (recursos / "Assets.car").unlink(missing_ok=True)
    caminho_plist.write_bytes(plistlib.dumps(informacoes))

    icone = RECURSOS / "autodoc.icns"
    if icone.exists():
        (recursos / ("applet.icns" if com_applet else "autodoc.icns")).write_bytes(icone.read_bytes())

    if com_applet and shutil.which("codesign"):
        # Mexer no Info.plist e no icone quebra a assinatura que o osacompile
        # pos; assinar de novo, sem certificado ("-"), deixa o pacote integro.
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(pacote)], check=True, capture_output=True)

    # O Finder guarda em cache o icone pelo tempo de modificacao do pacote.
    os.utime(pacote, None)

    return Atalho(pacote, True, f"{NOME}.app criado em {base}")


# ---------------------------------------------------------------- Windows

def _criar_windows(destino_base: Path | None) -> Atalho:
    base = destino_base or (
        Path(os.environ.get("APPDATA", Path.home()))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    )
    base.mkdir(parents=True, exist_ok=True)
    atalho = base / f"{NOME}.lnk"

    icone = RECURSOS / "autodoc.ico"
    script = f"""
$w = New-Object -ComObject WScript.Shell
$a = $w.CreateShortcut("{atalho}")
$a.TargetPath = "{_python_do_projeto()}"
$a.Arguments = "main.py app"
$a.WorkingDirectory = "{RAIZ}"
$a.IconLocation = "{icone}"
$a.Description = "{DESCRICAO}"
$a.Save()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as erro:
        return Atalho(None, False, f"nao foi possivel criar o atalho: {erro}")

    return Atalho(atalho, True, f"atalho criado no menu Iniciar")


# ------------------------------------------------------------------ Linux

def _criar_linux(destino_base: Path | None) -> Atalho:
    base = destino_base or (Path.home() / ".local" / "share" / "applications")
    base.mkdir(parents=True, exist_ok=True)
    atalho = base / "autodoc.desktop"

    atalho.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOME}\n"
        f"Comment={DESCRICAO}\n"
        f'Exec="{_python_do_projeto()}" main.py app\n'
        f"Path={RAIZ}\n"
        f"Icon={RECURSOS / 'autodoc.png'}\n"
        "Terminal=false\n"
        "Categories=Office;Utility;\n",
        encoding="utf-8",
    )
    atalho.chmod(0o755)

    return Atalho(atalho, True, f"atalho criado em {base}")


def _versao() -> str:
    from .. import __version__
    return __version__
