"""Identificacao da data do documento.

Procura datas no texto em formatos comuns no Brasil (dd/mm/aaaa, "12 de marco
de 2026", aaaa-mm-dd) e devolve a primeira encontrada em ISO (aaaa-mm-dd).
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


def extrair_data(texto: str, padrao: date | None = None) -> str | None:
    """Data do documento em ISO. Cai no padrao informado quando nao acha nenhuma."""
    datas = extrair_datas(texto)
    if datas:
        return datas[0].isoformat()
    return padrao.isoformat() if padrao else None


def data_de_modificacao(caminho) -> date:
    """Data de modificacao do arquivo — usada quando o texto nao traz data."""
    return datetime.fromtimestamp(caminho.stat().st_mtime).date()
