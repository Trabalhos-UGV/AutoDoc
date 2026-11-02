"""Identificacao da data do documento."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from unittest import mock

from autodoc import datas
from autodoc.datas import data_do_documento, extrair_data, extrair_data_rotulada, extrair_datas

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

    def test_rotulo_com_data_iso(self):
        """Um PDF gerado por sistema costuma escrever a data em ISO."""
        self.assertEqual(extrair_data_rotulada("Vencimento: 2026-03-15"),
                         ("2026-03-15", "vencimento"))

    def test_rotulo_com_data_por_extenso(self):
        self.assertEqual(
            extrair_data_rotulada("Data de assinatura: 12 de março de 2026"),
            ("2026-03-12", "data de assinatura"))

    def test_conta_de_exemplo_usa_o_vencimento(self):
        texto = (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8")
        self.assertEqual(extrair_data_rotulada(texto), ("2026-03-12", "vencimento"))


class TestExtrairData(unittest.TestCase):
    def test_cai_na_primeira_data_quando_nao_ha_rotulo(self):
        self.assertEqual(extrair_data("assinado em 01/03/2026"), "2026-03-01")

    def test_prefere_a_data_rotulada(self):
        self.assertEqual(extrair_data("Leitura: 01/03/2026 Vencimento: 15/03/2026"),
                         "2026-03-15")

    def test_cai_no_padrao_informado(self):
        self.assertEqual(extrair_data("sem data", date(2026, 1, 1)), "2026-01-01")

    def test_sem_data_e_sem_padrao(self):
        self.assertIsNone(extrair_data("sem data"))


class TestAnoPlausivel(unittest.TestCase):
    def test_ano_curto_do_seculo_passado(self):
        """'98' e 1998: virar 2098 mandava o comprovante para uma pasta do futuro."""
        self.assertEqual(extrair_datas("15/08/98"), [date(1998, 8, 15)])
        self.assertEqual(extrair_datas("15/08/26"), [date(2026, 8, 15)])

    def test_ano_impossivel_e_erro_de_leitura(self):
        self.assertEqual(extrair_datas("12/03/202 e 12/03/1890 e 12/03/2099"), [])

    def test_virada_do_seculo_acompanha_o_ano_atual(self):
        with mock.patch.object(datas, "_ano_atual", return_value=2040):
            self.assertEqual(extrair_datas("01/01/41"), [date(2041, 1, 1)])
            self.assertEqual(extrair_datas("01/01/55"), [date(1955, 1, 1)])


class TestOcrEVersao(unittest.TestCase):
    def test_letra_no_lugar_de_digito(self):
        self.assertEqual(extrair_datas("Vencimento 12/O3/2026 e 1l/03/2026"), [date(2026, 3, 12), date(2026, 3, 11)])

    def test_palavra_nao_vira_data(self):
        self.assertEqual(extrair_datas("lo/ol/oi"), [])

    def test_numero_de_versao_nao_e_data(self):
        self.assertEqual(extrair_datas("Modelo v1.2.26"), [])


class TestDonoDaData(unittest.TestCase):
    def test_nascimento_nao_conta_como_data_do_documento(self):
        texto = "DATA DE NASCIMENTO 05/09/1995  DATA DE EXPEDICAO 10/07/2018"
        self.assertEqual(data_do_documento(texto, "documento_pessoal")[0], "2018-07-10")

    def test_leitura_anterior_nunca_e_a_data(self):
        self.assertEqual(data_do_documento("COPEL Leitura anterior 10/02/2026", "conta_luz")[0], None)

    def test_tabela_pareia_rotulo_e_valor_pela_ordem(self):
        texto = "LEITURA ANTERIOR  LEITURA ATUAL  VENCIMENTO  TOTAL\n18/02/2026  19/03/2026  06/04/2026  R$ 10,00"
        self.assertEqual(data_do_documento(texto, "conta_luz")[0], "2026-03-19")
        self.assertEqual(data_do_documento(texto, "boleto")[0], "2026-04-06")


class TestMesDeReferencia(unittest.TestCase):
    def test_formatos_de_mes_e_ano(self):
        for texto in ("Referencia MAR/2026", "Mes de referencia: 03/2026", "Competencia 03/26",
                      "Periodo de apuracao: Marco/2026", "Referencia: marco de 2026"):
            with self.subTest(texto=texto):
                self.assertEqual(data_do_documento(texto, "conta_luz")[0], "2026-03-01")

    def test_mes_e_ano_solto_nao_e_data(self):
        """Sem rotulo de referencia, '03/26' pode ser qualquer numero."""
        self.assertEqual(data_do_documento("Parcela 03/26 do financiamento", "contrato"), (None, mock.ANY))

    def test_conta_mensal_prefere_a_referencia_ao_vencimento(self):
        texto = "Referencia MAR/2026  Vencimento 06/04/2026"
        data, como = data_do_documento(texto, "conta_luz")
        self.assertEqual(data, "2026-03-01")
        self.assertIn("mês de referência", como)
        self.assertEqual(data_do_documento(texto, "boleto")[0], "2026-04-06")

    def test_sem_referencia_vale_o_vencimento_escrito(self):
        """Nada de 'vencimento menos um mes': ha conta que vence no proprio mes."""
        self.assertEqual(data_do_documento("Vencimento 12/03/2026", "conta_luz")[0], "2026-03-12")


class TestSemData(unittest.TestCase):
    def test_sem_data_nao_inventa(self):
        data, como = data_do_documento("CONTRATO DE LOCACAO sem data nenhuma", "contrato")
        self.assertIsNone(data)
        self.assertIn("sem-data", como)

    def test_categoria_desconhecida_usa_a_ordem_geral(self):
        self.assertEqual(data_do_documento("Emissao 01/02/2026 Vencimento 10/02/2026")[0], "2026-02-10")

    def test_cai_na_primeira_data_solta(self):
        data, como = data_do_documento("Pix enviado 04/04/2026", "comprovante")
        self.assertEqual(data, "2026-04-04")
        self.assertIn("sem rótulo", como)


if __name__ == "__main__":
    unittest.main()
