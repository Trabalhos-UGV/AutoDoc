"""Pipeline de processamento de um documento.

Fluxo: extrai texto -> classifica -> extrai data -> arquiva em
<saida>/<categoria>/<ano>/<mes>/ -> indexa no banco -> copia para o backup.

Cada passo registra o que fez. Esse registro — o "trajeto do arquivo" — e o que
a tela mostra quando alguem quer entender por que um documento foi parar onde
foi parar, e e a diferenca entre um programa que organiza e um que so esconde
os arquivos em outro lugar.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .classificador import NAO_CLASSIFICADO, Classificacao, classificar
from .config import Config
from .datas import data_de_modificacao, extrair_data_rotulada, extrair_datas
from .db import Banco, Documento
from .extrator import ExtracaoIndisponivel, extrair_com_origem, hash_arquivo

logger = logging.getLogger(__name__)

# Pasta para onde vai o que o classificador nao teve confianca de classificar.
PASTA_REVISAO = "_Revisar"

# Quanto do texto lido aparece no painel "trecho lido do documento".
TAMANHO_TRECHO = 220


@dataclass
class Resultado:
    """Retorno do processamento de um arquivo."""

    arquivo: Path
    categoria: str | None = None
    data: str | None = None
    destino: Path | None = None
    ignorado: str | None = None
    documento: Documento | None = None
    etapas: list[dict[str, str]] = field(default_factory=list)

    @property
    def sucesso(self) -> bool:
        return self.ignorado is None


def _trecho(texto: str) -> str:
    """Um pedaco limpo do inicio do texto, para mostrar na tela."""
    limpo = " ".join(texto.split())
    if len(limpo) <= TAMANHO_TRECHO:
        return limpo
    return limpo[:TAMANHO_TRECHO].rsplit(" ", 1)[0] + "…"


def _formatar_tamanho(bytes_: int) -> str:
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.0f} KB".replace(".", ",")
    return f"{bytes_ / 1024 / 1024:.1f} MB".replace(".", ",")


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

        tamanho = caminho.stat().st_size
        etapas = [
            {
                "titulo": "Detecção",
                "detalhe": (
                    f"arquivo novo na pasta monitorada — "
                    f"{datetime.now():%H:%M:%S}, {_formatar_tamanho(tamanho)}"
                ),
            }
        ]

        try:
            texto, origem = extrair_com_origem(caminho)
        except ExtracaoIndisponivel as erro:
            logger.warning("nao foi possivel ler %s: %s", caminho.name, erro)
            return Resultado(caminho, ignorado=str(erro))

        etapas.append({
            "titulo": "Extração de texto",
            "detalhe": f"{origem} · {len(texto)} caracteres lidos",
        })

        classificacao = classificar(texto)
        etapas.append({
            "titulo": "Classificação",
            "detalhe": (
                f"{classificacao.regra} · confiança "
                f"{classificacao.confianca:.0%}"
            ),
        })

        data, detalhe_data = self._resolver_data(texto, caminho)
        etapas.append({"titulo": "Data", "detalhe": detalhe_data})

        destino = self._arquivar(caminho, classificacao, data)
        relativo = self._relativo(destino)
        etapas.append({
            "titulo": "Arquivamento",
            "detalhe": f"movido para {relativo} e indexado na busca",
        })

        documento = Documento(
            arquivo=caminho.name,
            caminho=str(destino),
            categoria=classificacao.categoria,
            data_documento=data,
            texto=texto,
            hash=assinatura,
            confianca=classificacao.confianca,
            regra=classificacao.regra,
            palavras_chave=classificacao.chaves,
            trecho=_trecho(texto),
            etapas=etapas,
            origem=origem,
            tamanho=tamanho,
        )
        self.banco.inserir(documento)
        self._fazer_backup(destino, classificacao)

        logger.info(
            "%s -> %s (%s) confianca %.0f%%",
            caminho.name, classificacao.categoria, data, classificacao.confianca * 100,
        )
        return Resultado(
            caminho,
            categoria=classificacao.categoria,
            data=data,
            destino=destino,
            documento=documento,
            etapas=etapas,
        )

    @staticmethod
    def _resolver_data(texto: str, caminho: Path) -> tuple[str | None, str]:
        """A data do documento e a explicacao de como ela foi escolhida."""
        rotulada = extrair_data_rotulada(texto)
        if rotulada:
            data, rotulo = rotulada
            return data, f'rótulo "{rotulo}" no texto → {data}'

        soltas = extrair_datas(texto)
        if soltas:
            data = soltas[0].isoformat()
            return data, f"primeira data encontrada no texto → {data}"

        data = data_de_modificacao(caminho).isoformat()
        return data, f"nenhuma data no texto; usando a modificação do arquivo → {data}"

    def _pasta_destino(self, classificacao: Classificacao, data: str | None) -> Path:
        """Onde o arquivo vai parar.

        O que nao passou do limiar vai para uma fila unica de revisao, sem
        separar por ano: e uma pilha para alguem olhar, nao um arquivo morto.
        """
        if classificacao.categoria == NAO_CLASSIFICADO:
            return self.config.pasta_saida / PASTA_REVISAO

        if data:
            ano, mes = data.split("-")[0], data.split("-")[1]
            return self.config.pasta_saida / classificacao.categoria / ano / mes

        return self.config.pasta_saida / classificacao.categoria / "sem-data"

    def _arquivar(
        self, caminho: Path, classificacao: Classificacao, data: str | None
    ) -> Path:
        pasta = self._pasta_destino(classificacao, data)
        pasta.mkdir(parents=True, exist_ok=True)

        destino = self._nome_livre(pasta / caminho.name)
        shutil.move(str(caminho), destino)
        return destino

    def _relativo(self, destino: Path) -> str:
        """Caminho curto, a partir da pasta de saida, para mostrar na tela."""
        try:
            return str(destino.parent.relative_to(self.config.pasta_saida)) + "/"
        except ValueError:
            return str(destino.parent) + "/"

    def _fazer_backup(self, destino: Path, classificacao: Classificacao) -> None:
        if self.config.pasta_backup is None:
            return
        # Mesmo nome de pasta do arquivo principal, para o backup nao virar uma
        # organizacao paralela e diferente.
        nome = (
            PASTA_REVISAO
            if classificacao.categoria == NAO_CLASSIFICADO
            else classificacao.categoria
        )
        pasta = self.config.pasta_backup / nome
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
