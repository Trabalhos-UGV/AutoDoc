"""As etapas da instalacao — e a pasta escolhida chegando ao config.json.

Este arquivo existe por causa de um defeito concreto: escolher outra pasta no
instalador mudava so o texto da tela, e o AutoDoc subia vigiando a pasta
anterior. A janela abria vazia e nao havia como saber por que.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc import config as modulo_config
from autodoc.catalogo import PASTA_CATALOGO, Catalogo
from autodoc.config import Config
from autodoc.instalacao import atalho, instalador


class BaseInstalacao(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.base = Path(self._temporaria.name)
        self.config_json = self.base / "config.json"
        self.escolhida = self.base / "MinhaPasta" / "entrada"
        self.addCleanup(self._temporaria.cleanup)

        # Nenhum teste pode escrever no config.json de verdade do projeto.
        self.enterContext(mock.patch.object(
            instalador, "CAMINHO_CONFIG", self.config_json))
        self.enterContext(mock.patch.object(
            modulo_config, "CAMINHO_CONFIG", self.config_json))
        # Nem criar atalho no sistema de quem roda os testes.
        self.enterContext(mock.patch.object(
            atalho, "criar",
            return_value=atalho.Atalho(None, True, "atalho de teste")))

    def rodar(self, etapa) -> tuple[list[str], str]:
        estado = {"detalhe": ""}
        linhas = list(etapa(estado, self.escolhida))
        return linhas, estado["detalhe"]


class TestPrepararCatalogo(BaseInstalacao):
    def test_cria_a_pasta_organizada_ao_lado_da_escolhida(self):
        self.rodar(instalador.preparar_catalogo)
        self.assertTrue((self.escolhida.parent / "organizados").is_dir())

    def test_cria_o_caderno_de_fichas(self):
        self.rodar(instalador.preparar_catalogo)
        self.assertTrue((self.escolhida.parent / "organizados" / PASTA_CATALOGO).is_dir())

    def test_nao_fala_em_banco_de_dados(self):
        linhas, detalhe = self.rodar(instalador.preparar_catalogo)
        texto = " ".join(linhas + [detalhe]).lower()
        self.assertNotIn("sqlite", texto)
        self.assertNotIn("fts5", texto)

    def test_e_idempotente(self):
        self.rodar(instalador.preparar_catalogo)
        self.rodar(instalador.preparar_catalogo)  # nao pode levantar

    def test_reinstalar_por_cima_reconhece_o_que_ja_estava_arquivado(self):
        saida = self.escolhida.parent / "organizados" / "contrato" / "2026" / "03"
        saida.mkdir(parents=True)
        exemplos = Path(__file__).resolve().parent.parent / "exemplos"
        (saida / "contrato_aluguel.txt").write_text(
            (exemplos / "contrato_aluguel.txt").read_text(encoding="utf-8"),
            encoding="utf-8")

        linhas, _ = self.rodar(instalador.preparar_catalogo)
        self.assertTrue(any("1 documento" in linha for linha in linhas))


class TestDefinirPasta(BaseInstalacao):
    def test_grava_a_pasta_escolhida_no_config(self):
        """O defeito: a escolha tinha que chegar ao disco, e nao so a tela."""
        self.rodar(instalador.definir_pasta)

        gravado = Config.carregar(self.config_json)
        self.assertEqual(gravado.pasta_entrada, self.escolhida)

    def test_a_saida_acompanha_a_entrada_escolhida(self):
        self.rodar(instalador.definir_pasta)
        gravado = Config.carregar(self.config_json)
        self.assertEqual(gravado.pasta_saida, self.escolhida.parent / "organizados")

    def test_trocar_de_pasta_leva_a_saida_junto(self):
        """Senao os documentos novos continuariam indo para o lugar antigo."""
        self.rodar(instalador.definir_pasta)
        self.escolhida = self.base / "OutraPasta" / "entrada"
        self.rodar(instalador.definir_pasta)

        gravado = Config.carregar(self.config_json)
        self.assertEqual(gravado.pasta_entrada, self.base / "OutraPasta" / "entrada")
        self.assertEqual(gravado.pasta_saida, self.base / "OutraPasta" / "organizados")

    def test_cria_a_pasta_vigiada(self):
        self.rodar(instalador.definir_pasta)
        self.assertTrue(self.escolhida.is_dir())


class TestInstalacaoCompleta(BaseInstalacao):
    def test_as_seis_etapas_tem_titulo(self):
        titulos = [titulo for titulo, _ in instalador.PASSOS]
        self.assertEqual(len(titulos), 6)
        self.assertIn("Preparando a pasta organizada", titulos)
        self.assertNotIn("Criando banco de dados", titulos)

    def test_as_duas_ultimas_etapas_recebem_a_pasta(self):
        """Sem isso a instalacao usaria a pasta padrao em vez da escolhida."""
        for etapa in (instalador.preparar_catalogo, instalador.definir_pasta):
            with self.subTest(etapa=etapa.__name__):
                self.assertEqual(etapa.__code__.co_argcount, 2)

    def test_instantaneo_tem_o_que_a_tela_consome(self):
        instalacao = instalador.Instalacao(self.escolhida)
        foto = instalacao.instantaneo()
        for campo in ("indice", "progresso", "concluido", "erro", "pasta",
                      "etapas", "log"):
            self.assertIn(campo, foto)
        self.assertEqual(len(foto["etapas"]), 6)


class TestApontarPasta(BaseInstalacao):
    """O botao "escolher pasta" do instalador."""

    def test_apontar_grava_no_disco_e_nao_so_em_memoria(self):
        from autodoc.instalacao.principal import Instalador

        instalando = Instalador.__new__(Instalador)
        instalando.pasta_entrada = self.base / "antiga"
        instalando._apontar(self.escolhida)

        self.assertEqual(instalando.pasta_entrada, self.escolhida)
        self.assertEqual(Config.carregar(self.config_json).pasta_entrada,
                         self.escolhida)

    def test_apontar_atualiza_a_pasta_de_saida_mostrada(self):
        from autodoc.instalacao.principal import Instalador

        instalando = Instalador.__new__(Instalador)
        instalando.pasta_entrada = self.base / "antiga"
        instalando._apontar(self.escolhida)

        self.assertEqual(instalando.pasta_saida,
                         self.escolhida.parent / "organizados")


if __name__ == "__main__":
    unittest.main()
