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
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .catalogo import (
    PASTA_AGUARDANDO_OCR,
    PASTA_DUPLICADOS,
    PASTA_NAO_SUPORTADOS,
    PASTA_REVISAO,
    Catalogo,
    Ficha,
)
from .classificador import (
    IMAGENS,
    NAO_CLASSIFICADO,
    ROTULOS,
    TEXTOS,
    Classificacao,
    classificar,
)
from .config import Config
from .datas import data_do_documento, extrair_data
from .extrator import (
    EXTENSOES_IMAGEM,
    EXTENSOES_TEXTO,
    ExtracaoIndisponivel,
    OcrIndisponivel,
    extrair_com_origem,
    hash_arquivo,
    sobre_a_imagem,
)

logger = logging.getLogger(__name__)

# Quanto do texto lido aparece no painel "trecho lido do documento".
TAMANHO_TRECHO = 220

# Ate este lado, em pixels, a imagem e icone ou elemento de interface: nenhuma
# foto de documento, de celular ou de scanner, e tao pequena.
LADO_MAXIMO_ICONE = 600

# Texto de uma linha so, sem espaco, ate este tamanho: "8.0.29", um hash, um
# numero de versao. Nao e documento, e nao ha o que revisar nele.
TAMANHO_MAXIMO_LINHA_SOLTA = 64


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


