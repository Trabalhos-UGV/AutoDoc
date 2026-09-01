"""O caminho completo de um documento: da pasta de entrada ao arquivo."""

from __future__ import annotations

import logging
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from autodoc import pipeline as pipeline_modulo
from autodoc.catalogo import PASTA_DUPLICADOS, PASTA_REVISAO, Catalogo
from autodoc.classificador import NAO_CLASSIFICADO
from autodoc.config import Config
from autodoc.pipeline import Pipeline

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class BasePipeline(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        base = Path(self._temporaria.name)
        self.base = base
        self.config = Config(pasta_entrada=base / "entrada",
                             pasta_saida=base / "organizados")
        self.config.preparar_pastas()
        self.catalogo = Catalogo(self.config.pasta_saida)
        self.pipeline = Pipeline(self.config, self.catalogo)
        self.addCleanup(self._temporaria.cleanup)

    def largar(self, origem: Path, nome: str | None = None) -> Path:
        """Copia um arquivo para a pasta monitorada, como o usuario faria."""
        destino = self.config.pasta_entrada / (nome or origem.name)
        shutil.copy2(origem, destino)
        return destino

    def largar_exemplo(self, nome: str, como: str | None = None) -> Path:
        return self.largar(EXEMPLOS / nome, como)

    @property
    def entrada_vazia(self) -> bool:
        return not any(self.config.pasta_entrada.iterdir())


class TestArquivamento(BasePipeline):
    def test_conta_de_luz_vai_para_categoria_ano_e_mes(self):
        resultado = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt"))

        self.assertEqual(resultado.categoria, "conta_luz")
        self.assertEqual(
            resultado.destino.relative_to(self.config.pasta_saida),
            Path("conta_luz/2026/03/conta_energia_marco.txt"),
        )
        self.assertTrue(resultado.destino.exists())

    def test_o_arquivo_sai_da_pasta_de_entrada(self):
        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))
        self.assertTrue(self.entrada_vazia)

    def test_documento_duvidoso_vai_para_revisao(self):
        resultado = self.pipeline.processar(
            self.largar_exemplo("scan0031_ilegivel.txt"))

        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertEqual(resultado.destino.parent.name, PASTA_REVISAO)

    def test_revisao_nao_separa_por_ano(self):
        """E uma pilha para alguem olhar, nao um arquivo morto."""
        resultado = self.pipeline.processar(
            self.largar_exemplo("scan0031_ilegivel.txt"))
        self.assertEqual(resultado.destino.parent,
                         self.config.pasta_saida / PASTA_REVISAO)

    def test_nome_repetido_na_mesma_pasta_nao_sobrescreve(self):
        """Duas contas diferentes, mesmo nome, mesmo mes: nenhuma se perde."""
        primeiro = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt"))

        # outra conta de luz, do mesmo mes, com o mesmo nome de arquivo
        outra = self.config.pasta_entrada / "conta_energia_marco.txt"
        outra.write_text(
            "COPEL DISTRIBUICAO\nCONTA DE ENERGIA ELETRICA\n"
            "Consumo faturado: 92 kWh\nBandeira tarifaria: verde\n"
            "VENCIMENTO 20/03/2026\nTOTAL A PAGAR R$ 98,10\n",
            encoding="utf-8")
        segundo = self.pipeline.processar(outra)

        self.assertEqual(segundo.categoria, "conta_luz")
        self.assertEqual(segundo.destino.parent, primeiro.destino.parent)
        self.assertEqual(segundo.destino.name, "conta_energia_marco (2).txt")
        self.assertTrue(primeiro.destino.exists(), "o primeiro nao pode ter sumido")

    def test_extensao_fora_da_lista_e_ignorada(self):
        alvo = self.config.pasta_entrada / "planilha.xlsx"
        alvo.write_text("qualquer coisa", encoding="utf-8")

        resultado = self.pipeline.processar(alvo)
        self.assertFalse(resultado.sucesso)
        self.assertTrue(alvo.exists(), "o que nao e monitorado fica onde esta")


class TestTodosOsExemplos(BasePipeline):
    def test_os_cinco_exemplos_terminam_onde_devem(self):
        esperado = {
            "conta_energia_marco.txt": "conta_luz/2026/03",
            "nota_fiscal_1234.txt": "nota_fiscal/2026/03",
            "contrato_aluguel.txt": "contrato/2026/03",
            "comprovante_pix.txt": "comprovante/2026/03",
            "scan0031_ilegivel.txt": PASTA_REVISAO,
        }
        for nome, pasta in esperado.items():
            with self.subTest(arquivo=nome):
                resultado = self.pipeline.processar(self.largar_exemplo(nome))
                self.assertEqual(
                    str(resultado.destino.parent.relative_to(self.config.pasta_saida)),
                    pasta,
                )

        self.assertEqual(len(self.catalogo), 5)
        self.assertTrue(self.entrada_vazia)


