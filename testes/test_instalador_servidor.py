"""O instalador gráfico por dentro: o estado que ele guarda e as rotas dele.

É o módulo onde estava o defeito que abria a janela vazia — escolher a pasta
mudava só a memória e não o disco. Aqui se testa o resto: os eventos que
alimentam a tela e a API que ela chama.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path
from unittest import mock

from autodoc import config as modulo_config
from autodoc.instalacao import atalho, instalador as modulo_instalador
from autodoc.instalacao.principal import Instalador, RotasInstalador
from autodoc.web.servidor import ServidorHTTP


class BaseInstalador(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.base = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)

        self.config_json = self.base / "config.json"
        self.enterContext(mock.patch.object(
            modulo_config, "CAMINHO_CONFIG", self.config_json))
        self.enterContext(mock.patch.object(
            modulo_instalador, "CAMINHO_CONFIG", self.config_json))
        self.enterContext(mock.patch.object(
            atalho, "criar", return_value=atalho.Atalho(None, True, "atalho de teste")))

        self.instalador = Instalador()
        self.instalador.pasta_entrada = self.base / "entrada"
        self.instalador.pasta_saida = self.base / "organizados"


class TestInscricao(BaseInstalador):
    """Uma fila por tela aberta, para duas janelas não brigarem pelos eventos."""

    def test_inscrever_e_emitir(self):
        fila = self.instalador.inscrever()
        self.instalador._emitir({"progresso": 42})
        self.assertEqual(fila.get_nowait(), {"progresso": 42})

    def test_dois_inscritos_recebem_o_mesmo(self):
        uma = self.instalador.inscrever()
        outra = self.instalador.inscrever()
        self.instalador._emitir({"progresso": 7})

        self.assertEqual(uma.get_nowait()["progresso"], 7)
        self.assertEqual(outra.get_nowait()["progresso"], 7)

    def test_quem_chega_no_meio_ve_onde_a_instalacao_esta(self):
        """Sem isto a tela ficaria parada em 0% até o próximo evento."""
        self.instalador.instalacao = modulo_instalador.Instalacao(self.base / "entrada")
        self.instalador.instalacao.progresso = 60.0

        fila = self.instalador.inscrever()
        self.assertEqual(fila.get_nowait()["progresso"], 60.0)

    def test_sem_instalacao_em_curso_nao_manda_nada(self):
        self.assertTrue(self.instalador.inscrever().empty())

    def test_desinscrever_para_de_receber(self):
        fila = self.instalador.inscrever()
        self.instalador.desinscrever(fila)
        self.instalador._emitir({"progresso": 1})
        self.assertTrue(fila.empty())

    def test_desinscrever_duas_vezes_nao_quebra(self):
        fila = self.instalador.inscrever()
        self.instalador.desinscrever(fila)
        self.instalador.desinscrever(fila)


class TestInstalar(BaseInstalador):
    def test_roda_em_thread_para_a_tela_nao_congelar(self):
        with mock.patch.object(modulo_instalador, "PASSOS", []):
            self.instalador.instalar(str(self.base / "escolhida" / "entrada"))
            for _ in range(50):
                if self.instalador.instalacao.concluido:
                    break
                time.sleep(0.02)

        self.assertTrue(self.instalador.instalacao.concluido)
        self.assertEqual(self.instalador.pasta_entrada,
                         self.base / "escolhida" / "entrada")

    def test_nao_recomeca_o_que_ja_esta_rodando(self):
        self.instalador.instalacao = modulo_instalador.Instalacao(self.base / "entrada")
        primeira = self.instalador.instalacao

        self.instalador.instalar()
        self.assertIs(self.instalador.instalacao, primeira)

    def test_sem_pasta_usa_a_que_ja_estava(self):
        anterior = self.instalador.pasta_entrada
        with mock.patch.object(modulo_instalador, "PASSOS", []):
            self.instalador.instalar(None)
        self.assertEqual(self.instalador.pasta_entrada, anterior)


class TestEscolherPasta(BaseInstalador):
    def test_sem_janela_devolve_nada_sem_levantar(self):
        """O instalador pode estar servindo no navegador, sem janela nativa."""
        self.assertIsNone(self.instalador.escolher_pasta())

    def test_seletor_que_falha_e_registrado(self):
        janela = mock.Mock()
        janela.create_file_dialog.side_effect = RuntimeError("Cocoa recusou")

        with mock.patch("autodoc.instalacao.principal._janela", janela), \
             self.assertLogs("autodoc.instalacao.principal", "ERROR"):
            self.assertIsNone(self.instalador.escolher_pasta())

    def test_cancelar_o_seletor_mantem_a_pasta(self):
        janela = mock.Mock()
        janela.create_file_dialog.return_value = None
        anterior = self.instalador.pasta_entrada

        with mock.patch("autodoc.instalacao.principal._janela", janela):
            self.assertIsNone(self.instalador.escolher_pasta())
        self.assertEqual(self.instalador.pasta_entrada, anterior)

    def test_escolher_grava_no_disco(self):
        """O defeito de origem: a escolha tinha que sair da memória."""
        escolhida = self.base / "Documentos" / "AutoDoc" / "entrada"
        janela = mock.Mock()
        janela.create_file_dialog.return_value = [str(escolhida)]

        with mock.patch("autodoc.instalacao.principal._janela", janela):
            devolvido = self.instalador.escolher_pasta()

        self.assertEqual(devolvido, str(escolhida))
        gravado = json.loads(self.config_json.read_text(encoding="utf-8"))
        self.assertEqual(gravado["pasta_entrada"], str(escolhida))


class TestConcluir(BaseInstalador):
    def test_sobe_o_app_uma_vez_so_e_devolve_a_url(self):
        servidor = mock.Mock()
        with mock.patch("autodoc.web.servidor.Servidor", return_value=servidor):
            primeira = self.instalador.concluir()
            segunda = self.instalador.concluir()

        self.assertEqual(primeira, segunda)
        self.assertTrue(primeira.startswith("http://127.0.0.1:"))
        servidor.iniciar.assert_called_once()


class TestRotas(unittest.TestCase):
    """A API do instalador, exercitada por HTTP de verdade."""

    @classmethod
    def setUpClass(cls):
        cls._temporaria = tempfile.TemporaryDirectory()
        base = Path(cls._temporaria.name)
        cls.config_json = base / "config.json"

        cls._remendos = [
            mock.patch.object(modulo_config, "CAMINHO_CONFIG", cls.config_json),
            mock.patch.object(modulo_instalador, "CAMINHO_CONFIG", cls.config_json),
        ]
        for remendo in cls._remendos:
            remendo.start()

        cls.instalador = Instalador()
        cls.instalador.pasta_entrada = base / "entrada"
        cls.instalador.pasta_saida = base / "organizados"

        cls.servidor = ServidorHTTP(
            ("127.0.0.1", 8941), partial(RotasInstalador, instalador=cls.instalador))
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:8941"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        for remendo in cls._remendos:
            remendo.stop()
        cls._temporaria.cleanup()

    def get(self, rota: str):
        with urllib.request.urlopen(self.url + rota) as resposta:
            return json.loads(resposta.read())

    def post(self, rota: str, corpo=None, cru: bytes | None = None):
        dados = cru if cru is not None else json.dumps(corpo or {}).encode()
        pedido = urllib.request.Request(
            self.url + rota, data=dados, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(pedido) as resposta:
            return json.loads(resposta.read())

    def test_estado_traz_as_duas_pastas(self):
        estado = self.get("/api/estado")
        self.assertEqual(estado["modo"], "real")
        self.assertIn("pasta", estado)
        self.assertIn("pasta_saida", estado)

    def test_a_raiz_serve_a_tela_do_instalador(self):
        with urllib.request.urlopen(self.url + "/") as resposta:
            corpo = resposta.read().decode("utf-8")
        self.assertIn("data-etapas", corpo)
        self.assertIn("data-concluir", corpo)

    def test_instalar_responde_que_comecou(self):
        with mock.patch.object(self.instalador, "instalar") as comecou:
            resposta = self.post("/api/instalar", {"pasta_entrada": "/uma/pasta"})

        self.assertTrue(resposta["iniciado"])
        comecou.assert_called_once_with("/uma/pasta")

    def test_escolher_pasta_devolve_as_duas(self):
        with mock.patch.object(self.instalador, "escolher_pasta", return_value="/x"):
            resposta = self.post("/api/escolher-pasta")

        self.assertEqual(resposta["caminho"], "/x")
        self.assertIn("pasta_saida", resposta)

    def test_concluir_devolve_o_endereco_do_app(self):
        with mock.patch.object(self.instalador, "concluir",
                               return_value="http://127.0.0.1:8757/"):
            self.assertEqual(self.post("/api/concluir")["url"], "http://127.0.0.1:8757/")

    def test_corpo_que_nao_e_json_nao_derruba_o_servidor(self):
        with mock.patch.object(self.instalador, "instalar") as comecou:
            self.post("/api/instalar", cru=b"isto nao e json")
        comecou.assert_called_once_with(None)

    def test_corpo_vazio_e_aceito(self):
        with mock.patch.object(self.instalador, "instalar"):
            self.assertTrue(self.post("/api/instalar", cru=b"")["iniciado"])

    def test_rota_de_api_desconhecida_da_404(self):
        for chamada in (lambda: self.get("/api/inventada"),
                        lambda: self.post("/api/inventada")):
            with self.subTest(), self.assertRaises(urllib.error.HTTPError) as erro:
                chamada()
            self.assertEqual(erro.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
