"""Configuracao: os padroes, a pasta de saida e a gravacao da escolha."""

from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from autodoc import config as modulo_config
from autodoc.config import RAIZ, Config, problema_da_pasta


class BaseConfig(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporaria.name)
        self.arquivo = self.pasta / "config.json"
        self.addCleanup(self._temporaria.cleanup)

    def escrever(self, dados: dict) -> Path:
        self.arquivo.write_text(json.dumps(dados), encoding="utf-8")
        return self.arquivo


class TestPadroes(BaseConfig):
    def test_saida_nasce_ao_lado_da_entrada(self):
        config = Config(pasta_entrada=Path("/tmp/Meus/entrada"))
        self.assertEqual(config.pasta_saida, Path("/tmp/Meus/organizados"))

    def test_padrao_fica_fora_do_repositorio(self):
        """Programa instalado nao despeja arquivo no meio do proprio codigo."""
        config = Config()
        raiz = Path(__file__).resolve().parent.parent
        self.assertFalse(str(config.pasta_entrada).startswith(str(raiz)))

    def test_til_e_expandido(self):
        config = Config(pasta_entrada=Path("~/Docs/entrada"))
        self.assertFalse(str(config.pasta_entrada).startswith("~"))

    def test_sem_arquivo_usa_os_padroes(self):
        config = Config.carregar(self.pasta / "nao-existe.json")
        self.assertEqual(config.pasta_entrada, Config().pasta_entrada)


class TestPastaDeDocumentos(BaseConfig):
    def test_usa_o_nome_que_a_pasta_tem_neste_sistema(self):
        from autodoc.config import pasta_documentos

        self.assertIn(pasta_documentos().name,
                      {"Documentos", "Documents", Path.home().name})

    def test_sem_pasta_de_documentos_cai_na_casa(self):
        """Um sistema em outro idioma, ou uma conta recém-criada."""
        from autodoc import config as modulo

        with mock.patch.object(modulo.Path, "is_dir", return_value=False):
            self.assertEqual(modulo.pasta_documentos(), Path.home())


class TestLeitura(BaseConfig):
    def test_le_os_caminhos_escolhidos(self):
        config = Config.carregar(self.escrever({
            "pasta_entrada": "/a/entrada", "pasta_saida": "/b/organizados"}))
        self.assertEqual(config.pasta_entrada, Path("/a/entrada"))
        self.assertEqual(config.pasta_saida, Path("/b/organizados"))

    def test_saida_omitida_acompanha_a_entrada(self):
        config = Config.carregar(self.escrever({"pasta_entrada": "/a/entrada"}))
        self.assertEqual(config.pasta_saida, Path("/a/organizados"))

    def test_config_antigo_com_banco_ainda_carrega(self):
        """Nao ha mais banco; recusar o arquivo por causa dele seria pior."""
        config = Config.carregar(self.escrever({
            "pasta_entrada": "/a/entrada", "banco": "/velho/autodoc.db"}))
        self.assertEqual(config.pasta_entrada, Path("/a/entrada"))
        self.assertFalse(hasattr(config, "banco"))

    def test_config_quebrado_nao_impede_o_programa_de_abrir(self):
        self.arquivo.write_text("{ isto nao e json", encoding="utf-8")
        self.assertEqual(Config.carregar(self.arquivo).pasta_entrada,
                         Config().pasta_entrada)

    def test_extensoes_viram_minusculas(self):
        config = Config.carregar(self.escrever({"extensoes": [".PDF", ".Txt"]}))
        self.assertEqual(config.extensoes, (".pdf", ".txt"))


class TestPastaQueNaoPodeSerVigiada(BaseConfig):
    """O AutoDoc leva embora tudo o que aparece na pasta vigiada."""

    def test_pasta_do_programa_e_recusada(self):
        self.assertIn("próprio AutoDoc", problema_da_pasta(RAIZ / "exemplos"))
        self.assertIn("próprio AutoDoc", problema_da_pasta(RAIZ))

    def test_casa_e_o_que_esta_acima_dela_sao_recusados(self):
        self.assertIn("pessoal", problema_da_pasta(Path.home()))
        self.assertIn("pessoal", problema_da_pasta(Path.home().parent))

    def test_documentos_inteira_e_recusada_mas_subpasta_nao(self):
        documentos = modulo_config.pasta_documentos()
        with mock.patch.object(modulo_config, "pasta_documentos",
                               return_value=self.pasta / "Documentos"):
            self.assertIn("Documentos", problema_da_pasta(self.pasta / "Documentos"))
            self.assertIsNone(problema_da_pasta(self.pasta / "Documentos" / "Contas"))
        self.assertIsNone(problema_da_pasta(documentos / "AutoDoc" / "entrada"))

    def test_config_gravado_com_a_pasta_do_programa_volta_ao_padrao(self):
        """O defeito desta maquina: o app esvaziava `exemplos/` a cada abertura."""
        arquivo = self.escrever({
            "pasta_entrada": str(RAIZ / "exemplos"),
            "pasta_saida": str(RAIZ / "organizados")})
        with self.assertLogs("autodoc.config", "WARNING"):
            config = Config.carregar(arquivo)

        self.assertEqual(config.pasta_entrada, Config().pasta_entrada)
        self.assertEqual(config.pasta_saida, config.saida_ao_lado())
        # o arquivo nao e reescrito: quem decide a pasta e o instalador
        self.assertIn("exemplos", arquivo.read_text(encoding="utf-8"))


class TestGravacao(BaseConfig):
    def test_salvar_e_carregar_dao_a_volta(self):
        original = Config(pasta_entrada=self.pasta / "entrada",
                          pasta_saida=self.pasta / "saida")
        original.salvar(self.arquivo)

        relido = Config.carregar(self.arquivo)
        self.assertEqual(relido.pasta_entrada, original.pasta_entrada)
        self.assertEqual(relido.pasta_saida, original.pasta_saida)

    def test_o_gravado_nao_tem_banco(self):
        Config().salvar(self.arquivo)
        self.assertNotIn("banco", json.loads(self.arquivo.read_text(encoding="utf-8")))

    def test_preparar_pastas_cria_as_tres(self):
        config = Config(pasta_entrada=self.pasta / "e",
                        pasta_saida=self.pasta / "s",
                        pasta_backup=self.pasta / "b")
        config.preparar_pastas()
        for pasta in (config.pasta_entrada, config.pasta_saida, config.pasta_backup):
            self.assertTrue(pasta.is_dir())

    def test_preparar_pastas_roda_duas_vezes(self):
        config = Config(pasta_entrada=self.pasta / "e")
        config.preparar_pastas()
        config.preparar_pastas()  # nao pode levantar


if __name__ == "__main__":
    unittest.main()
