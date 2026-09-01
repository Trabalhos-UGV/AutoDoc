"""Extracao de texto, incluindo o OCR de PDF digitalizado.

O Tesseract e opcional e pode nao estar instalado na maquina que roda os
testes. Por isso o OCR e exercitado com um dublê no lugar do `image_to_string`:
o que se quer verificar aqui e o **caminho** — que o PDF sem camada de texto
chega ao OCR, e que a falta do Tesseract vira `ExtracaoIndisponivel` em vez de
derrubar o programa.
"""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc import extrator
from autodoc.extrator import ExtracaoIndisponivel, extrair_com_origem, hash_arquivo

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
        self.assertEqual(extrator._extrair_pdf(self.pdf), "")

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
        with mock.patch.object(extrator, "_extrair_pdf", return_value="ja tem texto"), \
             mock.patch.object(extrator, "texto_da_imagem") as ocr:
            texto, origem = extrair_com_origem(self.pdf)

        ocr.assert_not_called()
        self.assertEqual(origem, "PDF com texto embutido")
        self.assertEqual(texto, "ja tem texto")

    def test_sem_tesseract_vira_extracao_indisponivel(self):
        """A situacao desta maquina: pytesseract instalado, Tesseract nao."""
        import pytesseract

        with mock.patch.object(pytesseract, "image_to_string",
                               side_effect=pytesseract.TesseractNotFoundError()):
            with self.assertRaises(ExtracaoIndisponivel) as erro:
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


if __name__ == "__main__":
    unittest.main()