class TestDeduplicacao(BasePipeline):
    def setUp(self):
        super().setUp()
        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))

    def test_mesmo_conteudo_com_outro_nome_nao_e_indexado_de_novo(self):
        resultado = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt", "conta (copia).txt"))

        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.ignorado, "ja indexado")
        self.assertEqual(len(self.catalogo), 1)

    def test_a_copia_sai_da_pasta_de_entrada(self):
        """Deixada ali, seria reexaminada a cada abertura do programa."""
        self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt", "conta (copia).txt"))

        self.assertTrue(self.entrada_vazia)
        self.assertEqual(
            [p.name for p in (self.config.pasta_saida / PASTA_DUPLICADOS).iterdir()],
            ["conta (copia).txt"],
        )

    def test_a_copia_nao_e_apagada(self):
        """Arquivo de quem usa nao se apaga, se põe de lado."""
        self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt", "conta (copia).txt"))
        guardada = self.config.pasta_saida / PASTA_DUPLICADOS / "conta (copia).txt"
        self.assertTrue(guardada.exists())


class TestExplicacao(BasePipeline):
    """O trajeto do arquivo e o que permite discordar do sistema."""

    def setUp(self):
        super().setUp()
        self.resultado = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt"))
        self.ficha = self.resultado.documento

    def test_o_trajeto_tem_as_cinco_etapas(self):
        titulos = [etapa["titulo"] for etapa in self.ficha.etapas]
        self.assertEqual(titulos, ["Detecção", "Extração de texto",
                                   "Classificação", "Data", "Arquivamento"])

    def test_guarda_a_regra_e_as_palavras_chave(self):
        self.assertIn("conta_luz", self.ficha.regra)
        self.assertIn("kWh", self.ficha.palavras_chave)

    def test_guarda_o_trecho_lido(self):
        self.assertTrue(self.ficha.trecho)
        self.assertLessEqual(len(self.ficha.trecho), 221)

    def test_guarda_a_origem_do_texto(self):
        self.assertEqual(self.ficha.origem, "arquivo de texto")

    def test_a_data_vem_do_rotulo_de_vencimento(self):
        self.assertEqual(self.ficha.data_documento, "2026-03-12")
        self.assertIn("vencimento", self.ficha.etapas[3]["detalhe"])


class TestCorrecaoManual(BasePipeline):
    def setUp(self):
        super().setUp()
        self.pipeline.processar(self.largar_exemplo("scan0031_ilegivel.txt"))
        self.ficha = self.catalogo.por_id(1)

    def test_corrigir_move_o_arquivo_para_a_categoria_nova(self):
        corrigida = self.pipeline.reclassificar(self.ficha, "contrato")

        self.assertEqual(corrigida.categoria, "contrato")
        self.assertTrue(self.catalogo.caminho_de(corrigida).exists())
        self.assertFalse(any((self.config.pasta_saida / PASTA_REVISAO).iterdir()))

    def test_corrigir_registra_que_foi_decisao_humana(self):
        corrigida = self.pipeline.reclassificar(self.ficha, "contrato")

        self.assertEqual(corrigida.confianca, 1.0)
        self.assertIn("a mao", corrigida.regra)
        self.assertEqual(corrigida.etapas[-1]["titulo"], "Correção manual")

    def test_correcao_sobrevive_ao_fechamento(self):
        self.pipeline.reclassificar(self.ficha, "contrato")
        relido = Catalogo(self.config.pasta_saida)
        self.assertEqual(relido.por_id(1).categoria, "contrato")

    def test_categoria_inventada_e_recusada(self):
        with self.assertRaises(ValueError):
            self.pipeline.reclassificar(self.ficha, "categoria_que_nao_existe")


class TestBackup(BasePipeline):
    def test_copia_para_a_pasta_de_backup(self):
        self.config.pasta_backup = self.base / "drive"
        self.config.preparar_pastas()

        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))
        self.assertTrue(
            (self.config.pasta_backup / "conta_luz" / "conta_energia_marco.txt").exists())

    def test_backup_indisponivel_nao_impede_o_arquivamento(self):
        self.config.pasta_backup = Path("/proc/nao/existe")

        with self.assertLogs("autodoc.pipeline", "WARNING"):
            resultado = self.pipeline.processar(
                self.largar_exemplo("conta_energia_marco.txt"))

        self.assertTrue(resultado.sucesso)
        self.assertTrue(resultado.destino.exists())


