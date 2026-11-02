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
from pathlib import Path

CATEGORIA_PADRAO = "outros"
NAO_CLASSIFICADO = "nao_classificado"

# Identificados pelo tipo de arquivo, quando o conteudo nao e de documento
# nenhum (ver `pipeline._pelo_tipo`): nao saem do classificador por palavra.
IMAGENS = "imagens"
TEXTOS = "textos"

# Abaixo disto o documento vai para revisao manual.
LIMIAR = 0.60

# A categoria vencedora precisa de ao menos um termo com este peso. Termos
# fracos ("pix", "cpf", "vencimento") aparecem em quase todo documento: uma
# carta do banco que so cita "cadastre sua chave Pix" virava comprovante com 82%
# de confianca, porque era a unica categoria que pontuava.
PESO_FORTE = 3

# Boleto e forma de pagamento, nao tipo de documento: fatura de cartao, conta de
# luz e IPTU chegam todos com linha digitavel. Quando um destes tipos tem termo
# forte no texto, o "boleto" sai da disputa — senao a fatura empatava com ele.
PAGOS_POR_BOLETO = {"fatura_cartao", "impostos", "conta_luz", "conta_agua", "conta_gas", "telefone_internet"}

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
#
# Palavra comum nao entra sozinha: "das" esta em "das partes", "claro" em
# "claro que", "oi" em qualquer conversa. Por isso "das mei", "claro s.a.",
# "oi fibra".
REGRAS: dict[str, dict[str, int]] = {
    "conta_luz": {
        "kwh": 4, "consumo faturado": 4, "energia eletrica": 3, "conta de energia": 3,
        # Leitura anterior/atual estao em toda conta de consumo — agua e gas
        # tambem. Valiam 3 cada e puxavam a conta de gas para luz.
        "leitura anterior": 1, "leitura atual": 1, "bandeira tarifaria": 4,
        "total a pagar": 2, "consumo": 1, "distribuidora": 2,
        # Concessionarias — na pratica e o sinal mais forte de todos.
        "cemig": 4, "copel": 4, "enel": 4, "cpfl": 4, "equatorial": 4,
        "neoenergia": 4, "celesc": 4, "light": 3, "energisa": 4, "edp": 4,
        "fatura de energia": 3,
        "elektro": 4, "rge": 4, "ceee": 4, "coelba": 4, "celpe": 4, "cosern": 4,
    },
    "conta_agua": {
        "hidrometro": 4, "saneamento": 4, "consumo de agua": 4,
        "metros cubicos": 3, "m3": 2, "esgoto": 3, "agua": 1,
        "sabesp": 4, "copasa": 4, "sanepar": 4, "cagece": 4, "embasa": 4,
        "cedae": 4, "corsan": 4, "caesb": 4, "compesa": 4, "casan": 4, "saneago": 4,
    },
    "conta_gas": {
        "comgas": 5, "naturgy": 5, "gas canalizado": 5, "gas natural": 4, "gas": 2,
        "gas natural canalizado": 5, "gas encanado": 5, "fornecimento de gas": 4,
    },
    "telefone_internet": {
        "vivo": 4, "telefonica": 4, "claro s.a": 4, "tim s.a": 4, "oi fibra": 4,
        "telecomunicacao": 4, "telecomunicacoes": 4, "banda larga": 4,
        "fibra": 2, "internet": 2, "plano": 1,
    },
    "fatura_cartao": {
        "fatura do cartao": 5, "cartao de credito": 4, "total da fatura": 4,
        "pagamento minimo": 4, "limite disponivel": 4, "fechamento": 3,
    },
    "holerite": {
        "contracheque": 5, "holerite": 5, "recibo de pagamento de salario": 5,
        "salario base": 4, "liquido a receber": 4, "fgts": 3, "inss": 2,
        "irrf": 2, "competencia": 2,
    },
    "impostos": {
        "iptu": 5, "ipva": 5, "imposto predial": 5, "inscricao imobiliaria": 4,
        "das mei": 5, "simples nacional": 4, "documento de arrecadacao": 4,
        "darf": 5, "receita federal": 3, "prefeitura": 3, "periodo de apuracao": 3,
        "secretaria da fazenda": 4, "renavam": 4, "cota unica": 3, "parcela unica": 3,
    },
    "nota_fiscal": {
        "danfe": 5, "nota fiscal": 4, "nota fiscal eletronica": 5,
        "nfe": 3, "nfce": 4, "nota fiscal de consumidor": 5, "cupom fiscal": 5,
        "chave de acesso": 4, "valor total da nota": 4,
        "icms": 3, "natureza da operacao": 4, "cnpj": 2, "valor total": 2,
    },
    "boleto": {
        "linha digitavel": 5, "codigo de barras": 4, "cedente": 4,
        "sacado": 3, "pagador": 3, "nosso numero": 4, "beneficiario": 3,
        "ficha de compensacao": 4, "local de pagamento": 4,
        "boleto": 4, "vencimento": 1, "agencia/codigo": 3,
    },
    "contrato": {
        "contrato de locacao": 5, "clausula": 4, "clausula primeira": 4,
        "locador": 4, "locatario": 4, "contratante": 4, "contratada": 4,
        "das partes": 3, "contrato": 3, "foro da comarca": 4,
    },
    "comprovante": {
        "comprovante": 4, "id da transacao": 5, "transferencia": 3,
        "comprovante de pagamento": 5, "efetuado em": 3,
        "autenticacao": 3, "favorecido": 3,
        # Fracos: estao em quase todo boleto e conta de hoje.
        "pix": 1, "chave pix": 1, "pagamento": 1,
    },
    "documento_pessoal": {
        "carteira de identidade": 5, "carteira nacional de habilitacao": 5,
        "cnh": 4, "orgao expedidor": 4, "registro geral": 4,
        "filiacao": 4, "naturalidade": 4, "identidade": 3, "cpf": 1, "rg": 1,
    },
    # O que nao e conta nem documento pessoal, mas chega do mesmo jeito: tudo o
    # que se baixa vai parar na mesma pasta. Sem estas categorias, um
    # certificado de curso ou uma apostila iam para a revisao com 0%.
    "certificado": {
        "certificamos": 5, "certificado de conclusao": 5, "certificado": 4,
        "carga horaria": 4, "concluiu com exito": 4, "concluiu o curso": 4,
        "conteudo programatico": 3, "participou": 2, "curso": 1,
    },
    "estudos": {
        "exercicios em sala": 5, "lista de exercicios": 5, "atividade em grupo": 5,
        "trabalho academico": 5, "apostila": 5, "plano de aula": 5,
        "aula": 3, "disciplina": 3, "exercicio": 2, "exercicios": 2, "professor": 2,
        # Fraco: tambem e "atividade economica" na nota fiscal.
        "atividade": 2,
    },
    "manual_tecnico": {
        "schematic": 5, "datasheet": 5, "manual de instrucoes": 5,
        "manual do usuario": 5, "instrucoes de montagem": 5,
        "assembly": 4, "pinout": 4, "esquema eletrico": 5,
        "tools and requirements": 3, "designator": 3, "footprint": 3,
        "montagem": 3, "3d printed": 3, "gpio": 2,
    },
    "licenca": {
        "licensed under": 5, "creative commons": 5, "creativecommons": 5,
        "mit license": 5, "gnu general public license": 5, "apache license": 5,
        "permission is hereby granted": 5, "licenca de uso": 5,
        "termos de uso": 4, "license": 3, "licenca": 3,
    },
    "informativo": {
        "campanha de conscientizacao": 5, "cartilha": 5, "folheto": 4,
        "conscientizacao": 3, "como se proteger": 3, "folder": 3,
        # Fraco: contas trazem "mensagem informativa" no rodape.
        "informativo": 1,
    },
    "documentacao": {
        # O normalizador junta "LEIA-ME" em "leiame".
        # "leia me": o nome do arquivo LEIA-ME.md, com o hifen virado espaco.
        "leiame": 5, "leia me": 5, "readme": 5, "como instalar": 4, "como importar": 4,
        "instalacao manual": 4, "instrucoes de instalacao": 4,
        "use quando o usuario": 4, "como usar": 4, "pip install": 4, "npm install": 4,
        "documentacao": 3, "skill": 3, "instalacao": 2,
    },
}

