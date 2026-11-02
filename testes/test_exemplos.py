"""Os exemplos que vao para o GitHub e para a instalacao, cada um na pasta certa.

E a demonstracao do AutoDoc: a pasta `exemplos/` inteira passa pela varredura,
como se tivesse acabado de ser copiada para a pasta vigiada, e cada documento
precisa parar onde a tabela diz. Os que dependem de OCR so sao conferidos numa
maquina com o Tesseract; sem ele, o lugar certo e `_Aguardando_OCR/`.

Os arquivos saem de `ferramentas/gerar_exemplos.py`.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from autodoc import exemplos
from autodoc.catalogo import PASTA_CATALOGO, Catalogo
from autodoc.config import Config
from autodoc.extrator import diagnostico_ocr
from autodoc.monitor import processar_pendentes
from autodoc.pipeline import Pipeline

# nome -> (pasta esperada em organizados/, precisa de OCR)
ESPERADO = {
    "conta_luz_marco_2026.pdf": ("conta_luz/2026/03", False),
    "conta_agua_fevereiro_2026_escaneada.pdf": ("conta_agua/2026/02", True),
    "conta_gas_janeiro_2026.pdf": ("conta_gas/2026/01", False),
    "internet_fibra_marco_2026.pdf": ("telefone_internet/2026/03", False),
    "boleto_mensalidade_abril_2026.pdf": ("boleto/2026/04", False),
    "fatura_cartao_marco_2026.pdf": ("fatura_cartao/2026/03", False),
    "iptu_2026.pdf": ("impostos/2026/02", False),
    "holerite_marco_2026.pdf": ("holerite/2026/03", False),
    "rg_foto_celular.jpg": ("documento_pessoal/2018/07", True),
    "cnh_digitalizada.png": ("documento_pessoal/2024/02", True),
    "comprovante_pix_print.png": ("comprovante/2026/03", True),
    "certificado_python.pdf": ("certificado/2026/03", False),
    "lista_exercicios_calculo.pdf": ("estudos/sem-data", False),
    # a pagina das assinaturas, com a data, e escaneada
    "contrato_aluguel_assinado.pdf": ("contrato/2026/01", True),
    "nota_fiscal_fone.pdf": ("nota_fiscal/2026/03", False),
    "manual_cafeteira_deitado.jpg": ("manual_tecnico/sem-data", True),
    "foto_praia.jpg": ("imagens/2025/12", True),
    "icone_app.png": ("imagens/sem-data", True),
    "conta_energia_marco.txt": ("conta_luz/2026/03", False),
    "nota_fiscal_1234.txt": ("nota_fiscal/2026/03", False),
    "comprovante_pix.txt": ("comprovante/2026/03", False),
    "contrato_aluguel.txt": ("contrato/2026/03", False),
    "scan0031_ilegivel.txt": ("_Revisar", False),
}

# Estao ali para provar que o AutoDoc nao mexe no que nao e documento solto.
INTOCADOS = ["fotos_viagem.zip", "projeto_site/estilo.css", "projeto_site/index.html", "projeto_site/logo.png"]


class BaseTemporaria(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.base = Path(self._temporaria.name).resolve()
        self.addCleanup(self._temporaria.cleanup)


class TestDemonstracao(BaseTemporaria):
    def test_cada_exemplo_vai_para_a_pasta_certa(self):
        config = Config(pasta_entrada=self.base / "entrada", pasta_saida=self.base / "organizados")
        config.preparar_pastas()
        exemplos.copiar(config.pasta_entrada)
        catalogo = Catalogo(config.pasta_saida)
        pipeline = Pipeline(config, catalogo)

        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)
        processar_pendentes(pipeline)

        onde = {p.name: p.parent.relative_to(config.pasta_saida).as_posix()
                for p in config.pasta_saida.rglob("*")
                if p.is_file() and PASTA_CATALOGO not in p.parts}
        com_ocr = diagnostico_ocr()["disponivel"]
        for nome, (esperada, precisa_de_ocr) in ESPERADO.items():
            with self.subTest(exemplo=nome):
                if precisa_de_ocr and not com_ocr:
                    esperada = "_Aguardando_OCR"
                self.assertEqual(onde.get(nome), esperada)
        for nome in INTOCADOS:
            with self.subTest(intocado=nome):
                self.assertTrue((config.pasta_entrada / nome).exists())

    def test_todo_exemplo_tem_lugar_na_tabela(self):
        na_pasta = {p.name for p in exemplos.PASTA_EXEMPLOS.iterdir()
                    if p.is_file() and p.name not in exemplos.FORA_DA_COPIA}
        self.assertEqual(na_pasta - set(ESPERADO), {"fotos_viagem.zip"})


class TestCopia(BaseTemporaria):
    def setUp(self):
        super().setUp()
        self.origem = self.base / "exemplos"
        (self.origem / "projeto").mkdir(parents=True)
        (self.origem / "projeto" / "index.html").write_text("x", encoding="utf-8")
        (self.origem / "conta.pdf").write_bytes(b"%PDF")
        (self.origem / "LEIA-ME.md").write_text("leia", encoding="utf-8")
        (self.origem / ".DS_Store").write_bytes(b"x")
        self.destino = self.base / "entrada"

    def test_copia_arquivos_e_pastas_mas_nao_o_leia_me(self):
        copiados = exemplos.copiar(self.destino, self.origem)
        self.assertEqual(sorted(c.name for c in copiados), ["conta.pdf", "projeto"])
        self.assertTrue((self.destino / "projeto" / "index.html").exists())

    def test_nao_sobrescreve_o_que_ja_esta_la(self):
        self.destino.mkdir()
        (self.destino / "conta.pdf").write_bytes(b"meu")
        exemplos.copiar(self.destino, self.origem)
        self.assertEqual((self.destino / "conta.pdf").read_bytes(), b"meu")

    def test_sem_a_pasta_de_exemplos_nao_copia_nada(self):
        self.assertEqual(exemplos.copiar(self.destino, self.base / "nao-existe"), [])

    def test_na_instalacao_copia_uma_vez_so(self):
        saida = self.base / "organizados"
        primeira = exemplos.copiar_na_instalacao(self.destino, saida, self.origem)
        self.assertEqual(len(primeira), 2)
        shutil.rmtree(self.destino)  # o AutoDoc ja organizou tudo
        self.assertIsNone(exemplos.copiar_na_instalacao(self.destino, saida, self.origem))
        self.assertFalse(self.destino.exists())


if __name__ == "__main__":
    unittest.main()
