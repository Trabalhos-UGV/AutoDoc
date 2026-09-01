"""Pipeline de processamento de um documento.

Fluxo: extrai texto -> classifica -> extrai data -> arquiva em
<saida>/<categoria>/<ano>/<mes>/ -> ficha no catalogo -> copia para o backup.

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

from .catalogo import PASTA_REVISAO, Catalogo, Ficha
from .classificador import NAO_CLASSIFICADO, ROTULOS, Classificacao, classificar
from .config import Config
from .datas import data_de_modificacao, extrair_data_rotulada, extrair_datas
from .extrator import ExtracaoIndisponivel, extrair_com_origem, hash_arquivo

logger = logging.getLogger(__name__)

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
    documento: Ficha | None = None
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

    def __init__(self, config: Config, catalogo: Catalogo) -> None:
        self.config = config
        self.catalogo = catalogo

    def processar(self, caminho: Path) -> Resultado:
        if caminho.suffix.lower() not in self.config.extensoes:
            return Resultado(caminho, ignorado="extensao nao monitorada")

        assinatura = hash_arquivo(caminho)
        if self.catalogo.ja_indexado(assinatura):
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

        # Ler pode falhar por falta do Tesseract, PDF corrompido, permissao. Em
        # nenhum desses casos o arquivo pode ficar parado na pasta de entrada:
        # ali ele seria retentado a cada abertura do programa e ninguem saberia
        # que ele existe. Vai para a revisao, com o motivo escrito no trajeto.
        ilegivel: str | None = None
        try:
            texto, origem = extrair_com_origem(caminho)
        except (ExtracaoIndisponivel, OSError) as erro:
            logger.warning("nao foi possivel ler %s: %s", caminho.name, erro)
            texto, origem, ilegivel = "", "não foi possível ler o arquivo", str(erro)

        etapas.append({
            "titulo": "Extração de texto",
            "detalhe": ilegivel or f"{origem} · {len(texto)} caracteres lidos",
        })

        classificacao = classificar(texto)
        if ilegivel:
            classificacao = Classificacao(
                categoria=NAO_CLASSIFICADO,
                confianca=0.0,
                regra=f"não foi possível ler o conteúdo — {ilegivel}",
            )
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

        documento = Ficha(
            arquivo=caminho.name,
            caminho=self.catalogo.relativo(destino),
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
        self.catalogo.inserir(documento)
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

    def reclassificar(self, ficha: Ficha, categoria: str) -> Ficha:
        """Move o documento para outra categoria, porque alguem discordou.

        O classificador erra, e um sistema que so deixa concordar com ele nao e
        util: o que vai para `_Revisar/` precisa ter como sair de la. A
        confianca vira 1.0 e a regra passa a dizer que foi decisao humana — nao
        se atribui ao classificador um acerto que nao foi dele.
        """
        if categoria not in ROTULOS:
            raise ValueError(f"categoria desconhecida: {categoria}")

        origem = self.catalogo.caminho_de(ficha)
        destino_pasta = self._pasta_destino(
            Classificacao(categoria=categoria, confianca=1.0, regra=""),
            ficha.data_documento,
        )
        destino_pasta.mkdir(parents=True, exist_ok=True)
        destino = self._nome_livre(destino_pasta / origem.name)

        if origem.exists():
            shutil.move(str(origem), destino)
        else:
            logger.warning("arquivo de %s sumiu antes da correcao", ficha.arquivo)

        ficha.categoria = categoria
        ficha.caminho = self.catalogo.relativo(destino)
        ficha.confianca = 1.0
        ficha.regra = f'categoria definida a mao como "{ROTULOS[categoria]}"'
        ficha.etapas = list(ficha.etapas) + [{
            "titulo": "Correção manual",
            "detalhe": (
                f"movido para {self._relativo(destino)} por escolha de quem usa — "
                f"{datetime.now():%d/%m/%Y %H:%M}"
            ),
        }]

        self.catalogo.atualizar(ficha)
        logger.info("%s corrigido a mao para %s", ficha.arquivo, categoria)
        return ficha

    def analisar(self, caminho: Path) -> Ficha | None:
        """Le e classifica um arquivo **sem mover nada**.

        E o que o catalogo pede quando encontra, na pasta organizada, um
        documento que ele nao conhece: alguem arrastou o arquivo para la a mao,
        ou o caderno de fichas foi apagado. Nos dois casos o arquivo ja esta no
        lugar que alguem escolheu — o que falta e saber o que ele diz.
        """
        try:
            texto, origem = extrair_com_origem(caminho)
        except (ExtracaoIndisponivel, OSError) as erro:
            logger.warning("nao foi possivel reler %s: %s", caminho.name, erro)
            texto, origem = "", f"nao foi possivel ler: {erro}"

        classificacao = classificar(texto)
        data, detalhe_data = self._resolver_data(texto, caminho)

        return Ficha(
            arquivo=caminho.name,
            caminho=self.catalogo.relativo(caminho),
            categoria=classificacao.categoria,
            data_documento=data,
            texto=texto,
            hash=hash_arquivo(caminho),
            confianca=classificacao.confianca,
            regra=classificacao.regra,
            palavras_chave=classificacao.chaves,
            trecho=_trecho(texto),
            etapas=[
                {"titulo": "Releitura", "detalhe":
                 "documento encontrado na pasta organizada e fichado de novo"},
                {"titulo": "Extração de texto",
                 "detalhe": f"{origem} · {len(texto)} caracteres lidos"},
                {"titulo": "Classificação", "detalhe": classificacao.regra},
                {"titulo": "Data", "detalhe": detalhe_data},
            ],
            origem=origem,
            tamanho=caminho.stat().st_size,
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
