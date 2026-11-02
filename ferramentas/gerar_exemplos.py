"""Gera os documentos de exemplo em exemplos/: PDF, scan, foto de celular.

Nao roda em producao. Existe para reproduzir os arquivos versionados — quem
mudar um texto aqui roda o script de novo e commita o que saiu.

Todos os dados sao ficticios: pessoas, empresas, CPFs e enderecos nao existem.
Nenhuma marca real aparece; as contas sao reconhecidas pelo que dizem
("kWh", "bandeira tarifaria", "hidrometro"), que e o que o AutoDoc deve saber
fazer com uma empresa que ele nunca viu.

Os formatos cobrem o que chega de verdade numa pasta de documentos:

- PDF com texto (gerado aqui mesmo, sem biblioteca: o formato e simples);
- PDF escaneado (so imagem, precisa de OCR);
- PDF misto (paginas digitadas + pagina assinada escaneada);
- foto de celular torta, sobre a mesa, e foto gravada "deitada" com a
  orientacao no EXIF;
- print de tela;
- e o que nao e documento: foto, icone, uma pasta de projeto e um .zip.

Uso:
    python ferramentas/gerar_exemplos.py
Precisa do Pillow e de uma fonte TrueType (Arial no macOS e no Windows,
DejaVu/Liberation no Linux).
"""

from __future__ import annotations

import io
import random
import sys
import zipfile
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "exemplos"

RODAPE = "Documento fictício gerado para demonstração do AutoDoc — sem valor legal."

FONTES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def fonte(tamanho: int, negrito: bool = False) -> ImageFont.FreeTypeFont:
    candidatas = [f for f in FONTES if ("Bold" in f or "bd" in f) == negrito]
    for caminho in candidatas:
        if Path(caminho).exists():
            return ImageFont.truetype(caminho, tamanho)
    sys.exit("nenhuma fonte TrueType encontrada (ver FONTES)")


# --------------------------------------------------------------------- PDF
#
# Cada pagina e uma lista de linhas: (texto, tamanho, negrito). O PDF usa as
# fontes padrao Helvetica com WinAnsiEncoding — o pypdf extrai o texto delas
# com acento, que e exatamente o caso do PDF de conta baixado do site.

Linha = tuple[str, int, bool]


def _escapar(texto: str) -> bytes:
    bruto = texto.encode("cp1252")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _conteudo_texto(linhas: list[Linha]) -> bytes:
    partes = [b"0.15 0.15 0.15 RG 0.8 w 50 790 m 545 790 l S"]
    y = 770
    for texto, tamanho, negrito in linhas:
        if texto == "---":
            partes.append(f"0.6 G 0.5 w 50 {y + 4} m 545 {y + 4} l S".encode())
            y -= 10
            continue
        fonte_pdf = b"/F2" if negrito else b"/F1"
        partes.append(b"BT " + fonte_pdf + f" {tamanho} Tf 50 {y} Td (".encode()
                      + _escapar(texto) + b") Tj ET")
        y -= tamanho + 6
    partes.append(b"BT /F1 7 Tf 50 40 Td (" + _escapar(RODAPE) + b") Tj ET")
    return b"\n".join(partes)


