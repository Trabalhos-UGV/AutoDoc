"""Pipeline de processamento de um documento.

Fluxo: extrai texto -> classifica -> extrai data -> arquiva em
<saida>/<categoria>/<ano>/ -> indexa no banco -> copia para o backup.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from .classificador import classificar
from .config import Config
from .datas import data_de_modificacao, extrair_data
from .db import Banco, Documento
from .extrator import ExtracaoIndisponivel, extrair_texto, hash_arquivo

logger = logging.getLogger(__name__)


@dataclass
class Resultado:
    """Retorno do processamento de um arquivo."""

    arquivo: Path
    categoria: str | None = None
    data: str | None = None
    destino: Path | None = None
    ignorado: str | None = None

    @property
    def sucesso(self) -> bool:
        return self.ignorado is None


class Pipeline:
    """Orquestra a leitura, classificacao e arquivamento dos documentos."""

    def __init__(self, config: Config, banco: Banco) -> None:
        self.config = config
        self.banco = banco

    def processar(self, caminho: Path) -> Resultado:
        if caminho.suffix.lower() not in self.config.extensoes:
            return Resultado(caminho, ignorado="extensao nao monitorada")

        assinatura = hash_arquivo(caminho)
        if self.banco.ja_indexado(assinatura):
            return Resultado(caminho, ignorado="ja indexado")

        try:
            texto = extrair_texto(caminho)
        except ExtracaoIndisponivel as erro:
            logger.warning("nao foi possivel ler %s: %s", caminho.name, erro)
            return Resultado(caminho, ignorado=str(erro))

        categoria = classificar(texto)
        data = extrair_data(texto, padrao=data_de_modificacao(caminho))
        destino = self._arquivar(caminho, categoria, data)

        self.banco.inserir(
            Documento(
                arquivo=caminho.name,
                caminho=str(destino),
                categoria=categoria,
                data_documento=data,
                texto=texto,
                hash=assinatura,
            )
        )
        self._fazer_backup(destino, categoria)

        logger.info("%s -> %s (%s)", caminho.name, categoria, data)
        return Resultado(caminho, categoria=categoria, data=data, destino=destino)

    def _arquivar(self, caminho: Path, categoria: str, data: str | None) -> Path:
        ano = data.split("-")[0] if data else "sem-data"
        pasta = self.config.pasta_saida / categoria / ano
        pasta.mkdir(parents=True, exist_ok=True)

        destino = self._nome_livre(pasta / caminho.name)
        shutil.move(str(caminho), destino)
        return destino

    def _fazer_backup(self, destino: Path, categoria: str) -> None:
        if self.config.pasta_backup is None:
            return
        pasta = self.config.pasta_backup / categoria
        pasta.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destino, self._nome_livre(pasta / destino.name))

    @staticmethod
    def _nome_livre(destino: Path) -> Path:
        """Evita sobrescrever: relatorio.pdf -> relatorio (2).pdf."""
        if not destino.exists():
            return destino

        contador = 2
        while True:
            candidato = destino.with_name(f"{destino.stem} ({contador}){destino.suffix}")
            if not candidato.exists():
                return candidato
            contador += 1
