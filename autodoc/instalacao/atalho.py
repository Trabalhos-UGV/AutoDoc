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

def _criar_macos(destino_base: Path | None) -> Atalho:
    base = destino_base or (Path.home() / "Applications")
    base.mkdir(parents=True, exist_ok=True)
    pacote = base / f"{NOME}.app"

    conteudo = pacote / "Contents"
    executaveis = conteudo / "MacOS"
    recursos = conteudo / "Resources"
    executaveis.mkdir(parents=True, exist_ok=True)
    recursos.mkdir(parents=True, exist_ok=True)

    informacoes = {
        "CFBundleName": NOME,
        "CFBundleDisplayName": NOME,
        "CFBundleIdentifier": IDENTIFICADOR,
        "CFBundleExecutable": NOME,
        "CFBundleIconFile": "autodoc.icns",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": _versao(),
        "NSHighResolutionCapable": True,
    }
    (conteudo / "Info.plist").write_bytes(plistlib.dumps(informacoes))

    icone = RECURSOS / "autodoc.icns"
    if icone.exists():
        (recursos / "autodoc.icns").write_bytes(icone.read_bytes())

    lancador = executaveis / NOME
    lancador.write_text(
        "#!/bin/bash\n"
        f'cd "{RAIZ}"\n'
        f'exec "{_python_do_projeto()}" main.py app\n',
        encoding="utf-8",
    )
    lancador.chmod(0o755)

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