class TestFormatacao(unittest.TestCase):
    """Números que vão para a tela, e por isso são lidos por gente."""

    def test_tamanho_em_bytes_kilobytes_e_megabytes(self):
        from autodoc.pipeline import _formatar_tamanho

        self.assertEqual(_formatar_tamanho(512), "512 B")
        self.assertEqual(_formatar_tamanho(1023), "1023 B")
        self.assertEqual(_formatar_tamanho(2048), "2 KB")
        self.assertEqual(_formatar_tamanho(3 * 1024 * 1024), "3,0 MB")

    def test_o_tamanho_usa_virgula_como_se_escreve_em_portugues(self):
        from autodoc.pipeline import _formatar_tamanho

        self.assertIn(",", _formatar_tamanho(int(1.5 * 1024 * 1024)))

    def test_trecho_curto_sai_inteiro(self):
        from autodoc.pipeline import _trecho

        self.assertEqual(_trecho("conta de luz"), "conta de luz")

    def test_trecho_junta_os_espacos(self):
        from autodoc.pipeline import _trecho

        self.assertEqual(_trecho("conta   de\n\n luz"), "conta de luz")

    def test_trecho_comprido_e_cortado_numa_palavra_inteira(self):
        from autodoc.pipeline import TAMANHO_TRECHO, _trecho

        cortado = _trecho("palavra " * 100)
        self.assertTrue(cortado.endswith("…"))
        self.assertLessEqual(len(cortado), TAMANHO_TRECHO + 1)
        self.assertNotIn("palavr…", cortado, "não pode cortar no meio da palavra")


class TestDocumentoSemData(BasePipeline):
    def test_vai_para_sem_data(self):
        """Nem o texto nem o arquivo deram data: o documento não some."""
        alvo = self.config.pasta_entrada / "contrato_sem_data.txt"
        alvo.write_text("CONTRATO DE LOCACAO\nCLAUSULA PRIMEIRA\nLOCADOR\n"
                        "LOCATARIO\nForo da comarca", encoding="utf-8")

        with mock.patch.object(pipeline_modulo.Pipeline, "_resolver_data",
                               return_value=(None, "nenhuma data encontrada")):
            resultado = self.pipeline.processar(alvo)

        self.assertEqual(resultado.destino.parent.name, "sem-data")
        self.assertTrue(resultado.destino.exists())


class TestCaminhoRelativo(BasePipeline):
    def test_destino_fora_da_pasta_de_saida_sai_absoluto(self):
        """Pode acontecer se alguém trocar a pasta de saída com documentos já fichados."""
        fora = self.base / "outro" / "lugar" / "arquivo.txt"
        self.assertEqual(self.pipeline._relativo(fora), str(fora.parent) + "/")


class TestFalhasAoMover(BasePipeline):
    def test_recolher_que_falha_devolve_nada_sem_derrubar(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")

        with mock.patch.object(pipeline_modulo.shutil, "move",
                               side_effect=OSError("disco cheio")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            self.assertIsNone(self.pipeline._recolher(alvo, "_Duplicados"))

    def test_arquivo_ilegivel_no_hash_e_avisado(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")

        with mock.patch.object(pipeline_modulo, "hash_arquivo",
                               side_effect=OSError("sem permissao")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            resultado = self.pipeline.processar(alvo)

        self.assertFalse(resultado.sucesso)
        self.assertIn("ilegivel", resultado.ignorado)

    def test_corrigir_documento_cujo_arquivo_sumiu(self):
        """Alguém apagou no Finder entre a tela carregar e o clique."""
        self.pipeline.processar(self.largar_exemplo("scan0031_ilegivel.txt"))
        ficha = self.catalogo.por_id(1)
        self.catalogo.caminho_de(ficha).unlink()

        with self.assertLogs("autodoc.pipeline", "WARNING"):
            corrigida = self.pipeline.reclassificar(ficha, "contrato")

        # a ficha acompanha a decisão mesmo sem o arquivo
        self.assertEqual(corrigida.categoria, "contrato")


class TestAnalisar(BasePipeline):
    """A releitura que a reconciliação usa — sem mover nada."""

    def test_le_e_classifica_sem_mover(self):
        destino = self.config.pasta_saida / "conta_luz" / "2026" / "03"
        destino.mkdir(parents=True)
        alvo = destino / "conta_energia_marco.txt"
        alvo.write_text((EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8"),
                        encoding="utf-8")

        ficha = self.pipeline.analisar(alvo)

        self.assertEqual(ficha.categoria, "conta_luz")
        self.assertTrue(alvo.exists(), "não pode ter sido movido")
        self.assertEqual(ficha.etapas[0]["titulo"], "Releitura")

    def test_arquivo_ilegivel_vira_ficha_com_o_motivo(self):
        alvo = self.config.pasta_saida / "quebrado.pdf"
        alvo.write_bytes(b"isto nao e um PDF")

        # o pypdf reclama no log dele ao ver o arquivo torto; é o esperado aqui
        pypdf = logging.getLogger("pypdf")
        nivel = pypdf.level
        pypdf.setLevel(logging.CRITICAL)
        self.addCleanup(pypdf.setLevel, nivel)

        with self.assertLogs("autodoc.pipeline", "WARNING"):
            ficha = self.pipeline.analisar(alvo)

        self.assertEqual(ficha.texto, "")
        self.assertIn("nao foi possivel ler", ficha.origem)


if __name__ == "__main__":
    unittest.main()
