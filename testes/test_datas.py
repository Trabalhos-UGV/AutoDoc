"""Identificacao da data do documento."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from autodoc.datas import extrair_data, extrair_data_rotulada, extrair_datas

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class TestFormatos(unittest.TestCase):
    def test_formato_brasileiro(self):
        self.assertEqual(extrair_datas("vence em 12/03/2026"), [date(2026, 3, 12)])

    def test_formato_iso(self):
        self.assertEqual(extrair_datas("2026-03-12"), [date(2026, 3, 12)])

    def test_por_extenso(self):
        self.assertEqual(extrair_datas("12 de março de 2026"), [date(2026, 3, 12)])

    def test_ano_com_dois_digitos(self):
        self.assertEqual(extrair_datas("12/03/26"), [date(2026, 3, 12)])

    def test_separador_ponto_e_traco(self):
        self.assertEqual(extrair_datas("12.03.2026"), [date(2026, 3, 12)])
        self.assertEqual(extrair_datas("12-03-2026"), [date(2026, 3, 12)])


class TestDataInvalida(unittest.TestCase):
    """Numero com cara de data nao e data."""

    def test_dia_e_mes_impossiveis(self):
        self.assertEqual(extrair_datas("32/13/2026"), [])

    def test_29_de_fevereiro_fora_de_bissexto(self):
        self.assertEqual(extrair_datas("29/02/2026"), [])

    def test_sem_data_nenhuma(self):
        self.assertEqual(extrair_datas("nao ha data aqui"), [])
        self.assertIsNone(extrair_data_rotulada("nao ha data aqui"))


class TestDataPorRotulo(unittest.TestCase):
    """O motivo de a data nao ser simplesmente a primeira do texto."""

    CONTA = (
        "CEMIG — CONTA DE ENERGIA\n"
        "Leitura anterior: 10/02/2026\n"
        "Leitura atual:    10/03/2026\n"
        "VENCIMENTO        12/03/2026\n"
    )

    def test_vencimento_ganha_da_primeira_data_do_texto(self):
        self.assertEqual(extrair_datas(self.CONTA)[0], date(2026, 2, 10))
        self.assertEqual(extrair_data_rotulada(self.CONTA), ("2026-03-12", "vencimento"))

    def test_vencimento_ganha_de_emissao(self):
        texto = "Data de emissão: 01/03/2026\nVencimento: 15/03/2026"
        data, rotulo = extrair_data_rotulada(texto)
        self.assertEqual((data, rotulo), ("2026-03-15", "vencimento"))

    def test_espacamento_de_tabela_nao_separa_o_rotulo_da_data(self):
        """A distancia e medida no texto normalizado, com os espacos juntados.

        Numa conta o rotulo e o valor ficam em colunas distantes, cheias de
        espaco entre si; medir no texto cru desligaria "VENCIMENTO" da propria
        data que ele rotula.
        """
        texto = "VENCIMENTO" + " " * 60 + "12/03/2026"
        self.assertEqual(extrair_data_rotulada(texto), ("2026-03-12", "vencimento"))

    def test_rotulo_longe_demais_nao_conta(self):
        """Passado o alcance, o rotulo nao fala mais pela data."""
        texto = "VENCIMENTO conforme consta no contrato assinado entre as partes " \
                "interessadas e registrado em cartorio 12/03/2026"
        self.assertIsNone(extrair_data_rotulada(texto))

    def test_conta_de_exemplo_usa_o_vencimento(self):
        texto = (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8")
        self.assertEqual(extrair_data_rotulada(texto), ("2026-03-12", "vencimento"))


class TestExtrairData(unittest.TestCase):
    def test_cai_na_primeira_data_quando_nao_ha_rotulo(self):
        self.assertEqual(extrair_data("assinado em 01/03/2026"), "2026-03-01")

    def test_cai_no_padrao_informado(self):
        self.assertEqual(extrair_data("sem data", date(2026, 1, 1)), "2026-01-01")

    def test_sem_data_e_sem_padrao(self):
        self.assertIsNone(extrair_data("sem data"))


if __name__ == "__main__":
    unittest.main()
