"""Identificacao da data do documento.

Procura datas nos formatos comuns no Brasil (dd/mm/aaaa, "12 de marco de 2026",
aaaa-mm-dd) e devolve uma em ISO (aaaa-mm-dd).

Pegar a primeira data do texto nao serve: uma conta de luz comeca com a leitura
anterior, que e do mes passado, e arquivaria a conta no mes errado. Documentos
rotulam a data que importa — "VENCIMENTO", "Data de emissao" —, entao a data
proxima de um rotulo conhecido ganha da que so aparece solta.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from .classificador import normalizar

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

PADRAO_NUMERICO = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
PADRAO_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
PADRAO_EXTENSO = re.compile(
    rf"\b(\d{{1,2}})\s+de\s+({'|'.join(MESES)})\s+de\s+(\d{{4}})\b"
)


# Rotulo -> prioridade. Quanto maior, mais o rotulo indica "a data do
# documento". Vencimento ganha de emissao porque e por ele que se procura a
# conta depois; ambos ganham de um "data:" solto.
ROTULOS: dict[str, int] = {
    "vencimento": 3,
    "data de emissao": 2,
    "data de assinatura": 2,
    "emissao": 2,
    "competencia": 2,
    "data": 1,
}

# Distancia maxima, em caracteres, entre o fim do rotulo e o inicio da data.
# Cabe "VENCIMENTO                       12/03/2026" sem alcancar a linha
# seguinte de uma tabela.
ALCANCE_ROTULO = 40


def _montar(dia: int, mes: int, ano: int) -> date | None:
    if ano < 100:  # ano com dois digitos: 26 -> 2026
        ano += 2000
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def extrair_datas(texto: str) -> list[date]:
    """Todas as datas validas encontradas no texto, na ordem em que aparecem."""
    normalizado = normalizar(texto)
    encontradas: list[date] = []

    for dia, mes, ano in PADRAO_NUMERICO.findall(normalizado):
        data = _montar(int(dia), int(mes), int(ano))
        if data:
            encontradas.append(data)

    for ano, mes, dia in PADRAO_ISO.findall(normalizado):
        data = _montar(int(dia), int(mes), int(ano))
        if data:
            encontradas.append(data)

    for dia, mes, ano in PADRAO_EXTENSO.findall(normalizado):
        data = _montar(int(dia), MESES[mes], int(ano))
        if data:
            encontradas.append(data)

    return encontradas


def _datas_com_posicao(normalizado: str) -> list[tuple[int, date]]:
    """Todas as datas do texto normalizado, com onde cada uma comeca."""
    achadas: list[tuple[int, date]] = []

    for casamento in PADRAO_NUMERICO.finditer(normalizado):
        dia, mes, ano = casamento.groups()
        data = _montar(int(dia), int(mes), int(ano))
        if data:
            achadas.append((casamento.start(), data))

    for casamento in PADRAO_ISO.finditer(normalizado):
        ano, mes, dia = casamento.groups()
        data = _montar(int(dia), int(mes), int(ano))
        if data:
            achadas.append((casamento.start(), data))

    for casamento in PADRAO_EXTENSO.finditer(normalizado):
        dia, mes, ano = casamento.groups()
        data = _montar(int(dia), MESES[mes], int(ano))
        if data:
            achadas.append((casamento.start(), data))

    return sorted(achadas)


def extrair_data_rotulada(texto: str) -> tuple[str, str] | None:
    """A data mais bem rotulada do texto, junto com o rotulo que a indicou.

    Devolve (data ISO, rotulo) ou None quando nenhuma data esta perto de um
    rotulo conhecido.
    """
    normalizado = normalizar(texto)
    datas = _datas_com_posicao(normalizado)
    if not datas:
        return None

    melhor: tuple[int, int, date, str] | None = None

    for rotulo, prioridade in ROTULOS.items():
        for casamento in re.finditer(rf"\b{re.escape(rotulo)}\b", normalizado):
            fim = casamento.end()
            for posicao, data in datas:
                distancia = posicao - fim
                if 0 <= distancia <= ALCANCE_ROTULO:
                    # Prioridade alta primeiro; empatou, vence a data mais
                    # colada no rotulo.
                    candidato = (-prioridade, distancia, data, rotulo)
                    if melhor is None or candidato[:2] < melhor[:2]:
                        melhor = candidato
                    break

    if melhor is None:
        return None
    return melhor[2].isoformat(), melhor[3]


def extrair_data(texto: str, padrao: date | None = None) -> str | None:
    """Data do documento em ISO. Cai no padrao informado quando nao acha nenhuma."""
    rotulada = extrair_data_rotulada(texto)
    if rotulada:
        return rotulada[0]

    datas = extrair_datas(texto)
    if datas:
        return datas[0].isoformat()
    return padrao.isoformat() if padrao else None


def data_de_modificacao(caminho) -> date:
    """Data de modificacao do arquivo — usada quando o texto nao traz data."""
    return datetime.fromtimestamp(caminho.stat().st_mtime).date()
