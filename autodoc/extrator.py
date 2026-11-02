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
import os
import re
import shutil
import sys
from pathlib import Path

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif"}
EXTENSOES_TEXTO = {".txt", ".md", ".csv"}
EXTENSOES_SUPORTADAS = EXTENSOES_TEXTO | EXTENSOES_IMAGEM | {".pdf"}

# Foto do iPhone. O Pillow so a abre com o plugin do pillow-heif registrado.
EXTENSOES_HEIF = {".heic", ".heif"}

# Teto de paginas passadas pelo OCR. Cada pagina leva alguns segundos, e um PDF
# de duzentas paginas travaria o monitoramento inteiro; as primeiras paginas ja
# trazem cabecalho, emissor e data, que e o que decide a classificacao.
PAGINAS_OCR = 12

# Idioma do OCR. O pacote de portugues pode nao estar instalado ao lado do
# Tesseract, e nesse caso vale mais ler em ingles do que nao ler.
IDIOMA_OCR = "por"

# Pagina com menos texto do que isto e tratada como digitalizada. PDF de
# scanner as vezes traz em texto so o numero da pagina ou um carimbo — e antes
# isso bastava para o OCR nunca rodar, e o documento ia para a revisao vazio.
MINIMO_TEXTO_PAGINA = 40

# Lado menor, em pixels, abaixo do qual a imagem e ampliada antes do OCR. O
# Tesseract foi treinado com texto de uns 300 DPI; foto de celular reduzida e
# miniatura de scanner leem lixo abaixo disso.
LADO_MINIMO_OCR = 1200
AMPLIACAO_MAXIMA = 4


# O instalador do Tesseract no Windows nao o poe no PATH: sem procurar aqui, o
# OCR ficava desligado numa maquina em que ele esta instalado.
PASTAS_TESSERACT_WINDOWS = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR",
    Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
    / "Programs" / "Tesseract-OCR",
)

COMO_INSTALAR_OCR = {
    "darwin": "brew install tesseract tesseract-lang",
    "win": "instale o Tesseract (UB Mannheim) marcando o idioma Portuguese",
    "linux": "sudo apt install tesseract-ocr tesseract-ocr-por",
}


class ExtracaoIndisponivel(RuntimeError):
    """A dependencia necessaria para ler este formato nao esta instalada."""


class OcrIndisponivel(ExtracaoIndisponivel):
    """Falta o motor de OCR — o arquivo nao tem nada de errado.

    A diferenca importa: um arquivo ruim vai para a revisao, mas uma foto boa
    numa maquina sem Tesseract so precisa esperar o OCR ser instalado.
    """


def hash_arquivo(caminho: Path) -> str:
    """SHA-256 do conteudo, usado para nao reprocessar o mesmo documento."""
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _extrair_texto_simples(caminho: Path) -> str:
    """Texto de .txt/.csv/.md, na codificacao em que ele foi salvo.

    O Excel e o Bloco de Notas do Windows salvam em UTF-16 com BOM: lido como
    UTF-8, um CSV desses vira "D e s i g n a t o r" e nenhuma regra casa. E o
    que nao e UTF-8 valido costuma ser cp1252 — ignorar os bytes ruins, como
    antes, apagava todo "ã" e "ç" do texto sem avisar.
    """
    dados = caminho.read_bytes()
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return dados.decode("utf-16", errors="replace")
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


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