# Pontuacao a partir da qual a evidencia ja e considerada suficiente. Nao e a
# soma dos pesos: um documento nunca tras todos os termos possiveis, e varios
# deles se excluem — nenhuma conta de luz vem da CEMIG e da COPEL ao mesmo
# tempo. Exigir o teto mandaria todo documento legitimo para revisao.
ALVOS: dict[str, int] = {
    "conta_luz": 12,
    "conta_agua": 11,
    "conta_gas": 9,
    "telefone_internet": 11,
    "fatura_cartao": 10,
    "holerite": 9,
    "impostos": 10,
    "nota_fiscal": 12,
    "boleto": 12,
    "contrato": 12,
    "comprovante": 12,
    "documento_pessoal": 10,
    "certificado": 9,
    "estudos": 8,
    "manual_tecnico": 8,
    "licenca": 8,
    "informativo": 8,
    "documentacao": 8,
}

ROTULOS: dict[str, str] = {
    "conta_luz": "Conta de energia",
    "conta_agua": "Conta de água",
    "conta_gas": "Conta de gás",
    "telefone_internet": "Telefone e internet",
    "fatura_cartao": "Fatura do cartão",
    "holerite": "Holerite",
    "impostos": "Impostos",
    "nota_fiscal": "Nota fiscal",
    "boleto": "Boleto",
    "contrato": "Contrato",
    "comprovante": "Comprovante",
    "documento_pessoal": "Documento pessoal",
    "certificado": "Certificado",
    "estudos": "Estudos",
    "manual_tecnico": "Manual técnico",
    "licenca": "Licença",
    "informativo": "Informativo",
    "documentacao": "Documentação",
    IMAGENS: "Imagem",
    TEXTOS: "Arquivo de texto",
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
    pular_ate = -1

    for posicao, caractere in enumerate(texto):
        if posicao < pular_ate:
            continue
        # Hifen invisivel (U+00AD), comum em PDF justificado: "con­sumo".
        if unicodedata.category(caractere) == "Cf":
            continue
        # Hifen entre letras some: "NF-e" vira "nfe", e a palavra quebrada no
        # fim da linha ("consu-\nmo") volta a ser uma so. Entre digitos fica:
        # e separador de data.
        if caractere == "-" and saida and saida[-1].isalpha() and not espaco_pendente:
            seguinte = posicao + 1
            quebra = False
            while seguinte < len(texto) and texto[seguinte].isspace():
                quebra = quebra or texto[seguinte] == "\n"
                seguinte += 1
            if seguinte < len(texto) and texto[seguinte].isalpha() and (quebra or seguinte == posicao + 1):
                pular_ate = seguinte
                continue

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


# O OCR troca letras parecidas: "EQUATORlAL", "CEMlG", "C0NTA". Cada letra
# destas no termo aceita as trocas tipicas no texto.
_TROCAS_DE_OCR = {"i": "[il1]", "l": "[li1]", "o": "[o0]"}


def tolerante(palavra: str) -> str:
    """Regex de `palavra` que aceita as trocas de letra mais comuns do OCR."""
    return "".join(_TROCAS_DE_OCR.get(c, re.escape(c)) for c in palavra)


def _encontrar(termo: str, normalizado: str) -> re.Match | None:
    # \b evita que "agua" case dentro de "aguardando".
    return re.search(rf"\b{tolerante(termo)}\b", normalizado)


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


def _tem_termo_forte(categoria: str, normalizado: str) -> bool:
    return any(peso >= PESO_FORTE and _encontrar(termo, normalizado) for termo, peso in REGRAS[categoria].items())


def com_nome(texto: str, nome: str) -> str:
    """O texto precedido do nome do arquivo, em palavras.

    "certificado-3497633.pdf", "Folder LGPD", "License.txt": quem salva o
    arquivo ja disse o que ele e, e esse sinal era jogado fora. `_`, `-` e `.`
    viram espaco para o nome casar com os termos como palavra.
    """
    palavras = re.sub(r"[_\-.]+", " ", Path(nome).stem).strip() if nome else ""
    return f"{palavras}\n{texto}" if palavras else texto


def classificar(texto: str, nome: str = "") -> Classificacao:
    """Classifica o documento e explica a decisao.

    `nome` e o nome do arquivo; quando vem, conta como parte do texto.
    """
    texto = com_nome(texto, nome)
    placar = pontuar(texto)
    normalizado = normalizar(texto)
    if "boleto" in placar and any(_tem_termo_forte(c, normalizado) for c in PAGOS_POR_BOLETO & placar.keys()):
        del placar["boleto"]

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

    if not _tem_termo_forte(categoria, normalizado):
        return Classificacao(
            categoria=NAO_CLASSIFICADO,
            confianca=0.0,
            regra=(
                f'"{categoria}" só tem termos fracos ({", ".join(chaves)}), '
                f"que aparecem em quase todo documento — não dá para afirmar o tipo"
            ),
            chaves=chaves,
        )

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
