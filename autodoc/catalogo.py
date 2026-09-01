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
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

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