def _motor_ocr():
    """As bibliotecas de OCR, ou uma explicacao do que falta instalar."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise OcrIndisponivel(
            "OCR indisponivel (pip install pytesseract Pillow + Tesseract no sistema)"
        ) from erro
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass  # sem ele, so a foto HEIC deixa de abrir
    _achar_tesseract_no_windows(pytesseract)
    return pytesseract, Image


def sobre_a_imagem(caminho: Path) -> tuple[tuple[int, int] | None, str | None]:
    """Tamanho em pixels e data de captura (EXIF, "AAAA-MM-DD") da imagem.

    Serve para dizer o que e uma imagem sem texto de documento — um icone de
    64x64 nao e uma foto de 4000x3000. Qualquer falha devolve None: e so a
    descricao que fica mais pobre.
    """
    try:
        from PIL import Image
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        with Image.open(caminho) as imagem:
            tamanho = imagem.size
            exif = imagem.getexif()
            # DateTimeOriginal mora no bloco Exif; DateTime, no principal.
            capturada = exif.get_ifd(0x8769).get(36867) or exif.get(306)
    except Exception:
        return None, None

    data = None
    if isinstance(capturada, str) and re.match(r"\d{4}:\d{2}:\d{2}", capturada):
        ano, mes, dia = capturada[:10].split(":")
        if ano != "0000":
            data = f"{ano}-{mes}-{dia}"
    return tamanho, data


def tessdata_do_usuario() -> Path:
    """Onde o `instalar.py` poe o portugues do Tesseract no Windows."""
    local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(local) / "AutoDoc" / "tessdata"


def caminho_do_tesseract() -> str | None:
    """O executavel do Tesseract: no PATH ou, no Windows, onde o instalador o deixa."""
    if shutil.which("tesseract"):
        return shutil.which("tesseract")
    if sys.platform.startswith("win"):
        for pasta in PASTAS_TESSERACT_WINDOWS:
            if (pasta / "tesseract.exe").is_file():
                return str(pasta / "tesseract.exe")
    return None


def _achar_tesseract_no_windows(pytesseract) -> None:
    if not sys.platform.startswith("win"):
        return
    # O pacote do winget so traz o ingles; o portugues fica numa pasta da
    # pessoa, que nao pede administrador para ser escrita.
    if (tessdata_do_usuario() / "por.traineddata").is_file():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata_do_usuario()))
    caminho = caminho_do_tesseract()
    if caminho and not shutil.which("tesseract"):
        pytesseract.pytesseract.tesseract_cmd = caminho


def como_instalar_ocr() -> str:
    """O comando que poe o OCR em portugues neste sistema."""
    for prefixo, comando in COMO_INSTALAR_OCR.items():
        if sys.platform.startswith(prefixo):
            return comando
    return COMO_INSTALAR_OCR["linux"]


def diagnostico_ocr() -> dict:
    """O OCR desta maquina: existe, le portugues e, se nao, como resolver.

    Antes a falta do Tesseract so aparecia como foto atras de foto indo para a
    revisao, e a falta do pacote de portugues nao aparecia em lugar nenhum — o
    OCR lia em ingles calado, perdendo "ç" e "ã" de "Prestação" e "Emissão".
    """
    try:
        pytesseract, _ = _motor_ocr()
        idiomas = set(pytesseract.get_languages(config=""))
    except Exception:  # OcrIndisponivel, ou o Tesseract que nao responde
        return {
            "disponivel": False,
            "portugues": False,
            "resumo": "não instalado — fotos e scans esperam o OCR",
            "como_instalar": como_instalar_ocr(),
        }
    if IDIOMA_OCR not in idiomas:
        return {
            "disponivel": True,
            "portugues": False,
            "resumo": "sem o pacote de português — lendo em inglês",
            "como_instalar": como_instalar_ocr(),
        }
    return {"disponivel": True, "portugues": True, "resumo": "pronto, em português",
            "como_instalar": ""}


def preparar_para_ocr(imagem):
    """Endireita, tira a cor e amplia a imagem antes do OCR.

    - **Rotacao pelo EXIF.** A camera do celular grava a foto de lado e anota
      no EXIF que ela deve ser girada. O Tesseract nao le o EXIF: recebia a
      conta deitada e devolvia lixo.
    - **Tons de cinza.** Cor nao ajuda a ler letra e atrapalha a binarizacao
      interna do Tesseract em papel amarelado.
    - **Ampliacao.** Ver `LADO_MINIMO_OCR`.
    """
    from PIL import Image, ImageOps

    imagem = ImageOps.exif_transpose(imagem)
    if imagem.mode == "P" and "transparency" in imagem.info:
        # Direto de paleta para cinza o Pillow avisa a cada imagem — um aviso
        # por icone, centenas no terminal de quem largou uma pasta de PNGs.
        imagem = imagem.convert("RGBA")
    imagem = imagem.convert("L")
    menor = min(imagem.size)
    if 0 < menor < LADO_MINIMO_OCR:
        fator = min(LADO_MINIMO_OCR / menor, AMPLIACAO_MAXIMA)
        largura, altura = imagem.size
        imagem = imagem.resize((round(largura * fator), round(altura * fator)),
                               Image.Resampling.LANCZOS)
    return imagem


def texto_da_imagem(imagem) -> str:
    """Passa uma imagem ja aberta pelo OCR.

    Todo modo de falhar vira `ExtracaoIndisponivel`: o Tesseract ausente levanta
    excecao propria, e ela subindo crua derrubaria o observador da pasta a cada
    imagem largada nela — o programa pararia de vigiar por causa de um arquivo.
    """
    pytesseract, _ = _motor_ocr()
    imagem = preparar_para_ocr(imagem)
    try:
        return pytesseract.image_to_string(imagem, lang=IDIOMA_OCR).strip()
    except pytesseract.TesseractNotFoundError as erro:
        raise OcrIndisponivel(
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
        if caminho.suffix.lower() in EXTENSOES_HEIF:
            raise ExtracaoIndisponivel(
                f"foto HEIC ilegível — confira o pillow-heif (pip install pillow-heif): {erro}"
            ) from erro
        raise ExtracaoIndisponivel(f"imagem ilegível: {erro}") from erro
    with abrir as imagem:
        return texto_da_imagem(imagem)


def _texto_da_pagina(pagina) -> str:
    try:
        return (pagina.extract_text() or "").strip()
    except Exception:
        # Uma pagina defeituosa nao invalida as outras.
        return ""


def _ocr_da_pagina(pagina) -> str:
    """OCR das imagens embutidas numa pagina.

    Numa pagina de scanner ha uma imagem so, entao extrair as imagens embutidas
    equivale a rasterizar a pagina — sem depender de poppler. Uma imagem que o
    OCR nao consegue ler e pulada; a falta do proprio OCR sobe.
    """
    try:
        imagens = list(pagina.images)
    except Exception:  # PDF com objeto de imagem que o pypdf nao decodifica
        return ""

    partes = []
    for embutida in imagens:
        try:
            partes.append(texto_da_imagem(embutida.image))
        except OcrIndisponivel:
            raise
        except ExtracaoIndisponivel:
            continue
    return "\n".join(parte for parte in partes if parte)


def _extrair_pdf(caminho: Path) -> tuple[str, str]:
    """Texto de cada pagina, pela camada de texto ou, sem ela, pelo OCR.

    A decisao e por pagina, e nao pelo PDF inteiro: um contrato digitado com a
    pagina assinada escaneada no fim, ou um scan com o numero da pagina em
    texto, tinham o OCR pulado porque *alguma* pagina trazia texto.
    """
    leitor = _leitor_pdf(caminho)
    partes: list[str] = []
    pela_camada = pelo_ocr = 0
    falta_ocr: OcrIndisponivel | None = None

    for indice, pagina in enumerate(leitor.pages):
        texto = _texto_da_pagina(pagina)
        if len(texto) >= MINIMO_TEXTO_PAGINA:
            pela_camada += 1
        elif indice < PAGINAS_OCR and falta_ocr is None:
            try:
                lido = _ocr_da_pagina(pagina)
            except OcrIndisponivel as erro:
                falta_ocr, lido = erro, ""
            if lido:
                pelo_ocr += 1
                texto = f"{texto}\n{lido}".strip()
        if texto:
            partes.append(texto)

    texto = "\n".join(partes)
    if not texto:
        if falta_ocr:
            raise falta_ocr
        return "", "PDF sem camada de texto e sem imagem legível"
    if not pelo_ocr:
        if falta_ocr:
            return texto, "PDF com texto embutido — páginas digitalizadas sem OCR"
        return texto, "PDF com texto embutido"
    if not pela_camada:
        return texto, "PDF digitalizado — OCR"
    return texto, f"PDF com texto embutido + OCR em {pelo_ocr} página(s)"


def extrair_com_origem(caminho: Path) -> tuple[str, str]:
    """Texto do documento e uma descricao de como ele foi obtido.

    A origem vai para a tela: saber que um documento veio de OCR e nao da
    camada de texto de um PDF muda o quanto se confia no que foi lido.
    """
    extensao = caminho.suffix.lower()

    if extensao in EXTENSOES_TEXTO:
        return _extrair_texto_simples(caminho), "arquivo de texto"

    if extensao == ".pdf":
        return _extrair_pdf(caminho)

    if extensao in EXTENSOES_IMAGEM:
        return _extrair_imagem(caminho), "imagem — OCR"

    raise ExtracaoIndisponivel(f"formato nao suportado: {extensao}")


def extrair_texto(caminho: Path) -> str:
    """Retorna o texto do documento conforme a extensao do arquivo."""
    return extrair_com_origem(caminho)[0]
