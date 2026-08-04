"""Extracao de texto dos documentos.

Suporta texto puro, PDF (camada de texto) e imagens via OCR. As bibliotecas
opcionais (pypdf, pytesseract, Pillow) sao importadas sob demanda: a ausencia
de uma delas so afeta o formato correspondente.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
EXTENSOES_TEXTO = {".txt", ".md", ".csv"}


class ExtracaoIndisponivel(RuntimeError):
    """A dependencia necessaria para ler este formato nao esta instalada."""


def hash_arquivo(caminho: Path) -> str:
    """SHA-256 do conteudo, usado para nao reprocessar o mesmo documento."""
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _extrair_texto_simples(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="ignore")


def _extrair_pdf(caminho: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise ExtracaoIndisponivel("pypdf nao instalado (pip install pypdf)") from erro

    leitor = PdfReader(str(caminho))
    paginas = [pagina.extract_text() or "" for pagina in leitor.pages]
    return "\n".join(paginas).strip()


def _extrair_imagem(caminho: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise ExtracaoIndisponivel(
            "OCR indisponivel (pip install pytesseract Pillow + Tesseract no sistema)"
        ) from erro

    with Image.open(caminho) as imagem:
        return pytesseract.image_to_string(imagem, lang="por").strip()


def extrair_texto(caminho: Path) -> str:
    """Retorna o texto do documento conforme a extensao do arquivo."""
    extensao = caminho.suffix.lower()

    if extensao in EXTENSOES_TEXTO:
        return _extrair_texto_simples(caminho)
    if extensao == ".pdf":
        texto = _extrair_pdf(caminho)
        # PDF escaneado nao tem camada de texto — o OCR entra como fallback.
        return texto if texto else ""
    if extensao in EXTENSOES_IMAGEM:
        return _extrair_imagem(caminho)

    raise ExtracaoIndisponivel(f"formato nao suportado: {extensao}")
