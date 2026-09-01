"""As etapas da instalacao — e a pasta escolhida chegando ao config.json.

Este arquivo existe por causa de um defeito concreto: escolher outra pasta no
instalador mudava so o texto da tela, e o AutoDoc subia vigiando a pasta
anterior. A janela abria vazia e nao havia como saber por que.
"""

from __future__ import annotations

import tempfile
import unittest
from collections import namedtuple
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
        """Roda uma etapa que precisa saber a pasta escolhida."""
        estado = {"detalhe": ""}
        linhas = list(etapa(estado, self.escolhida))
        return linhas, estado["detalhe"]

    def rodar_sem_pasta(self, etapa) -> tuple[list[str], str]:
        """Roda uma das quatro etapas que só olham o ambiente."""
        estado = {"detalhe": ""}
        linhas = list(etapa(estado))
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


class TestVerificarAmbiente(BaseInstalacao):
    def test_informa_a_versao_e_o_espaco(self):
        linhas, detalhe = self.rodar_sem_pasta(instalador.verificar_ambiente)
        self.assertTrue(any("python --version" in l for l in linhas))
        self.assertTrue(any("espaço em disco" in l for l in linhas))
        self.assertIn("Python", detalhe)

    def test_python_velho_demais_interrompe_a_instalacao(self):
        """Instalar num Python que não roda o programa seria pior do que parar."""
        # `sys.version_info` é uma namedtuple: o código lê `.major` e `.minor`.
        Versao = namedtuple("Versao", "major minor micro releaselevel serial")
        antigo = Versao(3, 8, 0, "final", 0)
        with mock.patch.object(instalador.sys, "version_info", antigo):
            with self.assertRaises(RuntimeError) as erro:
                list(instalador.verificar_ambiente({"detalhe": ""}))

        self.assertIn("3.10", str(erro.exception))


class TestCriarAmbienteVirtual(BaseInstalacao):
    def test_venv_existente_nao_e_recriado(self):
        with mock.patch.object(instalador.subprocess, "run") as rodou:
            linhas, detalhe = self.rodar_sem_pasta(instalador.criar_ambiente_virtual)

        rodou.assert_not_called()
        self.assertTrue(any("já existe" in l for l in linhas))
        self.assertIn("já estava criado", detalhe)

    def test_venv_ausente_e_criado(self):
        with mock.patch.object(instalador, "_python_do_venv",
                               return_value=self.base / "venv" / "bin" / "python"), \
             mock.patch.object(instalador.subprocess, "run") as rodou:
            linhas, detalhe = self.rodar_sem_pasta(instalador.criar_ambiente_virtual)

        rodou.assert_called_once()
        self.assertIn("venv", rodou.call_args.args[0])
        self.assertTrue(any("criado" in l for l in linhas))


class TestInstalarDependencias(BaseInstalacao):
    def processo(self, returncode=0, stdout="", stderr=""):
        resultado = mock.Mock()
        resultado.returncode = returncode
        resultado.stdout, resultado.stderr = stdout, stderr
        return resultado

    def test_resume_o_que_foi_instalado(self):
        """A saída do pip é comprida; cortada no meio fica pior do que resumida."""
        saidas = [
            self.processo(stdout="Collecting watchdog\nSuccessfully installed watchdog-4.0.0"),
            self.processo(stdout="watchdog==4.0.0\npypdf==4.0.0"),
        ]
        with mock.patch.object(instalador.subprocess, "run", side_effect=saidas):
            linhas, detalhe = self.rodar_sem_pasta(instalador.instalar_dependencias)

        self.assertTrue(any("Successfully installed" in l for l in linhas))
        self.assertTrue(any("2 pacotes" in l for l in linhas))
        self.assertIn("watchdog", detalhe)

    def test_quando_nada_e_novo_conta_o_que_ja_tinha(self):
        saidas = [
            self.processo(stdout="Requirement already satisfied: watchdog\n"
                                 "Requirement already satisfied: pypdf\n"),
            self.processo(stdout="watchdog==4.0.0"),
        ]
        with mock.patch.object(instalador.subprocess, "run", side_effect=saidas):
            linhas, _ = self.rodar_sem_pasta(instalador.instalar_dependencias)

        self.assertTrue(any("2 dependências já estavam" in l for l in linhas))

    def test_pip_que_falha_interrompe_com_o_erro_na_mensagem(self):
        falhou = self.processo(returncode=1, stderr="ERROR: nao foi possivel resolver")
        with mock.patch.object(instalador.subprocess, "run", return_value=falhou):
            with self.assertRaises(RuntimeError) as erro:
                list(instalador.instalar_dependencias({"detalhe": ""}))

        self.assertIn("falha ao instalar", str(erro.exception))
        self.assertIn("nao foi possivel resolver", str(erro.exception))


