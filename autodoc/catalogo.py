"""Catalogo dos documentos do AutoDoc.

**A pasta organizada e a verdade.** O que existe de verdade sao os arquivos em
`<saida>/<categoria>/<ano>/<mes>/`; este catalogo e so um caderno de fichas
sobre eles, guardado em `<saida>/.autodoc/catalogo.jsonl`. Apagar esse caderno
nao apaga nada: na abertura seguinte o AutoDoc varre as pastas e o remonta.

E por isso que aqui nao ha banco de dados. Um banco seria uma segunda verdade,
que precisaria ser mantida de acordo com a primeira — e quando as duas
discordassem, ganharia a errada. Uma ficha que perdeu o arquivo e lixo; um
arquivo sem ficha e so um documento que ainda nao foi lido.

O formato e JSONL: uma ficha por linha, texto puro, legivel a olho nu. Gravar
documento novo e escrever **uma linha no fim** do arquivo, sem reescrever o
resto — entao uma queda no meio da escrita perde no maximo a ultima ficha, que
a varredura da pasta recupera depois.
"""

from __future__ import annotations

import json
import logging
import os
import re
from bisect import bisect_left
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from pathlib import Path

from .classificador import NAO_CLASSIFICADO, ROTULOS, normalizar

logger = logging.getLogger(__name__)

# Pasta escondida dentro da propria pasta organizada. Fica junto do que ela
# descreve: levar a pasta organizada para outra maquina leva o catalogo junto.
PASTA_CATALOGO = ".autodoc"
NOME_CATALOGO = "catalogo.jsonl"

# Pastas com nome proprio dentro da saida. Ficam aqui, e nao no pipeline,
# porque quem le a pasta organizada de volta e este modulo — ele precisa
# saber que `_Revisar/` nao e uma categoria.
PASTA_REVISAO = "_Revisar"
PASTA_DUPLICADOS = "_Duplicados"

# Teto do texto guardado por ficha. Um PDF de centenas de paginas nao pode
# transformar uma linha do catalogo em megabytes; o que passa disso nao muda a
# classificacao nem a busca, que ja decidiram com o comeco do documento.
LIMITE_TEXTO = 200_000