def pdf(caminho: Path, paginas: list) -> None:
    """Cada pagina: lista de Linhas (texto) ou uma Image (pagina escaneada)."""
    objetos: list[bytes] = []

    def novo(corpo: bytes) -> int:
        objetos.append(corpo)
        return len(objetos)

    fonte_normal = novo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    fonte_negrito = novo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    raiz_paginas = novo(b"")  # preenchido no fim
    filhas = []
    for pagina in paginas:
        if isinstance(pagina, Image.Image):
            jpeg = io.BytesIO()
            pagina.convert("RGB").save(jpeg, "JPEG", quality=80)
            largura, altura = pagina.size
            imagem = novo(
                f"<< /Type /XObject /Subtype /Image /Width {largura} /Height {altura} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(jpeg.getvalue())} >>\nstream\n".encode()
                + jpeg.getvalue() + b"\nendstream")
            desenho = b"q 595 0 0 842 0 0 cm /Im1 Do Q"
            recursos = f"<< /XObject << /Im1 {imagem} 0 R >> >>".encode()
        else:
            desenho = zlib.compress(_conteudo_texto(pagina))
            recursos = f"<< /Font << /F1 {fonte_normal} 0 R /F2 {fonte_negrito} 0 R >> >>".encode()
        filtro = b"" if isinstance(pagina, Image.Image) else b" /Filter /FlateDecode"
        conteudo = novo(f"<< /Length {len(desenho)}".encode() + filtro + b" >>\nstream\n"
                        + desenho + b"\nendstream")
        filhas.append(novo(
            f"<< /Type /Page /Parent {raiz_paginas} 0 R /MediaBox [0 0 595 842] "
            f"/Contents {conteudo} 0 R /Resources ".encode() + recursos + b" >>"))
    objetos[raiz_paginas - 1] = (
        f"<< /Type /Pages /Count {len(filhas)} /Kids [".encode()
        + b" ".join(f"{f} 0 R".encode() for f in filhas) + b"] >>")
    catalogo = novo(f"<< /Type /Catalog /Pages {raiz_paginas} 0 R >>".encode())

    saida = io.BytesIO()
    saida.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posicoes = []
    for numero, corpo in enumerate(objetos, 1):
        posicoes.append(saida.tell())
        saida.write(f"{numero} 0 obj\n".encode() + corpo + b"\nendobj\n")
    inicio_xref = saida.tell()
    saida.write(f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode())
    for posicao in posicoes:
        saida.write(f"{posicao:010d} 00000 n \n".encode())
    saida.write(f"trailer\n<< /Size {len(objetos) + 1} /Root {catalogo} 0 R >>\n"
                f"startxref\n{inicio_xref}\n%%EOF\n".encode())
    caminho.write_bytes(saida.getvalue())


# ------------------------------------------------------------------ imagem

def folha(linhas: list[Linha], largura: int = 1240, altura: int = 1754, margem: int = 90) -> Image.Image:
    """Uma folha A4 a ~150 dpi com o texto, como sai da impressora."""
    imagem = Image.new("RGB", (largura, altura), "white")
    desenho = ImageDraw.Draw(imagem)
    desenho.line((margem, margem - 20, largura - margem, margem - 20), fill=(40, 40, 40), width=3)
    y = margem
    for texto, tamanho, negrito in linhas:
        if texto == "---":
            desenho.line((margem, y + 6, largura - margem, y + 6), fill=(150, 150, 150), width=2)
            y += 24
            continue
        escala = tamanho * 2.1
        desenho.text((margem, y), texto, font=fonte(int(escala), negrito), fill=(25, 25, 25))
        y += int(escala * 1.45)
    desenho.text((margem, altura - margem), RODAPE, font=fonte(18), fill=(90, 90, 90))
    return imagem


def escanear(imagem: Image.Image, semente: int) -> Image.Image:
    """Papel levemente acinzentado, um grau torto e o grao do scanner."""
    aleatorio = random.Random(semente)
    papel = Image.new("RGB", imagem.size, (238, 236, 230))
    papel = Image.blend(papel, imagem, 0.88)
    papel = papel.rotate(aleatorio.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC,
                         fillcolor=(238, 236, 230))
    ruido = Image.effect_noise(imagem.size, 18).convert("RGB")
    papel = Image.blend(papel, ruido, 0.06)
    return papel.filter(ImageFilter.GaussianBlur(0.6))