class TestConfigurarOcr(BaseInstalacao):
    def test_tesseract_presente(self):
        versao = mock.Mock(stdout="tesseract 5.3.4\n leptonica-1.84")
        with mock.patch.object(instalador.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(instalador.subprocess, "run", return_value=versao):
            linhas, detalhe = self.rodar_sem_pasta(instalador.configurar_ocr)

        self.assertTrue(any("/usr/bin/tesseract" in l for l in linhas))
        self.assertTrue(any("5.3.4" in l for l in linhas))
        self.assertIn("pronto", detalhe)

    def test_tesseract_ausente_nao_e_erro(self):
        """O AutoDoc lê PDF e texto sem OCR; faltar o Tesseract não impede nada."""
        with mock.patch.object(instalador.shutil, "which", return_value=None):
            linhas, detalhe = self.rodar_sem_pasta(instalador.configurar_ocr)

        self.assertTrue(any("não encontrado" in l for l in linhas))
        self.assertTrue(any("funciona normalmente" in l for l in linhas))
        self.assertIn("desativado", detalhe)


class TestExecutar(BaseInstalacao):
    """O gerador de estados que alimenta a tela."""

    def instalacao_com_passos(self, passos):
        instalacao = instalador.Instalacao(self.escolhida)
        instalacao.etapas = [instalador.Etapa(titulo) for titulo, _ in passos]
        return instalacao

    def test_percorre_as_etapas_ate_o_fim(self):
        def etapa_boba(estado):
            estado["detalhe"] = "feito"
            yield "trabalhando"

        passos = [("Uma", etapa_boba), ("Outra", etapa_boba)]
        with mock.patch.object(instalador, "PASSOS", passos):
            instalacao = self.instalacao_com_passos(passos)
            estados = list(instalacao.executar())

        self.assertTrue(instalacao.concluido)
        self.assertIsNone(instalacao.erro)
        self.assertEqual(estados[-1]["progresso"], 100.0)

    def test_o_progresso_nunca_anda_para_tras(self):
        def etapa_boba(estado):
            yield "um"
            yield "dois"

        passos = [("Uma", etapa_boba), ("Outra", etapa_boba)]
        with mock.patch.object(instalador, "PASSOS", passos):
            progressos = [e["progresso"] for e in self.instalacao_com_passos(passos).executar()]

        self.assertEqual(progressos, sorted(progressos))
        self.assertEqual(progressos[0], 0.0)

    def test_uma_etapa_que_falha_para_tudo_e_conta_qual_foi(self):
        def explode(estado):
            yield "comecando"
            raise RuntimeError("disco cheio")

        def nunca_roda(estado):
            raise AssertionError("nao deveria ter chegado aqui")
            yield

        passos = [("Etapa Ruim", explode), ("Etapa Seguinte", nunca_roda)]
        with mock.patch.object(instalador, "PASSOS", passos):
            instalacao = self.instalacao_com_passos(passos)
            estados = list(instalacao.executar())

        self.assertFalse(instalacao.concluido)
        self.assertIn("Etapa Ruim", instalacao.erro)
        self.assertIn("disco cheio", instalacao.erro)
        self.assertIn("disco cheio", estados[-1]["erro"])

    def test_o_erro_aparece_no_log_da_tela(self):
        def explode(estado):
            raise RuntimeError("sem permissao")
            yield

        with mock.patch.object(instalador, "PASSOS", [("Etapa", explode)]):
            instalacao = self.instalacao_com_passos([("Etapa", explode)])
            estados = list(instalacao.executar())

        self.assertTrue(any("ERRO" in l["mensagem"] for l in estados[-1]["log"]))

    def test_o_log_nao_cresce_sem_limite(self):
        def muitas_linhas(estado):
            for numero in range(60):
                yield f"linha {numero}"

        with mock.patch.object(instalador, "PASSOS", [("Etapa", muitas_linhas)]):
            instalacao = self.instalacao_com_passos([("Etapa", muitas_linhas)])
            list(instalacao.executar())

        self.assertEqual(len(instalacao.log), 40)
        self.assertEqual(len(instalacao.instantaneo()["log"]), 8)


if __name__ == "__main__":
    unittest.main()
