"""Identificacao da data do documento — a que decide a pasta dele.

Procura datas nos formatos comuns no Brasil (dd/mm/aaaa, "12 de marco de 2026",
aaaa-mm-dd e, ao lado de um rotulo de referencia, mes/ano: "MAR/2026",
"03/2026") e devolve uma em ISO (aaaa-mm-dd).

**Pegar a primeira data do texto nao serve.** Uma conta de luz comeca com a
leitura anterior, que e do mes passado, e arquivaria a conta no mes errado.
Documentos rotulam a data que importa, entao cada data pertence ao rotulo que
vem logo antes dela — e "DATA DE NASCIMENTO 05/09/1995" pertence a
"nascimento", nao a um "data" generico que por acaso tambem esta ali.

**Qual data vale depende do tipo de documento** (`data_do_documento`), e foi
decidido com o grupo:

    contas mensais e cartao   o mes de referencia ("a conta de marco"),
                              mesmo vencendo em abril; sem referencia no
                              texto, a leitura atual, o fechamento ou o
                              vencimento — nunca uma conta inventada como
                              "vencimento menos um mes", que erraria as
                              contas que vencem no proprio mes
    holerite                  a competencia
    nota fiscal               a emissao
    boleto e imposto          o vencimento
    comprovante               o dia da operacao
    contrato                  a assinatura
    documento pessoal         a expedicao — nunca o nascimento nem a validade

**Sem data no texto, nao ha data.** A versao anterior caia na data de
modificacao do arquivo: um PDF baixado hoje ia para o mes de hoje, sem aviso, e
ninguem o achava depois. O lugar dele e `sem-data/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .classificador import normalizar

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
MESES_CURTOS = {nome[:3]: numero for nome, numero in MESES.items()}

# Nao pode estar colado a letra, ponto ou barra: "v1.2.26" e versao, nao data.
_ANTES = r"(?<![\w./-])"
_DEPOIS = r"(?![\w/-]|\.\d)"

PADRAO_NUMERICO = re.compile(rf"{_ANTES}(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{4}}|\d{{2}}){_DEPOIS}")
PADRAO_ISO = re.compile(rf"{_ANTES}(\d{{4}})-(\d{{2}})-(\d{{2}}){_DEPOIS}")
PADRAO_EXTENSO = re.compile(
    rf"\b(\d{{1,2}})\s+de\s+({'|'.join(MESES)})\s+de\s+(\d{{4}})\b"
)
# Mes e ano, sem dia. So vale ao lado de um rotulo de referencia: solto, "03/26"
# pode ser qualquer numero.
PADRAO_MES_ANO = re.compile(rf"{_ANTES}(\d{{1,2}})[/.-](\d{{4}}|\d{{2}}){_DEPOIS}")
PADRAO_MES_ANO_NOME = re.compile(
    rf"\b({'|'.join([*MESES, *MESES_CURTOS])})\b\.?\s*(?:/|-|de)?\s*(\d{{4}}|\d{{2}})\b"
)

# Na zona de uma data o OCR troca zero por "o" e um por "l" ou "i".
_PARECE_DATA_DE_OCR = re.compile(r"(?<![a-z0-9])[0-9oil]{1,2}[/.-][0-9oil]{1,2}[/.-][0-9oil]{2,4}(?![a-z0-9])")
_CORRECAO_OCR = str.maketrans({"o": "0", "i": "1", "l": "1"})

# Rotulo -> tipo de data. O tipo "ignorar" existe para tomar a data que o
# rotulo indica e tira-la do jogo: nascimento, validade, leitura anterior.
ROTULOS_POR_TIPO: dict[str, str] = {
    "mes/ano de referencia": "referencia",
    "mes de referencia": "referencia",
    "periodo de referencia": "referencia",
    "periodo de apuracao": "referencia",
    "referencia": "referencia",
    "competencia": "referencia",
    "fornecimento": "referencia",
    "fechamento": "fechamento",
    "leitura atual": "leitura",
    "vencimento": "vencimento",
    "vencto": "vencimento",
    "venc": "vencimento",
    "pagar este documento ate": "vencimento",
    "data de emissao": "emissao",
    "data da emissao": "emissao",
    "data emissao": "emissao",
    "emissao": "emissao",
    "data de expedicao": "emissao",
    "data expedicao": "emissao",
    "expedicao": "emissao",
    "data do documento": "documento",
    "data de assinatura": "assinatura",
    "efetuado em": "operacao",
    "pago em": "operacao",
    "data do pagamento": "pagamento",
    "data de pagamento": "pagamento",
    "pagamento": "pagamento",
    "data": "data",
    # Datas que existem no documento mas nunca sao "a data" dele.
    "data de nascimento": "ignorar",
    "data nascimento": "ignorar",
    "nascimento": "ignorar",
    "validade": "ignorar",
    "1a habilitacao": "ignorar",
    "habilitacao": "ignorar",
    "leitura anterior": "ignorar",
}

# Rotulos que aceitam mes/ano sem dia.
TIPOS_COM_MES_ANO = {"referencia", "fechamento"}

_PADRAO_ROTULO = re.compile(
    r"(?<![a-z0-9])("
    + "|".join(re.escape(r) for r in sorted(ROTULOS_POR_TIPO, key=len, reverse=True))
    + r")(?![a-z0-9])"
)

# Distancia maxima, em caracteres, entre o fim do rotulo e o inicio da data.
# Cabe "VENCIMENTO                       12/03/2026" sem alcancar a linha
# seguinte de uma tabela.
ALCANCE_ROTULO = 40

MENSAIS = {"conta_luz", "conta_agua", "conta_gas", "telefone_internet", "fatura_cartao"}

# Por categoria: os tipos de rotulo, na ordem de preferencia.
POLITICAS: dict[str, list[str]] = {
    **{categoria: ["referencia", "leitura", "fechamento", "vencimento", "emissao"] for categoria in MENSAIS},
    "holerite": ["referencia", "pagamento"],
    "nota_fiscal": ["emissao", "documento"],
    "boleto": ["vencimento", "documento"],
    "impostos": ["vencimento", "referencia"],
    "comprovante": ["operacao", "pagamento", "data"],
    "contrato": ["assinatura"],
    "documento_pessoal": ["emissao"],
}
# Para quem nao diz a categoria, e para a data mostrada na tela: a data mais
# "do documento" que estiver escrita nele.
POLITICA_GERAL: list[str] = ["vencimento", "emissao", "assinatura", "referencia", "documento", "data"]

NOMES_DOS_TIPOS = {
    "referencia": "mês de referência",
    "fechamento": "fechamento da fatura",
    "leitura": "leitura atual",
    "vencimento": "vencimento",
    "emissao": "emissão",
    "documento": "data do documento",
    "assinatura": "assinatura",
    "operacao": "data da operação",
    "pagamento": "pagamento",
    "data": "rótulo \"data\"",
}


def _ano_atual() -> int:
    return date.today().year


def _montar(dia: int, mes: int, ano: int) -> date | None:
    """A data, se ela pode existir num documento de hoje.

    Ano de dois digitos vira 20xx so ate o ano que vem; depois disso e do
    seculo passado ("15/08/98" e 1998, nao 2098). Ano antes de 1950 ou depois
    de daqui a dois anos e erro de leitura, e nao data.
    """
    if ano < 100:
        ano += 2000 if ano <= _ano_atual() % 100 + 1 else 1900
    if not 1950 <= ano <= _ano_atual() + 2:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _texto_das_datas(texto: str) -> str:
    """Normalizado linha a linha, com as letras que o OCR pos no lugar de digito."""
    normalizado = "\n".join(normalizar(linha) for linha in texto.splitlines())

    def corrigir(casamento: re.Match) -> str:
        trecho = casamento.group(0)
        # So se ja ha digito o bastante para ser data: "lo/ol/oi" fica como esta.
        if sum(c.isdigit() for c in trecho) < 4:
            return trecho
        return trecho.translate(_CORRECAO_OCR)

    return _PARECE_DATA_DE_OCR.sub(corrigir, normalizado)


@dataclass
class Achado:
    inicio: int
    data: date
    mes_ano: bool = False
    tipo: str | None = None  # tipo do rotulo dono da data
    rotulo: str | None = None
    distancia: int = 0


def _achar_datas(normalizado: str) -> list[Achado]:
    achados = []
    for casamento in PADRAO_NUMERICO.finditer(normalizado):
        dia, mes, ano = casamento.groups()
        if (data := _montar(int(dia), int(mes), int(ano))):
            achados.append(Achado(casamento.start(), data))
    for casamento in PADRAO_ISO.finditer(normalizado):
        ano, mes, dia = casamento.groups()
        if (data := _montar(int(dia), int(mes), int(ano))):
            achados.append(Achado(casamento.start(), data))
    for casamento in PADRAO_EXTENSO.finditer(normalizado):
        dia, mes, ano = casamento.groups()
        if (data := _montar(int(dia), MESES[mes], int(ano))):
            achados.append(Achado(casamento.start(), data))
    for casamento in PADRAO_MES_ANO.finditer(normalizado):
        mes, ano = casamento.groups()
        if 1 <= int(mes) <= 12 and (data := _montar(1, int(mes), int(ano))):
            achados.append(Achado(casamento.start(), data, mes_ano=True))
    for casamento in PADRAO_MES_ANO_NOME.finditer(normalizado):
        nome, ano = casamento.groups()
        mes = MESES.get(nome) or MESES_CURTOS[nome]
        if (data := _montar(1, mes, int(ano))):
            achados.append(Achado(casamento.start(), data, mes_ano=True))
    return sorted(achados, key=lambda achado: achado.inicio)


def _achar_rotulos(normalizado: str) -> list[tuple[int, int, str]]:
    return [(c.start(), c.end(), c.group(1)) for c in _PADRAO_ROTULO.finditer(normalizado)]


def _parear_tabela(normalizado: str, rotulos, achados) -> None:
    """Rotulos numa linha e valores na de baixo: o 3o rotulo fica com a 3a data.

    E como o pypdf devolve muita conta: "LEITURA ANTERIOR  LEITURA ATUAL
    VENCIMENTO" numa linha e as tres datas na seguinte. Medindo so a distancia,
    as tres datas iam para o ultimo rotulo da linha de cima.
    """
    linhas, inicio = [], 0
    for linha in normalizado.split("\n"):
        linhas.append((inicio, inicio + len(linha)))
        inicio += len(linha) + 1
    preenchidas = [faixa for faixa in linhas if faixa[0] != faixa[1]]

    for (cabeca_ini, cabeca_fim), (valor_ini, valor_fim) in zip(preenchidas, preenchidas[1:]):
        da_cabeca = [r for r in rotulos if cabeca_ini <= r[0] < cabeca_fim]
        datas_na_cabeca = [a for a in achados if cabeca_ini <= a.inicio < cabeca_fim]
        datas_da_linha = [a for a in achados if valor_ini <= a.inicio < valor_fim and not a.mes_ano]
        if len(da_cabeca) >= 2 and not datas_na_cabeca and len(da_cabeca) == len(datas_da_linha):
            for (_, _, rotulo), achado in zip(da_cabeca, datas_da_linha):
                achado.tipo, achado.rotulo, achado.distancia = ROTULOS_POR_TIPO[rotulo], rotulo, 0


def _datas_com_dono(texto: str) -> list[Achado]:
    """Cada data com o rotulo que fala por ela (ou nenhum)."""
    normalizado = _texto_das_datas(texto)
    achados = _achar_datas(normalizado)
    rotulos = _achar_rotulos(normalizado)

    for achado in achados:
        anteriores = [r for r in rotulos if r[1] <= achado.inicio and achado.inicio - r[1] <= ALCANCE_ROTULO]
        if anteriores:
            inicio, fim, rotulo = anteriores[-1]
            # Outra data no meio quer dizer que o rotulo ja falou pela dela.
            entre = [a for a in achados if fim <= a.inicio < achado.inicio and not a.mes_ano]
            if not entre:
                achado.tipo, achado.rotulo, achado.distancia = ROTULOS_POR_TIPO[rotulo], rotulo, achado.inicio - fim
    _parear_tabela(normalizado, rotulos, achados)

    # Mes/ano sem dia so vale ao lado de um rotulo de referencia.
    return [a for a in achados if not a.mes_ano or a.tipo in TIPOS_COM_MES_ANO]


def _escolher(texto: str, politica: list[str]) -> tuple[date, str, str] | None:
    """(data, rotulo como estava no texto, explicacao) ou None."""
    achados = _datas_com_dono(texto)
    for tipo in politica:
        candidatos = [a for a in achados if a.tipo == tipo]
        if candidatos:
            melhor = min(candidatos, key=lambda a: a.distancia)
            como = NOMES_DOS_TIPOS[tipo]
            if melhor.mes_ano:
                como = f"{como} {melhor.data:%m/%Y}"
            return melhor.data, melhor.rotulo, como

    soltas = [a for a in achados if a.tipo in (None, "data") and not a.mes_ano]
    if soltas:
        return soltas[0].data, None, "primeira data do texto, sem rótulo"
    return None


def data_do_documento(texto: str, categoria: str | None = None) -> tuple[str | None, str]:
    """A data que decide a PASTA do documento, e como ela foi escolhida.

    Pode ser so mes e ano ("MAR/2026" vira 2026-03-01): serve para a pasta, e
    nao para ser mostrada como se o documento dissesse dia 1.
    """
    escolhida = _escolher(texto, POLITICAS.get(categoria, POLITICA_GERAL))
    if escolhida is None:
        return None, "nenhuma data no texto → pasta sem-data"
    data, rotulo, como = escolhida
    origem = f'{como} (rótulo "{rotulo}")' if rotulo and rotulo not in como else como
    return data.isoformat(), f"{origem} → {data:%m/%Y}"


# ------------------------------------------------------- compatibilidade


def extrair_datas(texto: str) -> list[date]:
    """Todas as datas completas (com dia) do texto, na ordem em que aparecem."""
    return [a.data for a in _achar_datas(_texto_das_datas(texto)) if not a.mes_ano]


def extrair_data_rotulada(texto: str) -> tuple[str, str] | None:
    """A data mais bem rotulada do texto, junto com o rotulo que a indicou.

    E a ordem geral (vencimento, emissao, assinatura...), sem saber o tipo de
    documento; para arquivar, vale `data_do_documento`, que sabe.
    """
    achados = [a for a in _datas_com_dono(texto) if not a.mes_ano]
    for tipo in POLITICA_GERAL:
        candidatos = [a for a in achados if a.tipo == tipo]
        if candidatos:
            melhor = min(candidatos, key=lambda a: a.distancia)
            return melhor.data.isoformat(), melhor.rotulo
    return None


def extrair_data(texto: str, padrao: date | None = None) -> str | None:
    """Data do documento em ISO. Cai no padrao informado quando nao acha nenhuma."""
    rotulada = extrair_data_rotulada(texto)
    if rotulada:
        return rotulada[0]
    datas = extrair_datas(texto)
    if datas:
        return datas[0].isoformat()
    return padrao.isoformat() if padrao else None