def foto_de_celular(imagem: Image.Image, semente: int, angulo: float) -> Image.Image:
    """A folha fotografada sobre a mesa: torta, com sombra e luz desigual."""
    aleatorio = random.Random(semente)
    folha_menor = imagem.resize((imagem.width * 3 // 4, imagem.height * 3 // 4), Image.Resampling.LANCZOS)
    mesa = Image.new("RGB", (int(folha_menor.width * 1.35), int(folha_menor.height * 1.25)), (92, 70, 52))
    sombra = Image.new("RGBA", folha_menor.size, (0, 0, 0, 110))
    girada = folha_menor.convert("RGBA").rotate(angulo, expand=True, resample=Image.Resampling.BICUBIC)
    sombra = sombra.rotate(angulo, expand=True).filter(ImageFilter.GaussianBlur(12))
    x = (mesa.width - girada.width) // 2
    y = (mesa.height - girada.height) // 2
    mesa.paste(sombra, (x + 14, y + 18), sombra)
    mesa.paste(girada, (x, y), girada)
    luz = Image.linear_gradient("L").resize(mesa.size).rotate(aleatorio.uniform(20, 60))
    escura = Image.new("RGB", mesa.size, (0, 0, 0))
    return Image.composite(mesa, escura, luz.point(lambda v: 170 + v * 85 // 255))


def salvar_jpeg_com_exif(imagem: Image.Image, caminho: Path, capturada: str,
                         orientacao: int | None = None) -> None:
    exif = Image.Exif()
    exif[0x010F] = "Celular Exemplo"          # Make
    exif[0x0110] = "Camera de demonstracao"   # Model
    exif[0x0132] = capturada                  # DateTime
    exif.get_ifd(0x8769)[0x9003] = capturada  # DateTimeOriginal
    if orientacao:
        exif[0x0112] = orientacao
    imagem.save(caminho, "JPEG", quality=85, exif=exif)


# ---------------------------------------------------------------- conteudo

def t(texto: str, tamanho: int = 11, negrito: bool = False) -> Linha:
    return (texto, tamanho, negrito)


CONTA_LUZ = [
    t("COMPANHIA DE ENERGIA DO VALE S.A.", 15, True),
    t("CNPJ 00.111.222/0001-33  -  Distribuidora de energia elétrica"),
    t("NOTA FISCAL / CONTA DE ENERGIA ELÉTRICA N. 004.512.337", 12, True),
    t("---"),
    t("Cliente: MARIA EXEMPLO DA SILVA       Unidade consumidora: 1029384756"),
    t("Endereço: Rua das Amostras, 100 - Apto 12 - Curitiba/PR"),
    t("Mês de referência: MAR/2026            Data de emissão: 18/03/2026"),
    t("---"),
    t("Leitura anterior: 13/02/2026     Leitura atual: 14/03/2026     Dias: 29"),
    t("Consumo faturado: 214 kWh        Bandeira tarifária: VERDE"),
    t("Energia elétrica ............................. R$ 162,40"),
    t("Contribuição de iluminação pública ............ R$ 18,90"),
    t("ICMS 18% ....................................... R$ 25,85"),
    t("---"),
    t("VENCIMENTO: 10/04/2026            TOTAL A PAGAR: R$ 207,15", 13, True),
    t("Código de barras: 83650000002-0 07150162026-1 04100000000-0 10293847566-1"),
]

CONTA_AGUA = [
    t("SERVIÇO MUNICIPAL DE ÁGUA E SANEAMENTO", 15, True),
    t("Conta de água e esgoto  -  Fatura n. 77.120.044"),
    t("---"),
    t("Cliente: JOÃO MODELO PEREIRA"),
    t("Matrícula: 4455-6     Hidrômetro: Y22B013377"),
    t("Referencia: FEV/2026"),
    t("Leitura anterior: 22/01/2026   Leitura atual: 21/02/2026"),
    t("Consumo de água: 14 metros cúbicos (m3)"),
    t("Agua ............................. R$ 61,30"),
    t("Esgoto ........................... R$ 49,04"),
    t("---"),
    t("Vencimento: 09/03/2026      Total a pagar: R$ 110,34", 13, True),
]

CONTA_GAS = [
    t("GÁS ENCANADO DO SUL LTDA.", 15, True),
    t("Fornecimento de gás natural canalizado"),
    t("---"),
    t("Cliente: MARIA EXEMPLO DA SILVA     Código do cliente: 556677"),
    t("Referencia: JAN/2026"),
    t("Leitura anterior: 05/12/2025     Leitura atual: 06/01/2026"),
    t("Consumo: 9 m3 de gás natural"),
    t("Valor do gás ...................... R$ 74,10"),
    t("---"),
    t("Vencimento: 25/01/2026        Total a pagar: R$ 74,10", 13, True),
]

INTERNET = [
    t("CONECTA TELECOMUNICAÇÕES S.A.", 15, True),
    t("Serviço de telecomunicações - Banda larga fibra 500 Mega"),
    t("---"),
    t("Assinante: MARIA EXEMPLO DA SILVA     Contrato: 9988776655"),
    t("Mês de referência: MAR/2026     Período: 01/03/2026 a 31/03/2026"),
    t("Plano Fibra 500 Mega ........................ R$ 99,90"),
    t("Telefone fixo ilimitado ...................... R$ 19,90"),
    t("---"),
    t("Vencimento: 15/04/2026        Total: R$ 119,80", 13, True),
]

BOLETO = [
    t("COLEGIO EXEMPLO DE ENSINO LTDA.", 15, True),
    t("Mensalidade escolar - Abril/2026"),
    t("---"),
    t("Beneficiário: Colegio Exemplo de Ensino Ltda   CNPJ 00.333.444/0001-55"),
    t("Pagador: JOÃO MODELO PEREIRA   CPF 000.000.000-00"),
    t("Nosso número: 000123456-7      Agencia/Código do beneficiário: 0001/12345-6"),
    t("Local de pagamento: pagável em qualquer banco até o vencimento"),
    t("Data do documento: 25/03/2026"),
    t("---"),
    t("Vencimento: 10/04/2026         Valor do documento: R$ 890,00", 13, True),
    t("Linha digitável: 00190.00009 01234.567890 12345.678901 1 10100000089000"),
    t("Ficha de compensação", 9),
]

FATURA_CARTAO = [
    t("BANCO EXEMPLO S.A. - CARTÃO DE CRÉDITO", 15, True),
    t("Fatura do cartão  -  Final 4321"),
    t("---"),
    t("Titular: MARIA EXEMPLO DA SILVA"),
    t("Mês de referência: MAR/2026     Fechamento: 03/03/2026"),
    t("Limite total: R$ 5.000,00       Limite disponível: R$ 3.420,55"),
    t("05/02  Mercado Exemplo ............... R$ 312,40"),
    t("12/02  Farmácia Modelo ............... R$ 48,90"),
    t("20/02  Posto Amostra ................. R$ 218,15"),
    t("---"),
    t("Total da fatura: R$ 1.579,45     Pagamento mínimo: R$ 236,92", 13, True),
    t("Vencimento: 10/03/2026"),
]

IPTU = [
    t("PREFEITURA MUNICIPAL DE CIDADE EXEMPLO", 15, True),
    t("Secretaria Municipal de Finanças - IPTU 2026"),
    t("Imposto predial e territorial urbano"),
    t("---"),
    t("Contribuinte: JOÃO MODELO PEREIRA"),
    t("Inscrição imobiliária: 01.023.0456.0789"),
    t("Endereço do imóvel: Rua das Amostras, 100"),
    t("Valor venal: R$ 280.000,00"),
    t("---"),
    t("Cota única - Vencimento: 10/02/2026     Valor: R$ 1.120,00", 13, True),
    t("Linha digitável: 81690000011-2 20000123456-7 89010202026-0 01234567890-1"),
]

HOLERITE = [
    t("EMPRESA MODELO DE SOFTWARE LTDA", 15, True),
    t("Recibo de pagamento de salário  -  Holerite"),
    t("---"),
    t("Funcionário: MARIA EXEMPLO DA SILVA     Cargo: Analista de sistemas"),
    t("Competência: 03/2026"),
    t("Salário base ..................................... R$ 4.500,00"),
    t("INSS ............................................. R$ 418,94"),
    t("IRRF ............................................. R$ 236,81"),
    t("FGTS do mes ...................................... R$ 360,00"),
    t("---"),
    t("Líquido a receber: R$ 3.844,25", 13, True),
    t("Data de pagamento: 05/04/2026"),
]

RG = [
    t("REPÚBLICA FEDERATIVA DO BRASIL", 15, True),
    t("ESTADO DO PARANÁ - SECRETARIA DE SEGURANÇA PÚBLICA"),
    t("CARTEIRA DE IDENTIDADE", 16, True),
    t("---"),
    t("Registro geral: 00.000.000-0"),
    t("Nome: MARIA EXEMPLO DA SILVA"),
    t("Filiação: ANA EXEMPLO DA SILVA e PEDRO EXEMPLO DA SILVA"),
    t("Naturalidade: CURITIBA - PR"),
    t("Data de nascimento: 14/05/1992"),
    t("Data de expedição: 10/07/2018"),
    t("Órgão expedidor: SESP/PR"),
]

CNH = [
    t("REPÚBLICA FEDERATIVA DO BRASIL", 15, True),
    t("CARTEIRA NACIONAL DE HABILITAÇÃO", 16, True),
    t("---"),
    t("Nome: JOÃO MODELO PEREIRA"),
    t("Data de nascimento: 02/09/1988"),
    t("Filiação: CLARA MODELO e JOSE PEREIRA"),
    t("Categoria: AB       Registro: 00000000000"),
    t("Data de emissão: 20/02/2024"),
    t("Validade: 20/02/2034"),
    t("Órgão emissor: DETRAN-PR"),
]

COMPROVANTE_PIX = [
    t("Comprovante de pagamento", 16, True),
    t("Pix enviado"),
    t("---"),
    t("Valor: R$ 152,30", 14, True),
    t("Data: 14/03/2026 às 18:42"),
    t("Favorecido: MERCADO EXEMPLO LTDA"),
    t("Chave Pix: 00.555.666/0001-77"),
    t("Pagador: MARIA EXEMPLO DA SILVA"),
    t("ID da transação: E00000000202603141842XYZ123"),
    t("Autenticação: 9F3A-77C1-0B2D"),
]

CERTIFICADO = [
    t("CERTIFICADO DE CONCLUSÃO", 20, True),
    t("---"),
    t("Certificamos que MARIA EXEMPLO DA SILVA concluiu com êxito o curso"),
    t("Introdução a Programação em Python, promovido pela Escola Exemplo"),
    t("de Tecnologia, com carga horária de 40 horas."),
    t(""),
    t("Conteúdo programático: variaveis, condicionais, laços, funções,"),
    t("listas, dicionários e leitura de arquivos."),
    t("---"),
    t("Data de emissão: 15/03/2026"),
    t("Código de verificação: CERT-2026-000123"),
]

EXERCICIOS = [
    t("UNIVERSIDADE EXEMPLO - Disciplina de Cálculo I", 14, True),
    t("Lista de exercícios 3 - Derivadas", 13, True),
    t("Professor: Carlos Amostra      Turma: 2026/1"),
    t("---"),
    t("Exercício 1. Calcule a derivada de f(x) = 3x^2 + 5x - 7."),
    t("Exercício 2. Derive g(x) = sen(x) . cos(x)."),
    t("Exercício 3. Encontre a reta tangente a y = x^3 no ponto x = 2."),
    t("Exercício 4. Use a regra da cadeia em h(x) = (2x + 1)^5."),
    t("---"),
    t("Entrega até a próxima aula, em grupo de até tres alunos."),
]

CONTRATO_PAG1 = [
    t("CONTRATO DE LOCAÇÃO RESIDENCIAL", 16, True),
    t("---"),
    t("Das partes: de um lado JOÃO MODELO PEREIRA, doravante LOCADOR, e de"),
    t("outro MARIA EXEMPLO DA SILVA, doravante LOCATÁRIA, tem entre si"),
    t("justo e contratado o seguinte:"),
    t("Cláusula primeira - O LOCADOR cede a LOCATÁRIA o imóvel situado na"),
    t("Rua das Amostras, 100, Apto 12, pelo prazo de 30 meses."),
    t("Cláusula segunda - O aluguel mensal e de R$ 1.800,00, com vencimento"),
    t("todo dia 5, reajustado anualmente pelo IPCA."),
    t("Cláusula terceira - Fica eleito o foro da comarca de Curitiba para"),
    t("dirimir quaisquer dúvidas oriundas deste contrato."),
]

CONTRATO_PAG2 = [
    t("CONTRATO DE LOCAÇÃO - ASSINATURAS", 14, True),
    t("---"),
    t("E por estarem assim justos e contratados, assinam o presente."),
    t(""),
    t("Curitiba, 15 de janeiro de 2026."),
    t(""),
    t("_______________________________        _______________________________"),
    t("LOCADOR: João Modelo Pereira              LOCATÁRIA: Maria Exemplo da Silva"),
    t(""),
    t("Testemunhas: ______________________   ______________________"),
]

DANFE = [
    t("DANFE - Documento auxiliar da nota fiscal eletrônica", 13, True),
    t("LOJA EXEMPLO DE ELETRÔNICOS LTDA   CNPJ 00.777.888/0001-99"),
    t("---"),
    t("Natureza da operação: VENDA DE MERCADORIA"),
    t("Chave de acesso: 4126 0300 7778 8800 0199 5500 1000 0012 3410 0001 2345"),
    t("Data de emissão: 22/03/2026"),
    t("Destinatario: MARIA EXEMPLO DA SILVA   CPF 000.000.000-00"),
    t("1  Fone de ouvido sem fio .......... 1 un .... R$ 249,90"),
    t("2  Cabo USB-C 2 m .................. 2 un .... R$ 59,80"),
    t("---"),
    t("Base de cálculo do ICMS: R$ 309,70     ICMS: R$ 55,75"),
    t("Valor total da nota: R$ 309,70", 13, True),
]

MANUAL = [
    t("CAFETEIRA ELÉTRICA EXEMPLO CX-20", 16, True),
    t("Manual de instruções", 13, True),
    t("---"),
    t("1. Instruções de montagem: encaixe o porta-filtro e a jarra na base."),
    t("2. Encha o reservatório com água até a marca MAX."),
    t("3. Ligue na tomada (127 V) e pressione o botao liga/desliga."),
    t("4. Limpeza: lave a jarra e o porta-filtro com água e sabão neutro."),
    t("---"),
    t("Especificações: 800 W, 127 V, capacidade de 20 xícaras."),
    t("Garantia de 12 meses contra defeitos de fabricação."),
]

def foto_de_praia() -> Image.Image:
    """Ceu, mar e areia: uma foto sem texto nenhum."""
    largura, altura = 1600, 1000
    foto = Image.new("RGB", (largura, altura))
    desenho = ImageDraw.Draw(foto)
    for y in range(altura):
        if y < 430:
            cor = (110 + y // 8, 170 + y // 10, 235)
        elif y < 650:
            cor = (30, 110 + (y - 430) // 6, 160)
        else:
            cor = (225, 200 - (y - 650) // 12, 150)
        desenho.line((0, y, largura, y), fill=cor)
    desenho.ellipse((1180, 90, 1330, 240), fill=(255, 236, 160))
    return foto.filter(ImageFilter.GaussianBlur(1.5))


def icone() -> Image.Image:
    imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(64, 120, 220, 255))
    desenho.polygon([(20, 18), (46, 32), (20, 46)], fill=(255, 255, 255, 255))
    return imagem


def gerar() -> None:
    DESTINO.mkdir(exist_ok=True)

    pdf(DESTINO / "conta_luz_marco_2026.pdf", [CONTA_LUZ])
    escaneada = escanear(folha(CONTA_AGUA), 1)
    escaneada.save(DESTINO / "conta_agua_fevereiro_2026_escaneada.pdf", "PDF", resolution=150)
    pdf(DESTINO / "conta_gas_janeiro_2026.pdf", [CONTA_GAS])
    pdf(DESTINO / "internet_fibra_marco_2026.pdf", [INTERNET])
    pdf(DESTINO / "boleto_mensalidade_abril_2026.pdf", [BOLETO])
    pdf(DESTINO / "fatura_cartao_marco_2026.pdf", [FATURA_CARTAO])
    pdf(DESTINO / "iptu_2026.pdf", [IPTU])
    pdf(DESTINO / "holerite_marco_2026.pdf", [HOLERITE])

    salvar_jpeg_com_exif(foto_de_celular(folha(RG), 2, angulo=4.0),
                         DESTINO / "rg_foto_celular.jpg", "2026:03:02 10:15:00")
    # Em tons de cinza, como o scanner salva: colorida, o ruido nao comprime.
    escanear(folha(CNH), 3).convert("L").save(DESTINO / "cnh_digitalizada.png", optimize=True)
    print_de_tela = folha(COMPROVANTE_PIX, largura=900, altura=1300, margem=70)
    print_de_tela.save(DESTINO / "comprovante_pix_print.png")

    pdf(DESTINO / "certificado_python.pdf", [CERTIFICADO])
    pdf(DESTINO / "lista_exercicios_calculo.pdf", [EXERCICIOS])
    pdf(DESTINO / "contrato_aluguel_assinado.pdf", [CONTRATO_PAG1, escanear(folha(CONTRATO_PAG2), 4)])
    pdf(DESTINO / "nota_fiscal_fone.pdf", [DANFE])
    # Gravada deitada, com o EXIF dizendo como girar: o que o celular faz.
    deitada = folha(MANUAL).rotate(90, expand=True)
    salvar_jpeg_com_exif(deitada, DESTINO / "manual_cafeteira_deitado.jpg",
                         "2026:01:20 09:00:00", orientacao=6)

    salvar_jpeg_com_exif(foto_de_praia(), DESTINO / "foto_praia.jpg", "2025:12:24 17:30:00")
    icone().save(DESTINO / "icone_app.png")

    # O que o AutoDoc nao pode tocar: uma pasta de projeto e um .zip.
    projeto = DESTINO / "projeto_site"
    projeto.mkdir(exist_ok=True)
    (projeto / "index.html").write_text(
        "<!doctype html>\n<title>Site de exemplo</title>\n<h1>Ola</h1>\n", encoding="utf-8")
    (projeto / "estilo.css").write_text("h1 { color: #4078dc; }\n", encoding="utf-8")
    icone().save(projeto / "logo.png")
    with zipfile.ZipFile(DESTINO / "fotos_viagem.zip", "w", zipfile.ZIP_DEFLATED) as zipado:
        zipado.writestr("leia.txt", "Fotos da viagem de exemplo.\n")
        foto = io.BytesIO()
        foto_de_praia().resize((400, 250)).save(foto, "JPEG")
        zipado.writestr("praia.jpg", foto.getvalue())

    # O que cada um deve virar esta em testes/test_exemplos.py.
    print(f"exemplos gerados em {DESTINO}")


if __name__ == "__main__":
    gerar()