@dataclass
class Ficha:
    """O que se sabe sobre um documento arquivado.

    `caminho` e guardado **relativo a pasta de saida**, e nao absoluto: assim
    mover a pasta organizada inteira para outro lugar (ou outra maquina) nao
    invalida o catalogo.
    """

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
    processado_em: str = ""
    id: int = 0

    def __post_init__(self) -> None:
        self.texto = self.texto[:LIMITE_TEXTO]
        if not self.processado_em:
            self.processado_em = datetime.now().isoformat(timespec="seconds")

    @classmethod
    def de_json(cls, dados: dict) -> "Ficha":
        """Monta a ficha ignorando campos que esta versao nao conhece.

        Um catalogo escrito por uma versao mais nova pode trazer campo a mais, e
        um mais antigo, campo a menos. Nenhum dos dois e motivo para o programa
        nao abrir.
        """
        conhecidos = {campo.name for campo in fields(cls)}
        return cls(**{c: v for c, v in dados.items() if c in conhecidos})

    def para_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class Catalogo:
    """As fichas dos documentos arquivados, carregadas do disco."""

    def __init__(self, pasta_saida: Path) -> None:
        self.pasta_saida = Path(pasta_saida)
        self.pasta = self.pasta_saida / PASTA_CATALOGO
        self.arquivo = self.pasta / NOME_CATALOGO

        self._fichas: dict[int, Ficha] = {}
        self._hashes: set[str] = set()
        self._proximo_id = 1
        # palavra -> ids das fichas em que ela aparece, e a mesma lista de
        # palavras ordenada, para achar prefixo por busca binaria.
        self._indice: dict[str, set[int]] = {}
        self._ordenadas: list[str] | None = None

        self.pasta.mkdir(parents=True, exist_ok=True)
        self.carregar()

    def __len__(self) -> int:
        return len(self._fichas)

    def carregar(self) -> None:
        """Le o catalogo do disco, pulando linha corrompida em vez de parar.

        Uma linha ilegivel e a que a queda cortou pela metade — perder essa
        ficha e aceitavel, nao abrir o programa por causa dela nao e.
        """
        self._fichas.clear()
        self._hashes.clear()
        self._indice.clear()
        self._ordenadas = None
        self._proximo_id = 1

        if not self.arquivo.exists():
            return

        with self.arquivo.open(encoding="utf-8") as caderno:
            for numero, linha in enumerate(caderno, start=1):
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    ficha = Ficha.de_json(json.loads(linha))
                except (json.JSONDecodeError, TypeError) as erro:
                    logger.warning(
                        "ficha ilegivel na linha %d do catalogo: %s", numero, erro
                    )
                    continue
                self._guardar(ficha)

    def _guardar(self, ficha: Ficha) -> None:
        """Coloca a ficha na memoria — sem tocar no disco."""
        # A ultima ficha de um mesmo id vence: e assim que uma correcao gravada
        # depois (categoria mudada a mao) sobrescreve a versao antiga.
        self._fichas[ficha.id] = ficha
        self._hashes.add(ficha.hash)
        self._proximo_id = max(self._proximo_id, ficha.id + 1)
        self._indexar(ficha)

    def caminho_de(self, ficha: Ficha) -> Path:
        """O caminho absoluto do arquivo desta ficha, aqui nesta maquina."""
        return self.pasta_saida / ficha.caminho

    def relativo(self, caminho: Path) -> str:
        """O caminho como ele deve ser guardado: relativo a pasta de saida."""
        try:
            return str(Path(caminho).relative_to(self.pasta_saida))
        except ValueError:
            # Fora da pasta organizada — guarda absoluto, que ao menos aponta
            # para o arquivo certo enquanto ele estiver ali.
            return str(caminho)

    # --------------------------------------------------------- escrita

    def _anexar(self, ficha: Ficha) -> None:
        """Escreve uma linha no fim do caderno e garante que ela chegou ao disco.

        `flush` porque o AutoDoc costuma ser fechado pela janela, sem aviso: uma
        ficha que ficou no buffer do Python quando o processo morreu e uma ficha
        perdida.
        """
        with self.arquivo.open("a", encoding="utf-8") as caderno:
            caderno.write(ficha.para_json() + "\n")
            caderno.flush()

    def inserir(self, ficha: Ficha) -> int | None:
        """Fixa a ficha no catalogo. Devolve None se o documento ja estava la.

        A comparacao e pelo hash do conteudo, e nao pelo nome: o mesmo boleto
        salvo como `boleto.pdf` e `boleto (1).pdf` e um documento so.
        """
        if ficha.hash in self._hashes:
            return None

        ficha.id = self._proximo_id
        self._guardar(ficha)
        self._anexar(ficha)
        return ficha.id

    def compactar(self) -> None:
        """Reescreve o caderno so com as fichas que valem agora.

        O arquivo novo e escrito ao lado e trocado de lugar com `os.replace`,
        que e atomico: ou o catalogo antigo esta inteiro, ou o novo esta — nunca
        um meio-termo, que e o que sobraria de escrever por cima do original e
        ser interrompido no meio.
        """
        temporario = self.arquivo.with_suffix(".jsonl.novo")
        with temporario.open("w", encoding="utf-8") as caderno:
            for ficha in sorted(self._fichas.values(), key=lambda f: f.id):
                caderno.write(ficha.para_json() + "\n")
            caderno.flush()
        os.replace(temporario, self.arquivo)

    def ja_indexado(self, hash_arquivo: str) -> bool:
        return hash_arquivo in self._hashes

    # ---------------------------------------------------------- indice

    def _indexar(self, ficha: Ficha) -> None:
        """Aponta cada palavra da ficha para o id dela."""
        for palavra in _palavras(_texto_indexavel(ficha)):
            self._indice.setdefault(palavra, set()).add(ficha.id)
        # A lista ordenada envelheceu; so vale a pena refaze-la na hora da
        # busca, porque carregar o catalogo chama isto uma vez por ficha.
        self._ordenadas = None

    def _reindexar(self) -> None:
        """Refaz indice e hashes do zero — depois de descartar ou alterar fichas."""
        self._indice.clear()
        self._hashes.clear()
        self._ordenadas = None
        for ficha in self._fichas.values():
            self._hashes.add(ficha.hash)
            self._indexar(ficha)

    def _ids_por_prefixo(self, prefixo: str) -> set[int]:
        """Fichas que tem alguma palavra comecando por `prefixo`.

        Busca binaria na lista ordenada e depois anda para a frente enquanto as
        palavras continuarem comecando assim. E o que faz "marc" achar "marco"
        sem achar "demarcado": a comparacao e do inicio da palavra, e nao de um
        pedaco no meio dela como o LIKE fazia.
        """
        if self._ordenadas is None:
            self._ordenadas = sorted(self._indice)

        achados: set[int] = set()
        for posicao in range(bisect_left(self._ordenadas, prefixo), len(self._ordenadas)):
            palavra = self._ordenadas[posicao]
            if not palavra.startswith(prefixo):
                break
            achados |= self._indice[palavra]
        return achados

    # ----------------------------------------------------- reconciliacao

    def arquivos_no_disco(self) -> list[Path]:
        """Todo documento que existe de verdade dentro da pasta organizada.

        Fora ficam a propria pasta do catalogo e os arquivos que o sistema
        operacional espalha (`.DS_Store`, `Thumbs.db`), que nao sao documentos
        de ninguem.
        """
        if not self.pasta_saida.exists():
            return []

        achados = []
        for caminho in sorted(self.pasta_saida.rglob("*")):
            if not caminho.is_file() or caminho.name.startswith("."):
                continue
            if PASTA_CATALOGO in caminho.relative_to(self.pasta_saida).parts:
                continue
            achados.append(caminho)
        return achados

    def categoria_do_caminho(self, caminho: Path) -> str | None:
        """A categoria que a pasta onde o arquivo esta ja declara.

        Quem colocou o arquivo em `contrato/` disse que e um contrato — e uma
        pessoa dizendo isso vale mais do que o classificador adivinhando.
        """
        partes = Path(self.relativo(caminho)).parts
        if not partes or len(partes) < 2:
            return None
        if partes[0] == PASTA_REVISAO:
            return NAO_CLASSIFICADO
        return partes[0] if partes[0] in ROTULOS else None

    def reconciliar(self, analisar=None) -> dict[str, int]:
        """Poe o catalogo de acordo com a pasta, que e quem manda.

        Ficha cujo arquivo sumiu e descartada — apagou no Finder, sumiu da tela.
        Arquivo sem ficha e lido e fichado **onde esta**, sem ser movido: se
        alguem arrastou um contrato para `contrato/2026/03/` a mao, o lugar
        escolhido e para ser respeitado, nao corrigido.

        `analisar` recebe um caminho e devolve uma Ficha; e por onde o pipeline
        empresta a leitura e a classificacao sem que este modulo precise
        conhece-los. Sem ele, o que a pasta diz ja e o bastante para fichar.

        Devolve quantas fichas foram descartadas e quantas foram criadas.
        """
        presentes = self.arquivos_no_disco()
        fichados = {self.caminho_de(f) for f in self._fichas.values()}

        perdidas = [
            identificador
            for identificador, ficha in self._fichas.items()
            if self.caminho_de(ficha) not in set(presentes)
        ]
        for identificador in perdidas:
            del self._fichas[identificador]
        if perdidas:
            self._reindexar()

        criadas = 0
        for caminho in presentes:
            if caminho in fichados:
                continue
            ficha = self._fichar_encontrado(caminho, analisar)
            if ficha and self.inserir(ficha) is not None:
                criadas += 1

        if perdidas:
            self.compactar()

        if perdidas or criadas:
            logger.info(
                "catalogo reconciliado: %d ficha(s) descartada(s), %d recuperada(s)",
                len(perdidas), criadas,
            )
        return {"descartadas": len(perdidas), "recuperadas": criadas}

    def _fichar_encontrado(self, caminho: Path, analisar) -> Ficha | None:
        """Monta a ficha de um arquivo achado solto na pasta organizada."""
        try:
            if analisar is not None:
                ficha = analisar(caminho)
                if ficha is None:
                    return None
            else:
                ficha = Ficha(
                    arquivo=caminho.name,
                    caminho=self.relativo(caminho),
                    categoria=NAO_CLASSIFICADO,
                    data_documento=None,
                    texto="",
                    hash="",
                    regra="ficha remontada a partir da pasta, sem releitura",
                    tamanho=caminho.stat().st_size,
                )
        except OSError as erro:
            logger.warning("nao foi possivel fichar %s: %s", caminho.name, erro)
            return None

        # A pasta manda na categoria: foi uma pessoa que colocou o arquivo ali.
        declarada = self.categoria_do_caminho(caminho)
        if declarada:
            ficha.categoria = declarada
        ficha.caminho = self.relativo(caminho)
        return ficha

    # ---------------------------------------------------------- consulta

    def _como_dict(self, ficha: Ficha) -> dict:
        """A ficha no formato que o resto do programa consome.

        `caminho` sai **absoluto**: e guardado relativo para o catalogo ser
        portatil, mas quem recebe quer abrir o arquivo, nao remontar o caminho.
        """
        dados = asdict(ficha)
        dados["caminho"] = str(self.caminho_de(ficha))
        return dados

    def listar(self, limite: int = 50, categoria: str | None = None) -> list[dict]:
        """Os documentos mais recentes, opcionalmente de uma categoria so."""
        fichas = [
            f for f in self._fichas.values()
            if categoria is None or f.categoria == categoria
        ]
        fichas.sort(key=_ordem, reverse=True)
        return [self._como_dict(f) for f in fichas[:limite]]

    def buscar(self, termo: str, limite: int = 20) -> list[dict]:
        """Documentos que casam com todas as palavras digitadas.

        Cada palavra vale como prefixo e **todas** precisam aparecer: "conta
        luz" acha "conta de luz de marco" em vez de trazer tudo que tem "conta"
        ou "luz". Termo vazio nao e busca — devolve a listagem normal.
        """
        prefixos = _palavras(termo)
        if not prefixos:
            return self.listar(limite)

        ids: set[int] | None = None
        for prefixo in prefixos:
            achados = self._ids_por_prefixo(prefixo)
            ids = achados if ids is None else ids & achados
            if not ids:
                return []

        fichas = [self._fichas[i] for i in ids or ()]
        fichas.sort(key=_ordem, reverse=True)
        return [self._como_dict(f) for f in fichas[:limite]]

    def por_id(self, identificador: int) -> Ficha | None:
        """A ficha de um documento — o que as acoes da tela precisam achar."""
        return self._fichas.get(identificador)

    def contar_por_categoria(self) -> dict[str, int]:
        """Quantos documentos ha em cada categoria — alimenta a barra lateral."""
        contagem: dict[str, int] = {}
        for ficha in self._fichas.values():
            contagem[ficha.categoria] = contagem.get(ficha.categoria, 0) + 1
        return dict(sorted(contagem.items(), key=lambda item: -item[1]))

    def estatisticas(self) -> dict[str, int]:
        """Os quatro numeros do topo da tela."""
        hoje = date.today().isoformat()
        fichas = list(self._fichas.values())
        return {
            "arquivados": len(fichas),
            "hoje": sum(1 for f in fichas if f.processado_em.startswith(hoje)),
            "ocr": sum(1 for f in fichas if "OCR" in f.origem),
            "revisar": sum(1 for f in fichas if f.categoria == NAO_CLASSIFICADO),
        }


def _ordem(ficha: Ficha) -> tuple[str, int]:
    """Como as fichas saem para a tela: a mais recente primeiro.

    Documento sem data vai para o fim, e nao para o comeco, que e onde uma
    string vazia cairia numa ordenacao decrescente.
    """
    return (ficha.data_documento or "0000-00-00", ficha.id)


def _texto_indexavel(ficha: Ficha) -> str:
    """Tudo o que deve ser alcancavel pela busca, junto num texto so.

    O rotulo entra ao lado da categoria interna para que procurar "energia"
    ache o que esta guardado como `conta_luz`.
    """
    return " ".join([
        ficha.arquivo,
        ficha.categoria,
        ROTULOS.get(ficha.categoria, ""),
        ficha.data_documento or "",
        " ".join(ficha.palavras_chave),
        ficha.texto,
    ])


def _palavras(texto: str) -> set[str]:
    """As palavras do texto, sem acento e em minusculas.

    Reaproveita o `normalizar` da classificacao de proposito: buscar e
    classificar tem que enxergar "MARCO", "março" e "Marco" como a mesma coisa,
    e duas normalizacoes diferentes no mesmo programa acabariam discordando.
    """
    return {p for p in re.split(r"[^0-9a-z]+", normalizar(texto)) if p}

