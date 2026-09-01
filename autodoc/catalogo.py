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
        """Refaz o indice do zero — depois de descartar ou alterar fichas."""
        self._indice.clear()
        self._ordenadas = None
        for ficha in self._fichas.values():
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

