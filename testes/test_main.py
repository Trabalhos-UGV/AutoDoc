"""A interface de linha de comando — `python main.py ...`.

É o que o README documenta e o que o atalho do sistema chama, e até aqui não
tinha uma linha testada.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from autodoc import __version__
from autodoc import config as modulo_config
from autodoc.catalogo import Catalogo
from autodoc.config import Config
from autodoc.pipeline import Pipeline
from autodoc.web.servidor import PORTA_PADRAO

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class TestParser(unittest.TestCase):
    def setUp(self):
        self.parser = main.montar_parser()

    def test_os_quatro_subcomandos_existem(self):
        # `buscar` é o único que exige argumento próprio.
        for argumentos in (["app"], ["monitorar"], ["buscar", "luz"], ["listar"]):
            with self.subTest(comando=argumentos[0]):
                self.assertEqual(
                    self.parser.parse_args(argumentos).comando, argumentos[0])

    def test_app_usa_a_porta_padrao(self):
        self.assertEqual(self.parser.parse_args(["app"]).porta, PORTA_PADRAO)

    def test_porta_pode_ser_trocada(self):
        self.assertEqual(self.parser.parse_args(["app", "--porta", "9000"]).porta, 9000)

    def test_buscar_exige_o_termo(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.parser.parse_args(["buscar"])

    def test_limite_padrao_de_buscar_e_listar(self):
        self.assertEqual(self.parser.parse_args(["buscar", "luz"]).limite, 20)
        self.assertEqual(self.parser.parse_args(["listar"]).limite, 20)

    def test_sem_comando_nenhum(self):
        self.assertIsNone(self.parser.parse_args([]).comando)

    def test_versao(self):
        saida = io.StringIO()
        with self.assertRaises(SystemExit) as saiu, contextlib.redirect_stdout(saida):
            self.parser.parse_args(["--versao"])
        self.assertEqual(saiu.exception.code, 0)
        self.assertEqual(saida.getvalue().strip(), f"AutoDoc {__version__}")

    def test_comando_inventado(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.parser.parse_args(["inventado"])


class TestImprimir(unittest.TestCase):
    def capturar(self, linhas) -> str:
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            main.imprimir(linhas)
        return saida.getvalue()

    def test_lista_vazia_diz_que_nao_achou(self):
        self.assertIn("nenhum documento encontrado", self.capturar([]))

    def test_mostra_id_data_categoria_arquivo_e_caminho(self):
        saida = self.capturar([{
            "id": 7, "data_documento": "2026-03-12", "categoria": "conta_luz",
            "arquivo": "conta.txt", "caminho": "/casa/organizados/conta_luz/conta.txt",
        }])
        for pedaco in ("7", "2026-03-12", "conta_luz", "conta.txt",
                       "/casa/organizados/conta_luz/conta.txt"):
            self.assertIn(pedaco, saida)

    def test_documento_sem_data(self):
        saida = self.capturar([{
            "id": 1, "data_documento": None, "categoria": "nao_classificado",
            "arquivo": "scan.txt", "caminho": "/casa/_Revisar/scan.txt",
        }])
        self.assertIn("sem data", saida)


class BaseCLI(unittest.TestCase):
    """Um AutoDoc montado numa pasta temporária, com o config apontado para lá."""

    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        base = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)

        self.config_json = base / "config.json"
        Config(pasta_entrada=base / "entrada",
               pasta_saida=base / "organizados").salvar(self.config_json)
        # Nenhum teste do CLI pode ler nem escrever o config.json de verdade.
        self.enterContext(mock.patch.object(
            modulo_config, "CAMINHO_CONFIG", self.config_json))

        # `main()` liga o log no nível INFO para o processo inteiro; num teste
        # isso só despeja linha na saída da suíte.
        self.enterContext(mock.patch.object(main.logging, "basicConfig"))
        self.enterContext(mock.patch.object(
            main.logging.getLogger(), "level", main.logging.CRITICAL))

        self.config = Config.carregar(self.config_json)
        self.config.preparar_pastas()

    def arquivar_exemplos(self) -> None:
        catalogo = Catalogo(self.config.pasta_saida)
        pipeline = Pipeline(self.config, catalogo)
        for exemplo in sorted(EXEMPLOS.glob("*.txt")):
            shutil.copy2(exemplo, self.config.pasta_entrada / exemplo.name)
            pipeline.processar(self.config.pasta_entrada / exemplo.name)

    def rodar(self, argumentos) -> tuple[int, str]:
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = main.main(argumentos)
        return codigo, saida.getvalue()


class TestListarEBuscar(BaseCLI):
    def setUp(self):
        super().setUp()
        self.arquivar_exemplos()

    def test_listar_mostra_os_documentos(self):
        codigo, saida = self.rodar(["listar"])
        self.assertEqual(codigo, 0)
        self.assertIn("conta_energia_marco.txt", saida)
        self.assertIn("nota_fiscal_1234.txt", saida)

    def test_listar_respeita_o_limite(self):
        _, saida = self.rodar(["listar", "--limite", "2"])
        # duas linhas por documento: a do resumo e a do caminho
        self.assertEqual(len([l for l in saida.splitlines() if l.startswith("[")]), 2)

    def test_buscar_pelo_conteudo(self):
        codigo, saida = self.rodar(["buscar", "kwh"])
        self.assertEqual(codigo, 0)
        self.assertIn("conta_energia_marco.txt", saida)
        self.assertNotIn("nota_fiscal_1234.txt", saida)

    def test_buscar_sem_acento_acha_com_acento(self):
        _, saida = self.rodar(["buscar", "marc"])
        self.assertIn("conta_energia_marco.txt", saida)

    def test_buscar_sem_resultado(self):
        _, saida = self.rodar(["buscar", "bicicleta"])
        self.assertIn("nenhum documento encontrado", saida)

    def test_o_catalogo_e_remontado_da_pasta(self):
        """Sem banco: o CLI abre lendo as pastas, e não um arquivo de banco."""
        shutil.rmtree(self.config.pasta_saida / ".autodoc")
        _, saida = self.rodar(["listar"])
        self.assertIn("conta_energia_marco.txt", saida)


class TestMonitorarPeloCLI(BaseCLI):
    def test_processa_pendentes_e_entra_no_laco(self):
        with mock.patch.object(main, "processar_pendentes", return_value=3) as pendentes, \
             mock.patch.object(main, "monitorar") as monitorar:
            codigo, saida = self.rodar(["monitorar"])

        self.assertEqual(codigo, 0)
        self.assertIn("3 documento(s) pendente(s)", saida)
        pendentes.assert_called_once()
        monitorar.assert_called_once()

    def test_sem_pendentes_nao_anuncia_nada(self):
        with mock.patch.object(main, "processar_pendentes", return_value=0), \
             mock.patch.object(main, "monitorar"):
            _, saida = self.rodar(["monitorar"])
        self.assertNotIn("pendente", saida)


class TestAbrirAplicativo(BaseCLI):
    def test_sem_comando_nenhum_abre_o_app(self):
        with mock.patch.object(main, "abrir_aplicativo", return_value=0) as abrir:
            self.assertEqual(self.rodar([])[0], 0)
        abrir.assert_called_once()

    def test_sobe_o_servidor_e_abre_a_janela(self):
        with mock.patch.object(main.janela, "abrir", return_value="nativa") as abrir:
            codigo, saida = self.rodar(["app", "--porta", "8931"])

        self.assertEqual(codigo, 0)
        self.assertIn("monitorando", saida)
        abrir.assert_called_once()
        self.assertTrue(abrir.call_args.args[0].startswith("http://127.0.0.1:"))

    def test_o_servidor_para_mesmo_se_a_janela_quebrar(self):
        """O `finally` existe para isso: sem ele o processo ficaria vivo em segundo plano."""
        catalogo = Catalogo(self.config.pasta_saida)
        servidor = mock.Mock()
        servidor.iniciar.return_value = "http://127.0.0.1:8757/"

        with mock.patch.object(main, "Servidor", return_value=servidor), \
             mock.patch.object(main.janela, "abrir", side_effect=RuntimeError("janela morreu")), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                main.abrir_aplicativo(self.config, catalogo, 8757)

        servidor.parar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
