"""As seis etapas da instalacao do AutoDoc.

Sao as mesmas seis que a tela desenha, e todas fazem trabalho de verdade:
procurar o Python, criar o ambiente virtual, instalar as dependencias, achar o
Tesseract, preparar a pasta organizada e registrar a pasta monitorada — mais o
atalho no sistema, que e o que faz o programa ficar instalado em vez de so rodar.

A instalacao e **idempotente**: rodar de novo verifica o que ja existe e so
refaz o que falta. Um instalador que quebra quando ja foi rodado uma vez e um
instalador que ninguem ousa rodar duas vezes.

Cada etapa e um gerador que solta linhas de log conforme trabalha; quem chama
transforma isso em eventos para a tela.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..catalogo import PASTA_CATALOGO, Catalogo
from ..config import CAMINHO_CONFIG, Config
from . import atalho

RAIZ = Path(__file__).resolve().parent.parent.parent
VENV = RAIZ / "venv"
PYTHON_MINIMO = (3, 10)


@dataclass
class Etapa:
    """Uma etapa da instalacao, com o que mostrar na tela enquanto roda."""

    titulo: str
    detalhe: str = ""
    logs: list[str] = field(default_factory=list)


def _python_do_venv() -> Path:
    if sys.platform.startswith("win"):
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


# --------------------------------------------------------------- etapas

def verificar_ambiente(estado: dict) -> Iterator[str]:
    versao = sys.version_info
    texto = f"{versao.major}.{versao.minor}.{versao.micro}"
    yield f"python --version → {texto}"

    if versao[:2] < PYTHON_MINIMO:
        exigido = ".".join(str(n) for n in PYTHON_MINIMO)
        raise RuntimeError(f"o AutoDoc precisa do Python {exigido} ou mais novo")

    livre = shutil.disk_usage(RAIZ).free / (1024 ** 3)
    yield f"espaço em disco: {livre:.0f} GB livres"
    estado["detalhe"] = f"Python {texto} encontrado"


def criar_ambiente_virtual(estado: dict) -> Iterator[str]:
    python = _python_do_venv()
    if python.exists():
        yield f"venv já existe em {VENV.name}/"
        estado["detalhe"] = f"{VENV.name}/ já estava criado"
        return

    yield "python -m venv venv"
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    yield "ambiente virtual criado"
    estado["detalhe"] = f"{VENV.name}/ criado no diretório do projeto"


def instalar_dependencias(estado: dict) -> Iterator[str]:
    python = _python_do_venv()
    yield "pip install -r requirements.txt"

    processo = subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(RAIZ / "requirements.txt")],
        capture_output=True, text=True,
    )
    if processo.returncode != 0:
        raise RuntimeError(
            "falha ao instalar as dependências:\n"
            + (processo.stderr or processo.stdout)[-400:]
        )

    # Resumir em vez de repetir a saida do pip: ela e comprida, cheia de
    # caminho absoluto, e cortada no meio fica pior do que nao mostrar nada.
    saida = processo.stdout
    novos = [l for l in saida.splitlines() if l.startswith("Successfully installed")]
    if novos:
        yield novos[-1][:100]
    else:
        ja_tinha = saida.count("Requirement already satisfied")
        yield f"{ja_tinha} dependências já estavam instaladas"

    instalados = subprocess.run(
        [str(python), "-m", "pip", "list", "--format=freeze"],
        capture_output=True, text=True,
    ).stdout.splitlines()
    yield f"{len(instalados)} pacotes disponíveis no ambiente"
    estado["detalhe"] = "watchdog, pypdf, pywebview, pytesseract"


def configurar_ocr(estado: dict) -> Iterator[str]:
    caminho = shutil.which("tesseract")
    if not caminho:
        # Ausencia do Tesseract nao e erro: o AutoDoc le PDF e texto sem ele.
        yield "tesseract não encontrado no PATH"
        yield "OCR desativado — o resto do AutoDoc funciona normalmente"
        estado["detalhe"] = "Tesseract ausente — OCR de imagens desativado"
        return

    versao = subprocess.run(
        [caminho, "--version"], capture_output=True, text=True
    ).stdout.splitlines()
    yield f"tesseract encontrado em {caminho}"
    if versao:
        yield versao[0].strip()
    estado["detalhe"] = "Tesseract pronto para ler imagens"


def preparar_catalogo(estado: dict, pasta_entrada: Path) -> Iterator[str]:
    """Prepara a pasta organizada — que e onde o AutoDoc guarda o que sabe.

    Nao ha banco de dados para criar. O que existe e uma pasta com os
    documentos e um caderno de fichas dentro dela, e essa etapa so garante que
    a pasta existe e le o que ja estiver la.
    """
    config = Config.carregar()
    config.pasta_entrada = pasta_entrada
    config.pasta_saida = config.saida_ao_lado()
    config.preparar_pastas()
    yield f"pasta organizada: {config.pasta_saida}"

    catalogo = Catalogo(config.pasta_saida)
    yield f"caderno de fichas em {PASTA_CATALOGO}/{catalogo.arquivo.name}"

    # A pasta manda: se ja houver documentos arquivados ali, eles voltam para o
    # catalogo sozinhos — inclusive numa reinstalacao por cima da anterior.
    resumo = catalogo.reconciliar()
    if resumo["recuperadas"]:
        yield f"{resumo['recuperadas']} documento(s) ja arquivado(s) reconhecido(s)"
    yield f"{len(catalogo)} documento(s) no catálogo"
    estado["detalhe"] = f"{config.pasta_saida.name}/ pronta, sem banco de dados"


def definir_pasta(estado: dict, pasta_entrada: Path) -> Iterator[str]:
    config = Config.carregar()
    config.pasta_entrada = pasta_entrada
    # A saida acompanha a entrada escolhida, e nao a que estava no config
    # anterior — senao trocar de pasta monitorada deixaria os documentos novos
    # indo para o lugar antigo.
    config.pasta_saida = config.saida_ao_lado()
    config.preparar_pastas()
    yield f"pasta monitorada: {pasta_entrada}"
    yield f"pasta organizada: {config.pasta_saida}"

    config.salvar(CAMINHO_CONFIG)
    yield f"configuração gravada em {CAMINHO_CONFIG.name}"

    resultado = atalho.criar()
    yield resultado.detalhe if resultado.criado else f"atalho não criado: {resultado.detalhe}"
    estado["detalhe"] = str(pasta_entrada)


PASSOS = [
    ("Verificando ambiente", verificar_ambiente),
    ("Criando ambiente virtual", criar_ambiente_virtual),
    ("Instalando dependências", instalar_dependencias),
    ("Configurando motor de OCR", configurar_ocr),
    ("Preparando a pasta organizada", preparar_catalogo),
    ("Definindo pasta monitorada", definir_pasta),
]


class Instalacao:
    """Roda as seis etapas, contando o que vai acontecendo."""

    def __init__(self, pasta_entrada: Path) -> None:
        self.pasta_entrada = pasta_entrada
        self.etapas = [Etapa(titulo) for titulo, _ in PASSOS]
        self.log: list[dict[str, str]] = []
        self.indice = 0
        self.progresso = 0.0
        self.concluido = False
        self.erro: str | None = None

    def _registrar(self, mensagem: str) -> None:
        self.log.append({"hora": f"{datetime.now():%H:%M}", "mensagem": mensagem})
        self.log = self.log[-40:]

    def instantaneo(self) -> dict:
        """O estado atual, no formato que a tela consome."""
        return {
            "indice": self.indice,
            "progresso": round(self.progresso, 1),
            "concluido": self.concluido,
            "erro": self.erro,
            "pasta": str(self.pasta_entrada),
            "etapas": [
                {"titulo": e.titulo, "detalhe": e.detalhe, "logs": e.logs}
                for e in self.etapas
            ],
            "log": self.log[-8:],
        }

    def executar(self) -> Iterator[dict]:
        """Percorre as etapas, devolvendo o estado a cada mudanca."""
        total = len(PASSOS)

        for indice, (titulo, funcao) in enumerate(PASSOS):
            self.indice = indice
            self.progresso = (indice / total) * 100
            yield self.instantaneo()

            estado: dict = {"detalhe": ""}
            try:
                # As duas ultimas etapas precisam saber qual pasta foi
                # escolhida; as outras se viram com o ambiente.
                gerador = (
                    funcao(estado, self.pasta_entrada)
                    if funcao in (preparar_catalogo, definir_pasta)
                    else funcao(estado)
                )
                for mensagem in gerador:
                    self.etapas[indice].logs.append(mensagem)
                    self._registrar(mensagem)
                    self.progresso = ((indice + 0.6) / total) * 100
                    yield self.instantaneo()
            except Exception as erro:  # uma etapa falhou; a tela precisa saber
                self.erro = f"{titulo}: {erro}"
                self._registrar(f"ERRO — {self.erro}")
                yield self.instantaneo()
                return

            self.etapas[indice].detalhe = estado["detalhe"]
            self.progresso = ((indice + 1) / total) * 100
            yield self.instantaneo()

        self.concluido = True
        self.progresso = 100.0
        self._registrar("instalação concluída")
        yield self.instantaneo()
