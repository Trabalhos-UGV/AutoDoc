"""Classificacao: as categorias, a confianca e o limiar."""

from __future__ import annotations

import unittest
from pathlib import Path

from autodoc.classificador import (
    LIMIAR,
    NAO_CLASSIFICADO,
    classificar,
    normalizar,
    pontuar,
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
        self.assertIn("limiar", resultado.regra)

    def test_confianca_nunca_chega_a_certeza_absoluta(self):
        texto = (EXEMPLOS / "nota_fiscal_1234.txt").read_text(encoding="utf-8")
        self.assertLess(classificar(texto).confianca, 1.0)


class TestFronteiraDePalavra(unittest.TestCase):
    def test_agua_nao_casa_dentro_de_aguardando(self):
        self.assertNotIn("conta_agua", pontuar("aguardando pagamento"))


if __name__ == "__main__":
    unittest.main()
