"""Camada de persistencia do AutoDoc (SQLite).

Guarda os metadados de cada documento, o texto extraido e — o que faz
diferenca na tela — a explicacao da classificacao: a confianca, a regra que
disparou, as palavras-chave encontradas, o trecho lido e o trajeto do arquivo.
Sem isso o painel "por que foi classificado assim" nao teria o que mostrar.

A busca usa uma tabela FTS5, mantida em dia por gatilhos. Antes era `LIKE`, que
varre linha por linha e nao entende palavra: procurar "marco" com LIKE traz
"marcos" e "demarcado" junto.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

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

# Colunas acrescentadas depois da primeira versao. Ficam separadas do ESQUEMA
# para que um banco ja existente ganhe as novas sem precisar ser apagado.
COLUNAS_EXTRA: dict[str, str] = {
    "confianca": "REAL NOT NULL DEFAULT 0",
    "regra": "TEXT",
    "palavras_chave": "TEXT",   # JSON
    "trecho": "TEXT",
    "etapas": "TEXT",           # JSON
    "origem": "TEXT",
    "tamanho": "INTEGER",
}

# A tabela FTS5 nao guarda o conteudo (content=''): ela indexa e aponta para a
# linha da tabela real pelo rowid, evitando ter duas copias do texto no arquivo.
ESQUEMA_BUSCA = """
CREATE VIRTUAL TABLE IF NOT EXISTS documentos_busca USING fts5(
    arquivo, categoria, data_documento, texto,
    content='documentos', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS documentos_ai AFTER INSERT ON documentos BEGIN
    INSERT INTO documentos_busca(rowid, arquivo, categoria, data_documento, texto)
    VALUES (new.id, new.arquivo, new.categoria, new.data_documento, new.texto);
END;

CREATE TRIGGER IF NOT EXISTS documentos_ad AFTER DELETE ON documentos BEGIN
    INSERT INTO documentos_busca(documentos_busca, rowid, arquivo, categoria,
                                 data_documento, texto)
    VALUES ('delete', old.id, old.arquivo, old.categoria, old.data_documento, old.texto);
END;

CREATE TRIGGER IF NOT EXISTS documentos_au AFTER UPDATE ON documentos BEGIN
    INSERT INTO documentos_busca(documentos_busca, rowid, arquivo, categoria,
                                 data_documento, texto)
    VALUES ('delete', old.id, old.arquivo, old.categoria, old.data_documento, old.texto);
    INSERT INTO documentos_busca(rowid, arquivo, categoria, data_documento, texto)
    VALUES (new.id, new.arquivo, new.categoria, new.data_documento, new.texto);
END;
"""

CAMPOS = """id, arquivo, caminho, categoria, data_documento, processado_em,
            confianca, regra, palavras_chave, trecho, etapas, origem, tamanho"""


@dataclass
class Documento:
    """Um documento processado pelo AutoDoc."""

    arquivo: str
    caminho: str
    categoria: str
    data_documento: str | None
    texto: str
    hash: str
    confianca: float = 0.0
    regra: str = ""
    palavras_chave: list[str] = field(default_factory=list)
    trecho: str = ""
    etapas: list[dict[str, str]] = field(default_factory=list)
    origem: str = ""
    tamanho: int = 0


class BuscaIndisponivel(RuntimeError):
    """O SQLite desta maquina foi compilado sem FTS5."""


class Banco:
    """Acesso ao banco SQLite de documentos."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.tem_busca = False
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
            self._migrar(conexao)

            # FTS5 costuma vir compilado, mas nao e obrigatorio: se faltar, a
            # busca cai para LIKE em vez de o programa nao subir.
            try:
                conexao.executescript(ESQUEMA_BUSCA)
                self.tem_busca = True
            except sqlite3.OperationalError:
                self.tem_busca = False

    @staticmethod
    def _migrar(conexao: sqlite3.Connection) -> None:
        """Acrescenta a um banco antigo as colunas que ele ainda nao tem."""
        existentes = {
            linha["name"]
            for linha in conexao.execute("PRAGMA table_info(documentos)")
        }
        for coluna, tipo in COLUNAS_EXTRA.items():
            if coluna not in existentes:
                conexao.execute(f"ALTER TABLE documentos ADD COLUMN {coluna} {tipo}")

    def inserir(self, documento: Documento) -> int | None:
        """Grava um documento. Retorna None se ele ja estava indexado."""
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT OR IGNORE INTO documentos
                    (arquivo, caminho, categoria, data_documento, texto, hash,
                     confianca, regra, palavras_chave, trecho, etapas, origem, tamanho)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    documento.arquivo,
                    documento.caminho,
                    documento.categoria,
                    documento.data_documento,
                    documento.texto,
                    documento.hash,
                    documento.confianca,
                    documento.regra,
                    json.dumps(documento.palavras_chave, ensure_ascii=False),
                    documento.trecho,
                    json.dumps(documento.etapas, ensure_ascii=False),
                    documento.origem,
                    documento.tamanho,
                ),
            )
            return cursor.lastrowid if cursor.rowcount else None

    def ja_indexado(self, hash_arquivo: str) -> bool:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                "SELECT 1 FROM documentos WHERE hash = ? LIMIT 1", (hash_arquivo,)
            )
            return cursor.fetchone() is not None

    @staticmethod
    def _consulta_fts(termo: str) -> str:
        """Transforma o que a pessoa digitou numa consulta FTS5 valida.

        Aspas, asteriscos e operadores como OR e NEAR tem significado no FTS5;
        digitados sem querer, quebram a consulta. Cada palavra vira um termo
        entre aspas com prefixo, entao "conta luz" acha "conta de luz marco".
        """
        palavras = [p for p in "".join(
            c if c.isalnum() else " " for c in termo
        ).split() if p]
        return " ".join(f'"{p}"*' for p in palavras)

    def buscar(self, termo: str, limite: int = 20) -> list[sqlite3.Row]:
        """Busca por nome, categoria, data ou conteudo do documento."""
        consulta = self._consulta_fts(termo)
        if not consulta:
            return self.listar(limite)

        if self.tem_busca:
            with self._conectar() as conexao:
                cursor = conexao.execute(
                    f"""
                    SELECT {CAMPOS}
                    FROM documentos
                    WHERE id IN (
                        SELECT rowid FROM documentos_busca WHERE documentos_busca MATCH ?
                    )
                    ORDER BY data_documento DESC, id DESC
                    LIMIT ?
                    """,
                    (consulta, limite),
                )
                return cursor.fetchall()

        # Sem FTS5: volta ao LIKE, que e pior mas funciona em qualquer lugar.
        padrao = f"%{termo}%"
        with self._conectar() as conexao:
            cursor = conexao.execute(
                f"""
                SELECT {CAMPOS} FROM documentos
                WHERE arquivo LIKE ? OR categoria LIKE ?
                   OR data_documento LIKE ? OR texto LIKE ?
                ORDER BY data_documento DESC, id DESC
                LIMIT ?
                """,
                (padrao, padrao, padrao, padrao, limite),
            )
            return cursor.fetchall()

    def listar(self, limite: int = 50, categoria: str | None = None) -> list[sqlite3.Row]:
        filtro = "WHERE categoria = ?" if categoria else ""
        parametros: tuple[Any, ...] = (categoria, limite) if categoria else (limite,)
        with self._conectar() as conexao:
            cursor = conexao.execute(
                f"SELECT {CAMPOS} FROM documentos {filtro} "
                f"ORDER BY id DESC LIMIT ?",
                parametros,
            )
            return cursor.fetchall()

    def contar_por_categoria(self) -> dict[str, int]:
        """Quantos documentos ha em cada categoria — alimenta a barra lateral."""
        with self._conectar() as conexao:
            cursor = conexao.execute(
                "SELECT categoria, COUNT(*) AS total FROM documentos "
                "GROUP BY categoria ORDER BY total DESC"
            )
            return {linha["categoria"]: linha["total"] for linha in cursor}

    def estatisticas(self) -> dict[str, int]:
        """Os quatro numeros do topo da tela."""
        with self._conectar() as conexao:
            uma = lambda sql: conexao.execute(sql).fetchone()[0]  # noqa: E731
            return {
                "arquivados": uma("SELECT COUNT(*) FROM documentos"),
                "hoje": uma(
                    "SELECT COUNT(*) FROM documentos "
                    "WHERE date(processado_em) = date('now')"
                ),
                "ocr": uma(
                    "SELECT COUNT(*) FROM documentos WHERE origem LIKE '%OCR%'"
                ),
                "revisar": uma(
                    "SELECT COUNT(*) FROM documentos "
                    "WHERE categoria = 'nao_classificado'"
                ),
            }
