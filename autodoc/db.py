"""Camada de persistencia do AutoDoc (SQLite).

Guarda os metadados de cada documento processado e o texto extraido, para
permitir busca por conteudo (ex.: "conta de luz marco").
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo        TEXT NOT NULL,
    caminho        TEXT NOT NULL UNIQUE,
    categoria      TEXT NOT NULL,
    data_documento TEXT,
    texto          TEXT,
    hash           TEXT UNIQUE,
    processado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documentos_categoria ON documentos(categoria);
CREATE INDEX IF NOT EXISTS idx_documentos_data ON documentos(data_documento);
"""


@dataclass
class Documento:
    """Um documento processado pelo AutoDoc."""

    arquivo: str
    caminho: str
    categoria: str
    data_documento: str | None
    texto: str
    hash: str


class Banco:
    """Acesso ao banco SQLite de documentos."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._criar_esquema()

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        conexao = sqlite3.connect(self.caminho)
        conexao.row_factory = sqlite3.Row
        try:
            yield conexao
            conexao.commit()
        finally:
            conexao.close()

    def _criar_esquema(self) -> None:
        with self._conectar() as conexao:
            conexao.executescript(ESQUEMA)

    def inserir(self, documento: Documento) -> int | None:
        """Grava um documento. Retorna None se ele ja estava indexado."""
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT OR IGNORE INTO documentos
                    (arquivo, caminho, categoria, data_documento, texto, hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    documento.arquivo,
                    documento.caminho,
                    documento.categoria,
                    documento.data_documento,
                    documento.texto,
                    documento.hash,
                ),
            )
            return cursor.lastrowid if cursor.rowcount else None

    def ja_indexado(self, hash_arquivo: str) -> bool:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                "SELECT 1 FROM documentos WHERE hash = ? LIMIT 1", (hash_arquivo,)
            )
            return cursor.fetchone() is not None

    def buscar(self, termo: str, limite: int = 20) -> list[sqlite3.Row]:
        """Busca por nome do arquivo, categoria, data ou conteudo do texto."""
        padrao = f"%{termo}%"
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                SELECT id, arquivo, caminho, categoria, data_documento, processado_em
                FROM documentos
                WHERE arquivo LIKE ?
                   OR categoria LIKE ?
                   OR data_documento LIKE ?
                   OR texto LIKE ?
                ORDER BY data_documento DESC, id DESC
                LIMIT ?
                """,
                (padrao, padrao, padrao, padrao, limite),
            )
            return cursor.fetchall()

    def listar(self, limite: int = 50) -> list[sqlite3.Row]:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                SELECT id, arquivo, caminho, categoria, data_documento, processado_em
                FROM documentos
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,),
            )
            return cursor.fetchall()
