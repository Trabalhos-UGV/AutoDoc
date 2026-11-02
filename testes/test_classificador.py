"""Classificacao: as categorias, a confianca e o limiar."""

from __future__ import annotations

import unittest
from pathlib import Path

from autodoc.classificador import (
    LIMIAR,
    NAO_CLASSIFICADO,
    ROTULOS,
    classificar,
    normalizar,
    pontuar,
    tolerante,
)

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class TestNormalizar(unittest.TestCase):
    def test_tira_acento_e_caixa(self):
        self.assertEqual(normalizar("MARÇO"), "marco")
        self.assertEqual(normalizar("Água Não"), "agua nao")

    def test_junta_espacos(self):
        self.assertEqual(normalizar("total   a\n\npagar"), "total a pagar")


class TestClassificarExemplos(unittest.TestCase):
    """Os documentos de exemplo sao o contrato do classificador com a realidade."""

    ESPERADO = {
        "conta_energia_marco.txt": "conta_luz",
        "nota_fiscal_1234.txt": "nota_fiscal",
        "contrato_aluguel.txt": "contrato",
        "comprovante_pix.txt": "comprovante",
        "scan0031_ilegivel.txt": NAO_CLASSIFICADO,
    }

    def test_cada_exemplo_cai_na_categoria_certa(self):
        for nome, categoria in self.ESPERADO.items():
            with self.subTest(arquivo=nome):
                texto = (EXEMPLOS / nome).read_text(encoding="utf-8")
                self.assertEqual(classificar(texto).categoria, categoria)

    def test_documento_legitimo_passa_do_limiar(self):
        """O caso que reprovava antes: cobertura alta nao basta, margem importa."""
        texto = (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8")
        self.assertGreaterEqual(classificar(texto).confianca, LIMIAR)

    def test_a_explicacao_acompanha_a_decisao(self):
        texto = (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8")
        resultado = classificar(texto)
        self.assertIn("conta_luz", resultado.regra)
        self.assertTrue(resultado.chaves, "sem palavras-chave nao ha o que explicar")

    def test_chaves_saem_com_a_grafia_do_documento(self):
        """O painel mostra o que esta escrito no papel, nao a regra interna."""
        resultado = classificar("CONSUMO FATURADO: 187 kWh — CEMIG")
        self.assertIn("CONSUMO FATURADO", resultado.chaves)


class TestDuvida(unittest.TestCase):
    """Na duvida o classificador precisa admitir duvida, e nao chutar."""

    def test_texto_vazio(self):
        resultado = classificar("")
        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertEqual(resultado.confianca, 0.0)

    def test_texto_sem_termo_conhecido(self):
        self.assertEqual(classificar("bom dia, tudo bem?").categoria, NAO_CLASSIFICADO)

    def test_empate_no_topo_nao_escolhe(self):
        """Duas categorias com a mesma pontuacao e duvida, e nao escolha."""
        texto = "distribuidora cnpj"
        placar = pontuar(texto)
        self.assertEqual(placar["conta_luz"], placar["nota_fiscal"])

        resultado = classificar(texto)
        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertIn("empate", resultado.regra)

    def test_evidencia_fraca_vai_para_revisao(self):
        """Um termo leve e solto nao sustenta uma categoria."""
        resultado = classificar("consumo")
        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertIn("termos fracos", resultado.regra)

    def test_confianca_nunca_chega_a_certeza_absoluta(self):
        texto = (EXEMPLOS / "nota_fiscal_1234.txt").read_text(encoding="utf-8")
        self.assertLess(classificar(texto).confianca, 1.0)


class TestApresentacao(unittest.TestCase):
    """O que a tela lê da classificação."""

    def test_rotulo_traduz_a_categoria_interna(self):
        texto = (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8")
        self.assertEqual(classificar(texto).rotulo, "Conta de energia")

    def test_categoria_desconhecida_aparece_como_esta(self):
        from autodoc.classificador import Classificacao

        self.assertEqual(Classificacao("inventada", 0.5, "").rotulo, "inventada")

    def test_revisar_marca_o_que_nao_foi_classificado(self):
        self.assertTrue(classificar("").revisar)
        texto = (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8")
        self.assertFalse(classificar(texto).revisar)


class TestFronteiraDePalavra(unittest.TestCase):
    def test_agua_nao_casa_dentro_de_aguardando(self):
        self.assertNotIn("conta_agua", pontuar("aguardando pagamento"))

    def test_acento_solto_e_descartado(self):
        """Um acento sem letra debaixo dele some, em vez de virar caractere."""
        self.assertEqual(normalizar("consumo\u0301"), "consumo")

    def test_acento_grudado_na_letra_tambem_some(self):
        self.assertEqual(normalizar("a\u0301gua"), "agua")


class TestTermosFracos(unittest.TestCase):
    """Pix, CPF e vencimento estao em quase tudo: sozinhos, nao dizem o tipo."""

    def test_so_termo_fraco_vai_para_revisao(self):
        resultado = classificar("Cadastre sua chave Pix no aplicativo")
        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertIn("termos fracos", resultado.regra)

    def test_termo_forte_com_fraco_classifica(self):
        self.assertEqual(classificar("Comprovante  ID da transacao 1  Pix").categoria, "comprovante")


class TestNormalizacaoDeOcr(unittest.TestCase):
    def test_hifen_entre_letras_some(self):
        self.assertEqual(normalizar("NF-e"), "nfe")
        self.assertEqual(normalizar("12-03-2026"), "12-03-2026")

    def test_palavra_quebrada_no_fim_da_linha(self):
        self.assertEqual(normalizar("consu-\nmo fatu-\n  rado"), "consumo faturado")

    def test_hifen_com_espaco_e_separador(self):
        self.assertEqual(normalizar("Copel - Paraná"), "copel - parana")
        self.assertEqual(normalizar("ponta- grossa"), "ponta- grossa")

    def test_hifen_invisivel(self):
        self.assertEqual(normalizar("con\u00adsumo"), "consumo")

    def test_letras_trocadas_pelo_ocr(self):
        self.assertEqual(classificar("CEMlG C0NSUMO FATURADO 214 kWh").categoria, "conta_luz")
        self.assertRegex("cemlg", tolerante("cemig"))
        self.assertNotRegex("cemag", tolerante("cemig"))


class TestCategoriasNovas(unittest.TestCase):
    def test_cada_uma(self):
        for texto, categoria in (
            ("CONTRACHEQUE  Salario base 3.000  Liquido a receber 2.700", "holerite"),
            ("Fatura do cartao  Total da fatura 900  Pagamento minimo 150", "fatura_cartao"),
            ("Prefeitura  IPTU 2026  Inscricao imobiliaria 01.02", "impostos"),
            ("Vivo  Telefonica Brasil  Plano Fibra  telecomunicacao", "telefone_internet"),
            ("Comgas  Conta de gas canalizado  Consumo 12 m3", "conta_gas"),
        ):
            with self.subTest(categoria=categoria):
                self.assertEqual(classificar(texto).categoria, categoria)
                self.assertIn(categoria, ROTULOS)

    def test_boleto_de_verdade_continua_boleto(self):
        texto = "Boleto  Beneficiario Escola  Nosso numero 1  Linha digitavel 2379  Vencimento 10/05/2026"
        self.assertEqual(classificar(texto).categoria, "boleto")

    def test_fatura_com_linha_digitavel_nao_vira_boleto(self):
        texto = "Fatura do cartao  Total da fatura 900  Pague com boleto: linha digitavel 2609"
        self.assertEqual(classificar(texto).categoria, "fatura_cartao")


if __name__ == "__main__":
    unittest.main()
