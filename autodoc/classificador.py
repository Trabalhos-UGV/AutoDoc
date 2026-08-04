"""Classificacao de documentos por regras de palavras-chave.

Cada categoria tem um conjunto de termos com peso. O documento recebe a
categoria de maior pontuacao; empates e pontuacao zero caem em "outros".
"""

from __future__ import annotations

import re
import unicodedata

CATEGORIA_PADRAO = "outros"

# categoria -> {termo: peso}
REGRAS: dict[str, dict[str, int]] = {
    "conta_luz": {"kwh": 3, "energia eletrica": 3, "consumo": 1, "distribuidora": 2},
    "conta_agua": {"m3": 2, "agua": 2, "saneamento": 3, "hidrometro": 3},
    "nota_fiscal": {"nota fiscal": 4, "nfe": 3, "cnpj": 1, "danfe": 4, "total": 1},
    "boleto": {"boleto": 4, "codigo de barras": 3, "vencimento": 2, "cedente": 3},
    "contrato": {"contrato": 4, "clausula": 3, "contratante": 3, "partes": 1},
    "comprovante": {"comprovante": 4, "transferencia": 2, "pix": 2, "pagamento": 1},
    "documento_pessoal": {"cpf": 2, "rg": 2, "identidade": 3, "cnh": 3},
}


def normalizar(texto: str) -> str:
    """Minusculas, sem acentos e com espacamento uniforme."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


def pontuar(texto: str) -> dict[str, int]:
    """Pontuacao de cada categoria para o texto informado."""
    normalizado = normalizar(texto)
    placar: dict[str, int] = {}

    for categoria, termos in REGRAS.items():
        total = 0
        for termo, peso in termos.items():
            # \b evita que "agua" case dentro de outra palavra.
            if re.search(rf"\b{re.escape(termo)}\b", normalizado):
                total += peso
        if total:
            placar[categoria] = total

    return placar


def classificar(texto: str) -> str:
    """Retorna a categoria mais provavel do documento."""
    placar = pontuar(texto)
    if not placar:
        return CATEGORIA_PADRAO

    melhor = max(placar.values())
    empatadas = [c for c, p in placar.items() if p == melhor]
    return empatadas[0] if len(empatadas) == 1 else CATEGORIA_PADRAO
