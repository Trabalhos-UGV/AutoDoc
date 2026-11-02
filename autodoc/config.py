"""Configuracao do AutoDoc.

As opcoes sao lidas de um arquivo JSON (config.json na raiz do projeto).
Se o arquivo nao existir, valores padrao sao usados.

Nao ha caminho de banco de dados aqui: o AutoDoc guarda o que sabe dentro da
propria pasta organizada, em `.autodoc/`. Configurar a pasta de saida ja e
configurar onde ficam os dados.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_CONFIG = RAIZ / "config.json"

NOME_SAIDA = "organizados"

logger = logging.getLogger(__name__)


def pasta_documentos() -> Path:
    """A pasta de documentos da pessoa, com o nome que ela tem neste sistema."""
    for nome in ("Documentos", "Documents"):
        candidata = Path.home() / nome
        if candidata.is_dir():
            return candidata
    return Path.home()


def entrada_padrao() -> Path:
    """Onde o AutoDoc vigia quando ninguem escolheu nada.

    Fica nos documentos da pessoa, e nao dentro do repositorio: um programa
    instalado nao tem por que despejar arquivo no meio do proprio codigo.
    """
    return pasta_documentos() / "AutoDoc" / "entrada"


def problema_da_pasta(pasta: Path) -> str | None:
    """Por que esta pasta nao pode ser vigiada — ou None, se pode.

    O AutoDoc tira da pasta vigiada tudo o que aparece nela, subpastas
    inclusive. Apontado para a pasta do proprio programa, ele "organizava" os
    arquivos de exemplo do repositorio a cada abertura — foi o que esvaziou
    `exemplos/` nesta maquina. Apontado para a pasta pessoal ou para Documentos
    inteira, levaria embora arquivos que ninguem pediu para organizar.
    """
    pasta = Path(pasta).expanduser().resolve()
    if pasta == RAIZ or RAIZ in pasta.parents:
        return "fica dentro da pasta do próprio AutoDoc — escolha uma pasta só para os documentos"

    casa = Path.home().resolve()
    if pasta == casa or pasta in casa.parents:
        return "é a pasta pessoal inteira — escolha uma pasta só para os documentos"
    if pasta == pasta_documentos().resolve():
        return "é a pasta Documentos inteira — escolha uma subpasta dela"
    return None


@dataclass
class Config:
    """Opcoes de execucao do AutoDoc."""

    # Pasta monitorada: qualquer arquivo novo aqui e processado.
    pasta_entrada: Path = field(default_factory=entrada_padrao)

    # Pasta onde os documentos organizados sao arquivados. Quando nao e
    # informada, nasce ao lado da pasta vigiada — as duas andam juntas, e
    # separa-las so confunde quem depois vai procurar os arquivos.
    pasta_saida: Path | None = None

    # Pasta sincronizada (Drive/OneDrive) para backup. Opcional.
    pasta_backup: Path | None = None

    # Extensoes aceitas pelo monitorador.
    extensoes: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg", ".txt")

    def __post_init__(self) -> None:
        self.pasta_entrada = Path(self.pasta_entrada).expanduser()
        self.pasta_saida = (
            Path(self.pasta_saida).expanduser()
            if self.pasta_saida
            else self.saida_ao_lado()
        )

    def saida_ao_lado(self) -> Path:
        """A pasta organizada irma da pasta vigiada."""
        return self.pasta_entrada.parent / NOME_SAIDA

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Config":
        """Le a configuracao do disco, caindo nos padroes quando ausente."""
        caminho = caminho or CAMINHO_CONFIG
        if not caminho.exists():
            return cls()

        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Config quebrado nao pode impedir o programa de abrir; os padroes
            # levam a um estado utilizavel, e o instalador regrava o arquivo.
            return cls()

        config = cls()
        for campo in ("pasta_entrada", "pasta_saida", "pasta_backup"):
            if dados.get(campo):
                setattr(config, campo, Path(dados[campo]).expanduser())

        # Pasta de entrada escolhida e saida omitida: a saida acompanha.
        if dados.get("pasta_entrada") and not dados.get("pasta_saida"):
            config.pasta_saida = config.saida_ao_lado()

        # Uma pasta que nao pode ser vigiada, gravada por uma versao que ainda
        # nao recusava, volta para o padrao — junto com a saida, que andava com
        # ela. O arquivo nao e reescrito: quem decide a pasta e o instalador.
        problema = problema_da_pasta(config.pasta_entrada)
        if problema:
            logger.warning("pasta monitorada %s recusada: %s; usando %s",
                           config.pasta_entrada, problema, entrada_padrao())
            config.pasta_entrada = entrada_padrao()
            config.pasta_saida = config.saida_ao_lado()

        if dados.get("extensoes"):
            config.extensoes = tuple(e.lower() for e in dados["extensoes"])

        # Um `banco` de uma versao antiga e lido e ignorado de proposito: nao
        # ha mais banco, e recusar o arquivo por causa dele seria pior.
        return config

    def como_dict(self) -> dict:
        return {
            "pasta_entrada": str(self.pasta_entrada),
            "pasta_saida": str(self.pasta_saida),
            "pasta_backup": str(self.pasta_backup) if self.pasta_backup else None,
            "extensoes": list(self.extensoes),
        }

    def salvar(self, caminho: Path | None = None) -> Path:
        """Grava a configuracao. E por aqui que a pasta escolhida vira decisao."""
        caminho = caminho or CAMINHO_CONFIG
        caminho.write_text(
            json.dumps(self.como_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return caminho

    def preparar_pastas(self) -> None:
        """Cria as pastas necessarias caso ainda nao existam."""
        for pasta in (self.pasta_entrada, self.pasta_saida, self.pasta_backup):
            if pasta is not None:
                pasta.mkdir(parents=True, exist_ok=True)
