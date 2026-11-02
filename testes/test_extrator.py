"""Extracao de texto, incluindo o OCR de PDF digitalizado.

O Tesseract e opcional e pode nao estar instalado na maquina que roda os
testes. Por isso o OCR e exercitado com um dublê no lugar do `image_to_string`:
o que se quer verificar aqui e o **caminho** — que o PDF sem camada de texto
chega ao OCR, e que a falta do Tesseract vira `ExtracaoIndisponivel` em vez de
derrubar o programa.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc import extrator
from autodoc.extrator import (
    ExtracaoIndisponivel,
    OcrIndisponivel,
    extrair_com_origem,
    hash_arquivo,
)

TEXTO_DA_CONTA = (
    "CEMIG DISTRIBUICAO S.A.\n"
    "CONTA DE ENERGIA ELETRICA\n"
    "Consumo faturado: 187 kWh\n"
    "VENCIMENTO 12/03/2026\n"
    "TOTAL A PAGAR R$ 187,42\n"
)


def pdf_digitalizado(destino: Path) -> Path:
    """Um PDF que e so imagem, como o que sai de um scanner."""
    from PIL import Image, ImageDraw

    imagem = Image.new("RGB", (900, 500), "white")
    desenho = ImageDraw.Draw(imagem)
    for numero, linha in enumerate(TEXTO_DA_CONTA.splitlines()):
        desenho.text((40, 40 + numero * 44), linha, fill="black")
    imagem.save(destino, "PDF", resolution=150)
    return destino


class BaseArquivos(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)


class TestHash(BaseArquivos):
    def test_mesmo_conteudo_mesmo_hash(self):
        um = self.pasta / "a.txt"
        outro = self.pasta / "b.txt"
        um.write_text("igual", encoding="utf-8")
        outro.write_text("igual", encoding="utf-8")
        self.assertEqual(hash_arquivo(um), hash_arquivo(outro))

    def test_conteudo_diferente_hash_diferente(self):
        um = self.pasta / "a.txt"
        outro = self.pasta / "b.txt"
        um.write_text("um", encoding="utf-8")
        outro.write_text("outro", encoding="utf-8")
        self.assertNotEqual(hash_arquivo(um), hash_arquivo(outro))


class TestTexto(BaseArquivos):
    def test_arquivo_de_texto(self):
        alvo = self.pasta / "conta.txt"
        alvo.write_text(TEXTO_DA_CONTA, encoding="utf-8")

        texto, origem = extrair_com_origem(alvo)
        self.assertIn("kWh", texto)
        self.assertEqual(origem, "arquivo de texto")

    def test_formato_nao_suportado(self):
        alvo = self.pasta / "planilha.xlsx"
        alvo.write_bytes(b"nada")
        with self.assertRaises(ExtracaoIndisponivel):
            extrair_com_origem(alvo)


class TestArquivosDefeituosos(BaseArquivos):
    """Nenhum arquivo ruim pode derrubar o observador da pasta."""

    def setUp(self):
        super().setUp()
        # O pypdf reclama no proprio log ao ver um arquivo torto. E o
        # comportamento esperado aqui, entao nao precisa sujar a saida.
        pypdf = logging.getLogger("pypdf")
        nivel = pypdf.level
        pypdf.setLevel(logging.CRITICAL)
        self.addCleanup(pypdf.setLevel, nivel)

    def test_pdf_corrompido(self):
        alvo = self.pasta / "quebrado.pdf"
        alvo.write_bytes(b"isto nao e um PDF")
        with self.assertRaises(ExtracaoIndisponivel):
            extrair_com_origem(alvo)

    def test_imagem_corrompida(self):
        alvo = self.pasta / "falsa.png"
        alvo.write_bytes(b"nem isto e um PNG")
        with self.assertRaises(ExtracaoIndisponivel):
            extrair_com_origem(alvo)


class TestOcrDePdf(BaseArquivos):
    def setUp(self):
        super().setUp()
        self.pdf = pdf_digitalizado(self.pasta / "scan.pdf")

    def test_pdf_digitalizado_nao_tem_camada_de_texto(self):
        """A premissa do fallback: sem isto nao haveria o que consertar."""
        from pypdf import PdfReader
        self.assertEqual(extrator._texto_da_pagina(PdfReader(str(self.pdf)).pages[0]), "")

    def test_o_pypdf_alcanca_a_imagem_embutida(self):
        from pypdf import PdfReader
        imagens = list(PdfReader(str(self.pdf)).pages[0].images)
        self.assertEqual(len(imagens), 1)

    def test_pdf_sem_texto_passa_pelo_ocr(self):
        with mock.patch.object(extrator, "texto_da_imagem",
                               return_value=TEXTO_DA_CONTA) as ocr:
            texto, origem = extrair_com_origem(self.pdf)

        ocr.assert_called_once()
        self.assertEqual(origem, "PDF digitalizado — OCR")
        self.assertIn("kWh", texto)

    def test_o_que_o_ocr_leu_e_classificavel(self):
        """O ponto do OCR: um scan vira um documento classificado."""
        from autodoc.classificador import classificar
        from autodoc.datas import extrair_data_rotulada

        with mock.patch.object(extrator, "texto_da_imagem",
                               return_value=TEXTO_DA_CONTA):
            texto, _ = extrair_com_origem(self.pdf)

        self.assertEqual(classificar(texto).categoria, "conta_luz")
        self.assertEqual(extrair_data_rotulada(texto), ("2026-03-12", "vencimento"))

    def test_pdf_com_camada_de_texto_nao_aciona_o_ocr(self):
        """OCR e caro; so entra quando nao ha texto para ler."""
        with mock.patch.object(extrator, "_texto_da_pagina", return_value=TEXTO_DA_CONTA), \
             mock.patch.object(extrator, "texto_da_imagem") as ocr:
            texto, origem = extrair_com_origem(self.pdf)

        ocr.assert_not_called()
        self.assertEqual(origem, "PDF com texto embutido")
        self.assertEqual(texto, TEXTO_DA_CONTA)

    def test_sem_tesseract_vira_extracao_indisponivel(self):
        """A situacao desta maquina: pytesseract instalado, Tesseract nao."""
        import pytesseract

        with mock.patch.object(pytesseract, "image_to_string",
                               side_effect=pytesseract.TesseractNotFoundError()):
            with self.assertRaises(OcrIndisponivel) as erro:
                extrair_com_origem(self.pdf)

        self.assertIn("Tesseract", str(erro.exception))

    def test_idioma_ausente_tenta_o_padrao(self):
        """Sem o pacote de portugues, ler em ingles ainda acha datas e totais."""
        import pytesseract

        def falha_so_com_idioma(imagem, lang=None, **kwargs):
            if lang is not None:
                raise pytesseract.TesseractError(1, "idioma por nao encontrado")
            return TEXTO_DA_CONTA

        with mock.patch.object(pytesseract, "image_to_string", falha_so_com_idioma):
            texto, origem = extrair_com_origem(self.pdf)

        self.assertEqual(origem, "PDF digitalizado — OCR")
        self.assertIn("kWh", texto)


class TestDependenciasAusentes(BaseArquivos):
    """Faltar uma biblioteca só pode quebrar o formato que depende dela."""

    def test_sem_pypdf_o_pdf_fica_indisponivel(self):
        alvo = pdf_digitalizado(self.pasta / "scan.pdf")
        with mock.patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaises(ExtracaoIndisponivel) as erro:
                extrair_com_origem(alvo)
        self.assertIn("pypdf", str(erro.exception))

    def test_sem_pytesseract_a_imagem_fica_indisponivel(self):
        alvo = self.pasta / "foto.png"
        from PIL import Image
        Image.new("RGB", (10, 10), "white").save(alvo)

        with mock.patch.dict(sys.modules, {"pytesseract": None}):
            with self.assertRaises(ExtracaoIndisponivel) as erro:
                extrair_com_origem(alvo)
        self.assertIn("OCR indisponivel", str(erro.exception))

    def test_o_texto_puro_continua_funcionando_sem_nenhuma_delas(self):
        """É o ponto das dependências opcionais: o núcleo não depende delas."""
        alvo = self.pasta / "conta.txt"
        alvo.write_text(TEXTO_DA_CONTA, encoding="utf-8")

        with mock.patch.dict(sys.modules, {"pypdf": None, "pytesseract": None}):
            texto, origem = extrair_com_origem(alvo)

        self.assertIn("kWh", texto)
        self.assertEqual(origem, "arquivo de texto")


TEXTO_LONGO = "CONTRATO DE LOCACAO — clausula primeira, do objeto e do prazo"


def pagina_falsa(texto: str = "", imagens: int = 0):
    pagina = mock.Mock(images=[mock.Mock(image=None) for _ in range(imagens)])
    pagina.extract_text.return_value = texto
    return pagina


def extrair_paginas(paginas):
    with mock.patch.object(extrator, "_leitor_pdf", return_value=mock.Mock(pages=paginas)):
        return extrator._extrair_pdf(Path("qualquer.pdf"))


class TestPaginasDefeituosas(BaseArquivos):
    def test_uma_pagina_ruim_nao_invalida_as_outras(self):
        ruim = mock.Mock(images=[])
        ruim.extract_text.side_effect = RuntimeError("objeto corrompido")

        texto, _ = extrair_paginas([ruim, pagina_falsa(TEXTO_LONGO)])
        self.assertEqual(texto, TEXTO_LONGO)

    def test_imagem_que_o_pypdf_nao_decodifica_e_pulada(self):
        pagina = pagina_falsa()
        type(pagina).images = mock.PropertyMock(side_effect=RuntimeError("filtro exotico"))
        self.assertEqual(extrator._ocr_da_pagina(pagina), "")

    def test_uma_imagem_ilegivel_nao_derruba_as_outras(self):
        lidas = iter([ExtracaoIndisponivel("imagem corrompida"), "RECIBO"])

        def ocr(_imagem):
            lido = next(lidas)
            if isinstance(lido, Exception):
                raise lido
            return lido

        with mock.patch.object(extrator, "texto_da_imagem", ocr):
            self.assertEqual(extrator._ocr_da_pagina(pagina_falsa(imagens=2)), "RECIBO")


class TestOcrPorPagina(BaseArquivos):
    """A decisao do OCR e de cada pagina, e nao do PDF inteiro."""

    def test_pdf_misto_le_as_duas_partes(self):
        """Contrato digitado com a pagina assinada escaneada no fim."""
        paginas = [pagina_falsa(TEXTO_LONGO), pagina_falsa(imagens=1)]
        with mock.patch.object(extrator, "texto_da_imagem", return_value="Assinado em 10/03/2026"):
            texto, origem = extrair_paginas(paginas)

        self.assertIn("CONTRATO", texto)
        self.assertIn("Assinado", texto)
        self.assertEqual(origem, "PDF com texto embutido + OCR em 1 página(s)")

    def test_numero_da_pagina_em_texto_nao_impede_o_ocr(self):
        with mock.patch.object(extrator, "texto_da_imagem", return_value=TEXTO_DA_CONTA):
            texto, origem = extrair_paginas([pagina_falsa("Página 1 de 1", imagens=1)])

        self.assertIn("kWh", texto)
        self.assertIn("Página 1", texto)
        self.assertEqual(origem, "PDF digitalizado — OCR")

    def test_sem_ocr_o_texto_que_ha_e_aproveitado_e_dito(self):
        paginas = [pagina_falsa(TEXTO_LONGO), pagina_falsa(imagens=1), pagina_falsa(imagens=1)]
        with mock.patch.object(extrator, "texto_da_imagem",
                               side_effect=OcrIndisponivel("sem Tesseract")) as ocr:
            texto, origem = extrair_paginas(paginas)

        self.assertEqual(texto, TEXTO_LONGO)
        self.assertIn("sem OCR", origem)
        self.assertEqual(ocr.call_count, 1, "sem OCR uma vez, sem OCR nas outras")

    def test_pagina_curta_sem_imagem_nao_muda_a_origem(self):
        texto, origem = extrair_paginas([pagina_falsa(TEXTO_LONGO), pagina_falsa("fim")])
        self.assertEqual(origem, "PDF com texto embutido")
        self.assertTrue(texto.endswith("fim"))


class TestPreparoDaImagem(unittest.TestCase):
    def test_foto_de_lado_e_endireitada_pelo_exif(self):
        from PIL import Image

        deitada = Image.new("RGB", (1600, 1300), "white")
        exif = deitada.getexif()
        exif[0x0112] = 6  # Orientation: girar 90 graus
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "foto.jpg"
            deitada.save(alvo, exif=exif)
            with Image.open(alvo) as aberta:
                pronta = extrator.preparar_para_ocr(aberta)

        self.assertEqual(pronta.size, (1300, 1600))
        self.assertEqual(pronta.mode, "L")

    def test_imagem_pequena_e_ampliada_com_teto(self):
        from PIL import Image

        self.assertEqual(extrator.preparar_para_ocr(Image.new("RGB", (600, 400))).size,
                         (1800, 1200))
        miniatura = extrator.preparar_para_ocr(Image.new("RGB", (100, 50)))
        self.assertEqual(miniatura.size, (400, 200))

    def test_imagem_grande_nao_e_mexida_no_tamanho(self):
        from PIL import Image
        self.assertEqual(extrator.preparar_para_ocr(Image.new("RGB", (2480, 3508))).size,
                         (2480, 3508))

    def test_pdf_sem_texto_e_sem_imagem(self):
        """Um PDF só com vetores: não há o que ler nem o que passar pelo OCR."""
        leitor = mock.Mock(pages=[pagina_falsa()])
        with mock.patch.object(extrator, "_leitor_pdf", return_value=leitor):
            texto, origem = extrair_com_origem(Path("vazio.pdf"))

        self.assertEqual(texto, "")
        self.assertIn("sem imagem legível", origem)

    def test_o_teto_de_paginas_do_ocr_e_respeitado(self):
        """Um PDF de duzentas páginas travaria o monitoramento inteiro."""
        paginas = [pagina_falsa(imagens=1) for _ in range(40)]

        with mock.patch.object(extrator, "texto_da_imagem", return_value="x") as ocr:
            extrair_paginas(paginas)

        self.assertEqual(ocr.call_count, extrator.PAGINAS_OCR)


class TestOcrQueFalhaDeVez(BaseArquivos):
    def test_erro_que_persiste_sem_idioma_vira_indisponivel(self):
        import pytesseract

        with mock.patch.object(pytesseract, "image_to_string",
                               side_effect=pytesseract.TesseractError(1, "imagem corrompida")):
            with self.assertRaises(ExtracaoIndisponivel) as erro:
                from PIL import Image
                extrator.texto_da_imagem(Image.new("RGB", (10, 10)))

        self.assertIn("OCR falhou", str(erro.exception))


class TestImagem(BaseArquivos):
    def test_imagem_valida_passa_pelo_ocr(self):
        from PIL import Image

        alvo = self.pasta / "recibo.png"
        Image.new("RGB", (60, 30), "white").save(alvo)

        with mock.patch.object(extrator, "texto_da_imagem",
                               return_value="RECIBO 12/03/2026") as ocr:
            texto, origem = extrair_com_origem(alvo)

        ocr.assert_called_once()
        self.assertEqual(origem, "imagem — OCR")
        self.assertIn("RECIBO", texto)


class TestFormatosDeFoto(BaseArquivos):
    """Scanner salva .tiff, celular salva .webp e o iPhone salva .heic."""

    def test_cada_formato_chega_ao_ocr(self):
        from PIL import Image

        for extensao, formato in ((".tif", "TIFF"), (".webp", "WEBP"), (".heic", "HEIF")):
            with self.subTest(formato=extensao):
                alvo = self.pasta / f"foto{extensao}"
                Image.new("RGB", (60, 30), "white").save(alvo, formato)
                with mock.patch.object(extrator, "texto_da_imagem",
                                       return_value="RECIBO") as ocr:
                    texto, origem = extrair_com_origem(alvo)
                ocr.assert_called_once()
                self.assertEqual(texto, "RECIBO")

    def test_sem_pillow_heif_o_resto_do_ocr_continua(self):
        with mock.patch.dict(sys.modules, {"pillow_heif": None}):
            pytesseract, Image = extrator._motor_ocr()
        self.assertTrue(hasattr(Image, "open"))

    def test_heic_ilegivel_diz_o_que_conferir(self):
        alvo = self.pasta / "foto.heic"
        alvo.write_bytes(b"nao e uma foto")
        with self.assertRaises(ExtracaoIndisponivel) as erro:
            extrair_com_origem(alvo)
        self.assertIn("pillow-heif", str(erro.exception))


class TestDiagnosticoDoOcr(unittest.TestCase):
    """Antes, a falta do OCR so aparecia como foto atras de foto na revisao."""

    def com_idiomas(self, idiomas):
        import pytesseract
        return mock.patch.object(pytesseract, "get_languages", return_value=idiomas)

    def test_pronto_em_portugues(self):
        with self.com_idiomas(["eng", "por", "osd"]):
            diagnostico = extrator.diagnostico_ocr()
        self.assertTrue(diagnostico["portugues"])
        self.assertEqual(diagnostico["como_instalar"], "")

    def test_sem_pacote_de_portugues_diz_como_resolver(self):
        with self.com_idiomas(["eng", "osd"]):
            diagnostico = extrator.diagnostico_ocr()
        self.assertTrue(diagnostico["disponivel"])
        self.assertFalse(diagnostico["portugues"])
        self.assertIn("inglês", diagnostico["resumo"])
        self.assertTrue(diagnostico["como_instalar"])

    def test_sem_tesseract_diz_como_instalar(self):
        import pytesseract
        with mock.patch.object(pytesseract, "get_languages",
                               side_effect=pytesseract.TesseractNotFoundError()):
            diagnostico = extrator.diagnostico_ocr()
        self.assertFalse(diagnostico["disponivel"])
        self.assertIn("não instalado", diagnostico["resumo"])

    def test_o_comando_e_o_deste_sistema(self):
        for plataforma, trecho in (("darwin", "brew"), ("linux", "apt"),
                                   ("win32", "UB Mannheim"), ("freebsd14", "apt")):
            with self.subTest(sistema=plataforma), \
                 mock.patch.object(extrator.sys, "platform", plataforma):
                self.assertIn(trecho, extrator.como_instalar_ocr())


class TestTesseractNoWindows(BaseArquivos):
    """O instalador do Windows nao poe o Tesseract no PATH."""

    def setUp(self):
        super().setUp()
        import pytesseract
        self.pytesseract = pytesseract
        original = pytesseract.pytesseract.tesseract_cmd
        self.addCleanup(setattr, pytesseract.pytesseract, "tesseract_cmd", original)

    def achar(self, pastas, plataforma="win32", no_path=None):
        with mock.patch.object(extrator.sys, "platform", plataforma), \
             mock.patch.object(extrator.shutil, "which", return_value=no_path), \
             mock.patch.object(extrator, "PASTAS_TESSERACT_WINDOWS", pastas):
            extrator._achar_tesseract_no_windows(self.pytesseract)
        return self.pytesseract.pytesseract.tesseract_cmd

    def test_acha_na_pasta_de_programas(self):
        instalado = self.pasta / "Tesseract-OCR"
        instalado.mkdir()
        (instalado / "tesseract.exe").touch()
        self.assertEqual(self.achar((self.pasta / "nada", instalado)),
                         str(instalado / "tesseract.exe"))

    def test_no_path_ou_fora_do_windows_nao_mexe(self):
        antes = self.pytesseract.pytesseract.tesseract_cmd
        self.assertEqual(self.achar((self.pasta,), no_path="C:/tesseract.exe"), antes)
        self.assertEqual(self.achar((self.pasta,), plataforma="darwin"), antes)
        self.assertEqual(self.achar((self.pasta / "nada",)), antes)


class TestErroDoSistemaDeArquivos(BaseArquivos):
    def test_erro_de_leitura_do_pdf_sobe_como_oserror(self):
        """Sem permissão não é "PDF ilegível": o pipeline trata os dois, mas o
        motivo que chega na tela tem que ser o verdadeiro."""
        alvo = self.pasta / "trancado.pdf"
        alvo.write_bytes(b"%PDF-1.4")

        with mock.patch("pypdf.PdfReader", side_effect=OSError("sem permissao")):
            with self.assertRaises(OSError) as erro:
                extrator._leitor_pdf(alvo)

        self.assertNotIsInstance(erro.exception, ExtracaoIndisponivel)


class TestExtrairTexto(BaseArquivos):
    def test_o_involucro_devolve_so_o_texto(self):
        alvo = self.pasta / "conta.txt"
        alvo.write_text(TEXTO_DA_CONTA, encoding="utf-8")
        self.assertEqual(extrator.extrair_texto(alvo), extrair_com_origem(alvo)[0])


if __name__ == "__main__":
    unittest.main()