def _pelo_tipo(caminho: Path, texto: str, classificacao: Classificacao) -> Classificacao:
    """Quando o conteudo nao e de documento nenhum, o que o arquivo e.

    Um icone ou uma foto sem texto nao e duvida: e uma imagem. Mandados para
    `_Revisar/` com 0%, eles enchiam a fila de revisao com o que ninguem
    precisa olhar — foi assim que 183 arquivos de uma pasta de Downloads
    apareceram todos como "nao classificado". A revisao fica para o que pontuou
    em alguma regra sem convencer: ali, sim, errar a categoria e pior que
    perguntar.
    """
    if classificacao.categoria != NAO_CLASSIFICADO or classificacao.chaves:
        return classificacao

    extensao = caminho.suffix.lower()
    if extensao in EXTENSOES_IMAGEM:
        tamanho, _data = sobre_a_imagem(caminho)
        if tamanho is None:
            descricao = "imagem"
        else:
            medidas = f"{tamanho[0]}×{tamanho[1]}"
            descricao = (
                f"ícone ou elemento de interface ({medidas})"
                if max(tamanho) <= LADO_MAXIMO_ICONE
                else f"foto ou imagem ({medidas})"
            )
        return Classificacao(
            categoria=IMAGENS,
            confianca=1.0,
            regra=f"{descricao}, sem texto de documento — identificada pelo tipo de arquivo",
        )

    limpo = texto.strip()
    if (
        extensao in EXTENSOES_TEXTO
        and limpo
        and len(limpo) <= TAMANHO_MAXIMO_LINHA_SOLTA
        and not any(c.isspace() for c in limpo)
    ):
        return Classificacao(
            categoria=TEXTOS,
            confianca=1.0,
            regra=f'arquivo de texto de uma linha só ("{limpo}"), sem conteúdo de documento',
        )

    return classificacao


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
        # O watchdog e a varredura periodica podem achar o mesmo arquivo ao
        # mesmo tempo; um de cada vez, e o segundo ve que ele ja saiu.
        self._trava = threading.Lock()

    def processar(self, caminho: Path) -> Resultado:
        with self._trava:
            if not caminho.exists():
                return Resultado(caminho, ignorado="arquivo nao esta mais na pasta")
            return self._processar(caminho)

    def _processar(self, caminho: Path) -> Resultado:
        if caminho.suffix.lower() not in self.config.extensoes:
            # Deixado na entrada, um .docx ficava ali para sempre e quem o
            # largou achava que o AutoDoc tinha travado. Sai, para uma pasta
            # que diz o motivo, e a tela conta quantos estao la.
            destino = self._recolher(caminho, PASTA_NAO_SUPORTADOS)
            return Resultado(caminho, ignorado="formato nao suportado", destino=destino)

        try:
            assinatura = hash_arquivo(caminho)
        except OSError as erro:
            logger.warning("nao foi possivel ler %s: %s", caminho.name, erro)
            return Resultado(caminho, ignorado=f"arquivo ilegivel: {erro}")

        if self.catalogo.ja_indexado(assinatura):
            # Sair da pasta de entrada mesmo assim. Deixado ali, o arquivo seria
            # reexaminado a cada abertura do programa e a pasta nunca esvaziaria
            # — e quem largou a copia acharia que o AutoDoc simplesmente ignorou
            # o arquivo. Copia nao se apaga: o original e de quem usa.
            destino = self._recolher(caminho, PASTA_DUPLICADOS)
            return Resultado(
                caminho, ignorado="ja indexado", destino=destino,
            )

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
        except OcrIndisponivel as erro:
            return self._esperar_ocr(caminho, erro)
        except (ExtracaoIndisponivel, OSError) as erro:
            logger.warning("nao foi possivel ler %s: %s", caminho.name, erro)
            texto, origem, ilegivel = "", "não foi possível ler o arquivo", str(erro)

        etapas.append({
            "titulo": "Extração de texto",
            "detalhe": ilegivel or f"{origem} · {len(texto)} caracteres lidos",
        })

        classificacao = classificar(texto, caminho.name)
        if ilegivel:
            classificacao = Classificacao(
                categoria=NAO_CLASSIFICADO,
                confianca=0.0,
                regra=f"não foi possível ler o conteúdo — {ilegivel}",
            )
        else:
            classificacao = _pelo_tipo(caminho, texto, classificacao)
        etapas.append({
            "titulo": "Classificação",
            "detalhe": (
                f"{classificacao.regra} · confiança "
                f"{classificacao.confianca:.0%}"
            ),
        })

        data_pasta, detalhe_data = self._resolver_data(texto, classificacao.categoria, caminho)
        data = extrair_data(texto) or data_pasta
        etapas.append({"titulo": "Data", "detalhe": detalhe_data})

        try:
            destino = self._arquivar(caminho, classificacao, data_pasta)
        except OSError as erro:
            # Travado por outro programa (comum no Windows), caminho longo,
            # disco cheio. Nada foi fichado: o arquivo fica na entrada e a
            # varredura periodica tenta de novo.
            logger.warning("nao foi possivel mover %s: %s; nova tentativa depois",
                           caminho.name, erro)
            return Resultado(caminho, ignorado=f"nao foi possivel mover: {erro}")
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
            data_pasta=data_pasta,
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
            # Ficha de versao antiga nao tem `data_pasta`: a pasta era pela data.
            ficha.data_pasta or ficha.data_documento,
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

        classificacao = _pelo_tipo(caminho, texto, classificar(texto, caminho.name))
        data_pasta, detalhe_data = self._resolver_data(texto, classificacao.categoria, caminho)

        return Ficha(
            arquivo=caminho.name,
            caminho=self.catalogo.relativo(caminho),
            categoria=classificacao.categoria,
            data_documento=extrair_data(texto) or data_pasta,
            data_pasta=data_pasta,
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
    def _resolver_data(
        texto: str, categoria: str, caminho: Path | None = None
    ) -> tuple[str | None, str]:
        """A data do documento e a explicacao de como ela foi escolhida.

        Qual data vale depende do tipo (ver `datas.data_do_documento`). Sem data
        no texto, nao ha data: o documento vai para `sem-data/`. Usar a data de
        modificacao do arquivo, como antes, arquivava um PDF baixado hoje no mes
        de hoje — e ninguem o achava no mes a que ele pertence.

        Imagem sem texto de documento so tem uma data real: a da captura, que a
        camera grava no EXIF. O que o OCR leu de um icone nao e data de nada.
        """
        if categoria == IMAGENS and caminho is not None:
            _tamanho, capturada = sobre_a_imagem(caminho)
            if capturada:
                return capturada, f"data de captura da foto (EXIF): {capturada}"
            return None, "imagem sem data de captura → pasta sem-data"
        return data_do_documento(texto, categoria)

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

    def _esperar_ocr(self, caminho: Path, erro: OcrIndisponivel) -> Resultado:
        """Foto ou scan sem OCR na maquina: espera, em vez de ir para revisao.

        Na revisao ela ficava como "ilegivel" para sempre, mesmo depois de o
        Tesseract ser instalado. Em `_Aguardando_OCR/` a varredura a devolve ao
        pipeline assim que o OCR passar a existir.
        """
        logger.warning("%s espera o OCR: %s", caminho.name, erro)
        if caminho.parent.name == PASTA_AGUARDANDO_OCR:
            # Ja estava esperando; mover para o mesmo lugar so o renomearia.
            return Resultado(caminho, ignorado="aguardando OCR", destino=caminho)
        destino = self._recolher(caminho, PASTA_AGUARDANDO_OCR)
        return Resultado(caminho, ignorado="aguardando OCR", destino=destino)

    def _recolher(self, caminho: Path, nome_pasta: str) -> Path | None:
        """Tira o arquivo da pasta de entrada, sem arquiva-lo de fato."""
        pasta = self.config.pasta_saida / nome_pasta
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            destino = self._nome_livre(pasta / caminho.name)
            shutil.move(str(caminho), destino)
            return destino
        except OSError as erro:
            logger.warning("nao foi possivel mover %s: %s", caminho.name, erro)
            return None

    def _arquivar(
        self, caminho: Path, classificacao: Classificacao, data: str | None
    ) -> Path:
        pasta = self._pasta_destino(classificacao, data)
        pasta.mkdir(parents=True, exist_ok=True)

        destino = self._nome_livre(pasta / caminho.name)
        try:
            shutil.move(str(caminho), destino)
        except OSError:
            # Entre volumes o move e copia + apagar; se apagar a origem falhou,
            # o destino ficou com uma copia. Deixa-la geraria "nome (2)" na
            # proxima tentativa — o original continua na entrada, ele vale.
            if caminho.exists() and destino.exists():
                destino.unlink()
            raise
        return destino

    def _relativo(self, destino: Path) -> str:
        """Caminho curto, a partir da pasta de saida, para mostrar na tela."""
        try:
            return str(destino.parent.relative_to(self.config.pasta_saida)) + "/"
        except ValueError:
            return str(destino.parent) + "/"

    def _fazer_backup(self, destino: Path, classificacao: Classificacao) -> None:
        """Copia para a pasta sincronizada. Falhar aqui nao invalida o resto.

        A pasta de backup costuma ser do Drive ou do OneDrive, que ficam
        indisponiveis sozinhos. O documento ja esta arquivado e fichado quando
        isto roda — perder a copia e um aviso, nao um erro de processamento.
        """
        if self.config.pasta_backup is None:
            return
        # Mesmo nome de pasta do arquivo principal, para o backup nao virar uma
        # organizacao paralela e diferente.
        nome = (
            PASTA_REVISAO
            if classificacao.categoria == NAO_CLASSIFICADO
            else classificacao.categoria
        )
        try:
            pasta = self.config.pasta_backup / nome
            pasta.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, self._nome_livre(pasta / destino.name))
        except OSError as erro:
            logger.warning("backup de %s falhou: %s", destino.name, erro)

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
