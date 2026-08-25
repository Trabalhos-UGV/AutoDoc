"""Classificacao de documentos por regras de palavras-chave.

Cada categoria tem termos com peso. Alem da categoria, o classificador devolve
a confianca, a regra que disparou e as palavras-chave encontradas — e isso nao
e enfeite: e o que a tela mostra no painel "por que foi classificado assim", e
e o que permite discordar do sistema em vez de so acreditar nele.

Abaixo do limiar de confianca o documento nao e chutado numa categoria: vira
"nao classificado" e vai para revisao manual. Classificar errado e pior do que
admitir duvida, porque o arquivo some numa pasta onde ninguem vai procurar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

CATEGORIA_PADRAO = "outros"
NAO_CLASSIFICADO = "nao_classificado"

# Abaixo disto o documento vai para revisao manual.
LIMIAR = 0.60

# Quanto a confianca vem de cada coisa. "Cobertura" e quanta evidencia da regra
# apareceu; "margem" e o quanto a vencedora se destacou da segunda colocada.
# Uma so nao basta: um texto que casa muitos termos de duas categorias ao mesmo
# tempo tem cobertura alta e mesmo assim e duvidoso, e um texto que casa um
# termo unico e raro tem margem total sem ter evidencia nenhuma.
PESO_COBERTURA = 0.55
PESO_MARGEM = 0.45

# categoria -> {termo: peso}
#
# Os termos sao os que documentos reais trazem, e nao os que descrevem a
# categoria: uma conta de luz nao escreve "distribuidora", escreve "CEMIG" e
# "total a pagar". Escrever a regra pensando no documento, e nao no conceito,
# e o que faz a diferenca entre acertar e mandar tudo para revisao.
REGRAS: dict[str, dict[str, int]] = {
    "conta_luz": {
        "kwh": 4, "consumo faturado": 4, "energia eletrica": 3,
        "leitura anterior": 3, "leitura atual": 3, "bandeira tarifaria": 4,
        "total a pagar": 2, "consumo": 1, "distribuidora": 2,
        # Concessionarias — na pratica e o sinal mais forte de todos.
        "cemig": 4, "copel": 4, "enel": 4, "cpfl": 4, "equatorial": 4,
        "neoenergia": 4, "celesc": 4, "light": 3,
    },
    "conta_agua": {
        "hidrometro": 4, "saneamento": 4, "consumo de agua": 4,
        "metros cubicos": 3, "m3": 2, "esgoto": 3, "agua": 1,
        "sabesp": 4, "copasa": 4, "sanepar": 4, "cagece": 4, "embasa": 4,
    },
    "nota_fiscal": {
        "danfe": 5, "nota fiscal": 4, "nota fiscal eletronica": 5,
        "nfe": 3, "chave de acesso": 4, "valor total da nota": 4,
        "icms": 3, "natureza da operacao": 4, "cnpj": 2, "valor total": 2,
    },
    "boleto": {
        "linha digitavel": 5, "codigo de barras": 4, "cedente": 4,
        "sacado": 3, "nosso numero": 4, "beneficiario": 3,
        "boleto": 4, "vencimento": 2, "agencia/codigo": 3,
    },
    "contrato": {
        "contrato de locacao": 5, "clausula": 4, "clausula primeira": 4,
        "locador": 4, "locatario": 4, "contratante": 4, "contratada": 4,
        "das partes": 3, "contrato": 3, "foro da comarca": 4,
    },
    "comprovante": {
        "comprovante": 4, "pix": 4, "id da transacao": 5,
        "chave pix": 5, "transferencia": 3, "comprovante de pagamento": 5,
        "autenticacao": 3, "favorecido": 3, "pagamento": 1,
    },
    "documento_pessoal": {
        "carteira de identidade": 5, "cnh": 4, "orgao expedidor": 4,
        "filiacao": 4, "naturalidade": 4, "cpf": 2, "rg": 2, "identidade": 3,
    },
}

# Pontuacao a partir da qual a evidencia ja e considerada suficiente. Nao e a
# soma dos pesos: um documento nunca tras todos os termos possiveis, e varios
# deles se excluem — nenhuma conta de luz vem da CEMIG e da COPEL ao mesmo
# tempo. Exigir o teto mandaria todo documento legitimo para revisao.
ALVOS: dict[str, int] = {
    "conta_luz": 12,
    "conta_agua": 11,
    "nota_fiscal": 12,
    "boleto": 12,
    "contrato": 12,
    "comprovante": 12,
    "documento_pessoal": 10,
}

ROTULOS: dict[str, str] = {
    "conta_luz": "Conta de energia",
    "conta_agua": "Conta de água",
    "nota_fiscal": "Nota fiscal",
    "boleto": "Boleto",
    "contrato": "Contrato",
    "comprovante": "Comprovante",
    "documento_pessoal": "Documento pessoal",
    CATEGORIA_PADRAO: "Outros",
    NAO_CLASSIFICADO: "Não classificado",
}


@dataclass
class Classificacao:
    """O que o classificador concluiu, e por que."""

    categoria: str
    confianca: float
    regra: str
    chaves: list[str] = field(default_factory=list)

    @property
    def rotulo(self) -> str:
        return ROTULOS.get(self.categoria, self.categoria)

    @property
    def revisar(self) -> bool:
        return self.categoria == NAO_CLASSIFICADO


def _normalizar_mapeado(texto: str) -> tuple[str, list[int]]:
    """Normaliza guardando, para cada caractere, de onde ele veio.

    O mapa existe para conseguir devolver a palavra-chave **como ela aparece no
    documento** ("CONSUMO FATURADO", "kWh") em vez da forma interna da regra.
    Tirar acento e juntar espacos muda o tamanho do texto, entao sem guardar os
    indices nao da para voltar ao original.
    """
    saida: list[str] = []
    indices: list[int] = []
    espaco_pendente = False

    for posicao, caractere in enumerate(texto):
        decomposto = unicodedata.normalize("NFKD", caractere.lower())
        decomposto = "".join(c for c in decomposto if not unicodedata.combining(c))
        if not decomposto:
            continue

        if decomposto.isspace():
            espaco_pendente = True
            continue

        if espaco_pendente and saida:
            saida.append(" ")
            indices.append(posicao)
            espaco_pendente = False

        for c in decomposto:
            saida.append(c)
            indices.append(posicao)

    return "".join(saida), indices


def normalizar(texto: str) -> str:
    """Minusculas, sem acentos e com espacamento uniforme."""
    return _normalizar_mapeado(texto)[0]


def _encontrar(termo: str, normalizado: str) -> re.Match | None:
    # \b evita que "agua" case dentro de "aguardando".
    return re.search(rf"\b{re.escape(termo)}\b", normalizado)


def pontuar(texto: str) -> dict[str, int]:
    """Pontuacao de cada categoria para o texto informado."""
    normalizado = normalizar(texto)
    placar: dict[str, int] = {}

    for categoria, termos in REGRAS.items():
        total = sum(
            peso for termo, peso in termos.items() if _encontrar(termo, normalizado)
        )
        if total:
            placar[categoria] = total

    return placar


def _chaves_encontradas(categoria: str, texto: str) -> list[str]:
    """Os termos da categoria que aparecem no texto, com a grafia do documento."""
    normalizado, indices = _normalizar_mapeado(texto)
    achadas: list[str] = []

    # Do termo mais pesado para o mais leve: o painel mostra poucas, e as que
    # aparecem devem ser as que mais pesaram na decisao.
    termos = sorted(REGRAS[categoria].items(), key=lambda item: -item[1])
    for termo, _peso in termos:
        casamento = _encontrar(termo, normalizado)
        if not casamento:
            continue
        inicio = indices[casamento.start()]
        fim = indices[casamento.end() - 1] + 1
        achadas.append(texto[inicio:fim].strip())

    return achadas


def _confianca(pontos: int, alvo: int, segunda: int) -> float:
    """Mistura a evidencia acumulada com a distancia para a segunda colocada.

    O denominador da margem e `pontos + 1`, e nao `pontos`, para que nem o
    documento mais obvio chegue a 100%: um classificador por palavra-chave nao
    tem como afirmar certeza absoluta, e mostrar "100%" na tela seria prometer
    uma coisa que o metodo nao entrega.
    """
    cobertura = min(1.0, pontos / alvo) if alvo else 0.0
    margem = (pontos - segunda) / (pontos + 1) if pontos else 0.0
    return round(PESO_COBERTURA * cobertura + PESO_MARGEM * margem, 4)


def _virgula(numero: float) -> str:
    """Numero com virgula decimal, como se escreve em portugues."""
    return f"{numero:.2f}".replace(".", ",")


def classificar(texto: str) -> Classificacao:
    """Classifica o documento e explica a decisao."""
    placar = pontuar(texto)

    if not placar:
        return Classificacao(
            categoria=NAO_CLASSIFICADO,
            confianca=0.0,
            regra="nenhuma regra encontrou termo algum no texto extraído",
        )

    ordenado = sorted(placar.items(), key=lambda item: -item[1])
    categoria, pontos = ordenado[0]
    segunda_categoria, segunda_pontos = (
        ordenado[1] if len(ordenado) > 1 else (None, 0)
    )

    # Empate no topo e duvida, nao escolha.
    if segunda_pontos == pontos:
        return Classificacao(
            categoria=NAO_CLASSIFICADO,
            confianca=0.0,
            regra=(
                f'empate entre "{categoria}" e "{segunda_categoria}" '
                f"com {pontos} pontos cada — nenhuma delas se destacou"
            ),
            chaves=_chaves_encontradas(categoria, texto),
        )

    alvo = ALVOS.get(categoria, sum(REGRAS[categoria].values()))
    confianca = _confianca(pontos, alvo, segunda_pontos)
    chaves = _chaves_encontradas(categoria, texto)

    disputa = (
        f"; segunda colocada: {segunda_categoria} com {segunda_pontos}"
        if segunda_categoria
        else "; nenhuma outra regra pontuou"
    )
    plural = "termo encontrado" if len(chaves) == 1 else "termos encontrados"
    regra = (
        f'regra "{categoria}": {len(chaves)} {plural}, '
        f"{pontos} de {alvo} pontos necessários{disputa}"
    )

    if confianca < LIMIAR:
        return Classificacao(
            categoria=NAO_CLASSIFICADO,
            confianca=confianca,
            regra=f"{regra} — confiança abaixo do limiar de {_virgula(LIMIAR)}",
            chaves=chaves,
        )

    return Classificacao(
        categoria=categoria, confianca=confianca, regra=regra, chaves=chaves
    )
