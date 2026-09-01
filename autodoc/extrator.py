"""Extracao de texto dos documentos.

Suporta texto puro, PDF (camada de texto), PDF digitalizado e imagens, esses
dois ultimos via OCR. As bibliotecas opcionais (pypdf, pytesseract, Pillow) sao
importadas sob demanda: a ausencia de uma delas so afeta o formato
correspondente.

**PDF digitalizado nao tem camada de texto.** Um PDF que saiu do scanner e uma
imagem embrulhada em PDF: `extract_text()` devolve string vazia e o documento
seria classificado a partir de nada. Quando isso acontece, as imagens embutidas
sao extraidas pelo proprio pypdf e passadas pelo OCR — sem poppler nem
pdf2image, que exigiriam instalar programa externo alem do Tesseract.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
EXTENSOES_TEXTO = {".txt", ".md", ".csv"}

# Teto de paginas passadas pelo OCR. Cada pagina leva alguns segundos, e um PDF
# de duzentas paginas travaria o monitoramento inteiro; as primeiras paginas ja
# trazem cabecalho, emissor e data, que e o que decide a classificacao.
PAGINAS_OCR = 12

# Idioma do OCR. O pacote de portugues pode nao estar instalado ao lado do
# Tesseract, e nesse caso vale mais ler em ingles do que nao ler.
IDIOMA_OCR = "por"


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


def _leitor_pdf(caminho: Path):
    """Abre o PDF, traduzindo qualquer defeito dele para `ExtracaoIndisponivel`.

    O pypdf tem uma familia propria de excecoes (`PdfStreamError` para arquivo
    truncado, por exemplo). Deixa-las escapar cruas derrubaria o observador da
    pasta no primeiro PDF corrompido que alguem largasse ali — e um arquivo
    ruim nao pode parar o programa de vigiar os outros.
    """
    try:
        from pypdf import PdfReader
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise ExtracaoIndisponivel("pypdf nao instalado (pip install pypdf)") from erro

    try:
        return PdfReader(str(caminho))
    except OSError:
        raise
    except Exception as erro:
        raise ExtracaoIndisponivel(f"PDF ilegível: {erro}") from erro


def _extrair_pdf(caminho: Path) -> str:
    """O texto da camada de texto do PDF. Vazio quando o PDF e digitalizado."""
    leitor = _leitor_pdf(caminho)
    paginas = []
    for pagina in leitor.pages:
        try:
            paginas.append(pagina.extract_text() or "")
        except Exception:
            # Uma pagina defeituosa nao invalida as outras.
            continue
    return "\n".join(paginas).strip()


def _motor_ocr():
    """As bibliotecas de OCR, ou uma explicacao do que falta instalar."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise ExtracaoIndisponivel(
            "OCR indisponivel (pip install pytesseract Pillow + Tesseract no sistema)"
        ) from erro
    return pytesseract, Image


def texto_da_imagem(imagem) -> str:
    """Passa uma imagem ja aberta pelo OCR.

    Todo modo de falhar vira `ExtracaoIndisponivel`: o Tesseract ausente levanta
    excecao propria, e ela subindo crua derrubaria o observador da pasta a cada
    imagem largada nela — o programa pararia de vigiar por causa de um arquivo.
    """
    pytesseract, _ = _motor_ocr()
    try:
        return pytesseract.image_to_string(imagem, lang=IDIOMA_OCR).strip()
    except pytesseract.TesseractNotFoundError as erro:
        raise ExtracaoIndisponivel(
            "Tesseract nao esta instalado no sistema — o OCR nao pode rodar"
        ) from erro
    except Exception as erro:
        # Provavel pacote de idioma ausente: tenta o idioma padrao antes de
        # desistir, porque ler em ingles ainda acha "TOTAL", "CNPJ" e as datas.
        try:
            return pytesseract.image_to_string(imagem).strip()
        except Exception:
            raise ExtracaoIndisponivel(f"OCR falhou: {erro}") from erro


def _extrair_imagem(caminho: Path) -> str:
    _, Image = _motor_ocr()
    try:
        abrir = Image.open(caminho)
    except Exception as erro:
        raise ExtracaoIndisponivel(f"imagem ilegível: {erro}") from erro
    with abrir as imagem:
        return texto_da_imagem(imagem)


def _ocr_de_pdf(caminho: Path) -> str:
    """OCR das imagens embutidas num PDF sem camada de texto.

    Num PDF de scanner cada pagina e uma imagem so, entao extrair as imagens
    embutidas equivale a rasterizar as paginas — sem depender de poppler.
    """
    leitor = _leitor_pdf(caminho)
    partes: list[str] = []

    for pagina in leitor.pages[:PAGINAS_OCR]:
        try:
            imagens = list(pagina.images)
        except Exception:  # PDF com objeto de imagem que o pypdf nao decodifica
            continue
        for embutida in imagens:
            partes.append(texto_da_imagem(embutida.image))

    return "\n".join(parte for parte in partes if parte).strip()


def extrair_com_origem(caminho: Path) -> tuple[str, str]:
    """Texto do documento e uma descricao de como ele foi obtido.

    A origem vai para a tela: saber que um documento veio de OCR e nao da
    camada de texto de um PDF muda o quanto se confia no que foi lido.
    """
    extensao = caminho.suffix.lower()

    if extensao in EXTENSOES_TEXTO:
        return _extrair_texto_simples(caminho), "arquivo de texto"

    if extensao == ".pdf":
        texto = _extrair_pdf(caminho)
        if texto:
            return texto, "PDF com texto embutido"

        # PDF escaneado nao tem camada de texto — o OCR entra como fallback.
        texto = _ocr_de_pdf(caminho)
        if texto:
            return texto, "PDF digitalizado — OCR"
        return "", "PDF sem camada de texto e sem imagem legível"

    if extensao in EXTENSOES_IMAGEM:
        return _extrair_imagem(caminho), "imagem — OCR"

    raise ExtracaoIndisponivel(f"formato nao suportado: {extensao}")


def extrair_texto(caminho: Path) -> str:
    """Retorna o texto do documento conforme a extensao do arquivo."""
    return extrair_com_origem(caminho)[0]
