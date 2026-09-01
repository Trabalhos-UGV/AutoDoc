"""A pasta organizada e a verdade; o catalogo se acerta com ela.

E o que substitui o banco de dados. Se estes testes passam, apagar o catalogo
nao perde nada e apagar um arquivo no Finder tem o efeito que se espera.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from autodoc.catalogo import PASTA_CATALOGO, PASTA_DUPLICADOS, Catalogo
from autodoc.classificador import NAO_CLASSIFICADO
from autodoc.config import Config
from autodoc.pipeline import Pipeline

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class BaseReconciliacao(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        base = Path(self._temporaria.name)
        self.config = Config(pasta_entrada=base / "entrada",
                             pasta_saida=base / "organizados")
        self.config.preparar_pastas()
        self.catalogo = Catalogo(self.config.pasta_saida)
        self.pipeline = Pipeline(self.config, self.catalogo)
        self.addCleanup(self._temporaria.cleanup)

    def arquivar_exemplos(self) -> None:
        for exemplo in sorted(EXEMPLOS.glob("*.txt")):
            shutil.copy2(exemplo, self.config.pasta_entrada / exemplo.name)
            self.pipeline.processar(self.config.pasta_entrada / exemplo.name)

    def nomes(self, catalogo=None) -> list[str]:
        alvo = catalogo or self.catalogo
        return sorted(linha["arquivo"] for linha in alvo.listar())


class TestCatalogoApagado(BaseReconciliacao):
    def test_catalogo_apagado_e_remontado_pela_pasta(self):
        self.arquivar_exemplos()
        esperados = self.nomes()
        self.assertEqual(len(esperados), 5)

        shutil.rmtree(self.config.pasta_saida / PASTA_CATALOGO)

        novo = Catalogo(self.config.pasta_saida)
        self.assertEqual(len(novo), 0, "sem o caderno o catalogo nasce vazio")
        novo.reconciliar(self.pipeline.analisar)
        self.assertEqual(self.nomes(novo), esperados)

    def test_remontado_mantem_a_categoria_que_a_pasta_declara(self):
        self.arquivar_exemplos()
        antes = self.catalogo.contar_por_categoria()

        shutil.rmtree(self.config.pasta_saida / PASTA_CATALOGO)
        novo = Catalogo(self.config.pasta_saida)
        novo.reconciliar(self.pipeline.analisar)

        self.assertEqual(novo.contar_por_categoria(), antes)

    def test_remontado_continua_pesquisavel(self):
        self.arquivar_exemplos()
        shutil.rmtree(self.config.pasta_saida / PASTA_CATALOGO)
        novo = Catalogo(self.config.pasta_saida)
        novo.reconciliar(self.pipeline.analisar)

        achados = [l["arquivo"] for l in novo.buscar("kwh")]
        self.assertEqual(achados, ["conta_energia_marco.txt"])


class TestArquivoApagado(BaseReconciliacao):
    def test_arquivo_apagado_some_do_catalogo(self):
        self.arquivar_exemplos()
        alvo = self.catalogo.caminho_de(self.catalogo.por_id(1))
        alvo.unlink()

        resumo = self.catalogo.reconciliar(self.pipeline.analisar)
        self.assertEqual(resumo["descartadas"], 1)
        self.assertEqual(len(self.catalogo), 4)

    def test_ficha_descartada_nao_volta_ao_recarregar(self):
        self.arquivar_exemplos()
        self.catalogo.caminho_de(self.catalogo.por_id(1)).unlink()
        self.catalogo.reconciliar(self.pipeline.analisar)

        self.assertEqual(len(Catalogo(self.config.pasta_saida)), 4)

    def test_documento_apagado_sai_da_busca(self):
        self.arquivar_exemplos()
        conta = next(l for l in self.catalogo.listar() if "energia" in l["arquivo"])
        Path(conta["caminho"]).unlink()
        self.catalogo.reconciliar(self.pipeline.analisar)

        self.assertEqual(self.catalogo.buscar("kwh"), [])


class TestArquivoColocadoAMao(BaseReconciliacao):
    """Arrastar um arquivo direto para a pasta organizada tem que funcionar."""

    def test_arquivo_solto_e_fichado_onde_esta(self):
        destino = self.config.pasta_saida / "contrato" / "2026" / "03"
        destino.mkdir(parents=True)
        shutil.copy2(EXEMPLOS / "contrato_aluguel.txt", destino)

        self.catalogo.reconciliar(self.pipeline.analisar)

        self.assertEqual(self.nomes(), ["contrato_aluguel.txt"])
        self.assertTrue((destino / "contrato_aluguel.txt").exists(),
                        "o arquivo nao pode ter sido movido")

    def test_a_pasta_manda_na_categoria(self):
        """Quem pos o arquivo em contrato/ disse que e contrato."""
        destino = self.config.pasta_saida / "contrato" / "2026" / "03"
        destino.mkdir(parents=True)
        # um documento que o classificador chamaria de conta de luz
        shutil.copy2(EXEMPLOS / "conta_energia_marco.txt", destino)

        self.catalogo.reconciliar(self.pipeline.analisar)
        self.assertEqual(self.catalogo.por_id(1).categoria, "contrato")

    def test_arquivo_em_revisar_vira_nao_classificado(self):
        destino = self.config.pasta_saida / "_Revisar"
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXEMPLOS / "conta_energia_marco.txt", destino)

        self.catalogo.reconciliar(self.pipeline.analisar)
        self.assertEqual(self.catalogo.por_id(1).categoria, NAO_CLASSIFICADO)

    def test_duplicados_ficam_de_fora_da_varredura(self):
        pasta = self.config.pasta_saida / PASTA_DUPLICADOS
        pasta.mkdir(parents=True)
        shutil.copy2(EXEMPLOS / "conta_energia_marco.txt", pasta)

        self.catalogo.reconciliar(self.pipeline.analisar)
        self.assertEqual(len(self.catalogo), 0)


class TestReconciliacaoRepetida(BaseReconciliacao):
    def test_rodar_de_novo_nao_muda_nada(self):
        self.arquivar_exemplos()
        self.assertEqual(self.catalogo.reconciliar(self.pipeline.analisar),
                         {"descartadas": 0, "recuperadas": 0})

    def test_catalogo_vazio_e_pasta_vazia(self):
        self.assertEqual(self.catalogo.reconciliar(self.pipeline.analisar),
                         {"descartadas": 0, "recuperadas": 0})


if __name__ == "__main__":
    unittest.main()
