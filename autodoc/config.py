"""Configuracao do AutoDoc.

As opcoes sao lidas de um arquivo JSON (config.json na raiz do projeto).
Se o arquivo nao existir, valores padrao sao usados.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_CONFIG = RAIZ / "config.json"


@dataclass
class Config:
    """Opcoes de execucao do AutoDoc."""

    # Pasta monitorada: qualquer arquivo novo aqui e processado.
    pasta_entrada: Path = field(default_factory=lambda: RAIZ / "entrada")

    # Pasta onde os documentos organizados sao arquivados.
    pasta_saida: Path = field(default_factory=lambda: RAIZ / "organizados")

    # Pasta sincronizada (Drive/OneDrive) para backup. Opcional.
    pasta_backup: Path | None = None

    # Banco SQLite com os documentos indexados.
    banco: Path = field(default_factory=lambda: RAIZ / "autodoc.db")

    # Extensoes aceitas pelo monitorador.
    extensoes: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg", ".txt")

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Config":
        """Le a configuracao do disco, caindo nos padroes quando ausente."""
        caminho = caminho or CAMINHO_CONFIG
        if not caminho.exists():
            return cls()

        dados = json.loads(caminho.read_text(encoding="utf-8"))
        config = cls()

        for campo in ("pasta_entrada", "pasta_saida", "pasta_backup", "banco"):
            if dados.get(campo):
                setattr(config, campo, Path(dados[campo]).expanduser())

        if dados.get("extensoes"):
            config.extensoes = tuple(e.lower() for e in dados["extensoes"])

        return config

    def preparar_pastas(self) -> None:
        """Cria as pastas necessarias caso ainda nao existam."""
        for pasta in (self.pasta_entrada, self.pasta_saida, self.pasta_backup):
            if pasta is not None:
                pasta.mkdir(parents=True, exist_ok=True)
