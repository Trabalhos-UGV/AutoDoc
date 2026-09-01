"""A API que as telas consomem, exercitada por HTTP de verdade."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from autodoc import monitor
from autodoc.catalogo import Catalogo
from autodoc.config import Config
from autodoc.pipeline import Pipeline
from autodoc.web.servidor import Servidor

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class BaseServidor(unittest.TestCase):
    """Sobe um AutoDoc completo numa pasta temporaria, com os exemplos dentro."""

    PORTA = 8901

    @classmethod
    def setUpClass(cls):
        # A espera pela copia terminar nao e o que se testa aqui, e cobrar
        # meio segundo por arquivo deixaria a suite lenta a toa.
        cls._intervalo = monitor.INTERVALO_ESTABILIDADE
        monitor.INTERVALO_ESTABILIDADE = 0.01

        cls._temporaria = tempfile.TemporaryDirectory()
        base = Path(cls._temporaria.name)
        cls.config = Config(pasta_entrada=base / "entrada",
                            pasta_saida=base / "organizados")
        cls.config.preparar_pastas()
        cls.catalogo = Catalogo(cls.config.pasta_saida)
        cls.pipeline = Pipeline(cls.config, cls.catalogo)

        for exemplo in sorted(EXEMPLOS.glob("*.txt")):
            shutil.copy2(exemplo, cls.config.pasta_entrada / exemplo.name)

        # porta 0 nao existe como preferida: o servidor procura a proxima livre
        cls.servidor = Servidor(cls.config, cls.catalogo, cls.pipeline, porta=cls.PORTA)
        cls.url = cls.servidor.iniciar()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.parar()
        cls._temporaria.cleanup()
        monitor.INTERVALO_ESTABILIDADE = cls._intervalo

    def get(self, rota: str) -> dict:
        with urllib.request.urlopen(self.url.rstrip("/") + rota) as resposta:
            return json.loads(resposta.read())

    def post(self, rota: str, corpo: dict) -> dict:
        pedido = urllib.request.Request(
            self.url.rstrip("/") + rota, data=json.dumps(corpo).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(pedido) as resposta:
            return json.loads(resposta.read())


class TestEstado(BaseServidor):
    def test_existir_ja_significa_modo_real(self):
        self.assertEqual(self.get("/api/estado")["modo"], "real")

    def test_informa_as_duas_pastas(self):
        estado = self.get("/api/estado")
        self.assertEqual(estado["pasta"], str(self.config.pasta_entrada))
        self.assertEqual(estado["pasta_saida"], str(self.config.pasta_saida))

    def test_nao_anuncia_banco_nem_fts5(self):
        self.assertEqual(self.get("/api/estado")["busca"], "índice interno")

    def test_oferece_as_categorias_para_correcao_manual(self):
        rotulos = [c["rotulo"] for c in self.get("/api/estado")["categorias_possiveis"]]
        self.assertIn("Contrato", rotulos)
        self.assertIn("Conta de energia", rotulos)


class TestDocumentos(BaseServidor):
    def test_os_exemplos_pendentes_foram_processados_ao_subir(self):
        self.assertEqual(len(self.get("/api/documentos")["linhas"]), 5)

    def test_a_linha_tem_o_que_a_tela_desenha(self):
        linha = self.get("/api/documentos")["linhas"][0]
        for campo in ("id", "arquivo", "origem", "tipo", "confianca",
                      "data", "destino", "regra", "chaves", "trecho", "etapas"):
            self.assertIn(campo, linha)

    def test_chaves_e_etapas_chegam_como_listas(self):
        """Vinham como texto JSON quando havia banco; agora ja sao listas."""
        linha = self.get("/api/documentos")["linhas"][0]
        self.assertIsInstance(linha["chaves"], list)
        self.assertIsInstance(linha["etapas"], list)

    def test_data_sai_no_formato_brasileiro(self):
        conta = next(l for l in self.get("/api/documentos")["linhas"]
                     if "energia" in l["arquivo"])
        self.assertEqual(conta["data"], "12/03/2026")

    def test_filtra_pelo_rotulo_da_barra_lateral(self):
        dados = self.get("/api/documentos?cat=Conta%20de%20energia")
        self.assertEqual([l["arquivo"] for l in dados["linhas"]],
                         ["conta_energia_marco.txt"])

    def test_busca_pelo_conteudo(self):
        dados = self.get("/api/documentos?q=kwh")
        self.assertEqual([l["arquivo"] for l in dados["linhas"]],
                         ["conta_energia_marco.txt"])

    def test_todos_traz_a_lista_completa_mesmo_filtrando(self):
        """O painel de detalhe precisa achar o selecionado fora do filtro."""
        dados = self.get("/api/documentos?q=kwh")
        self.assertEqual(len(dados["linhas"]), 1)
        self.assertEqual(len(dados["todos"]), 5)

    def test_estatisticas_e_categorias_acompanham(self):
        dados = self.get("/api/documentos")
        self.assertEqual(dados["estatisticas"]["arquivados"], 5)
        self.assertEqual(dados["estatisticas"]["revisar"], 1)
        self.assertEqual(dados["categorias"][0]["nome"], "Todos")
        self.assertEqual(dados["categorias"][0]["contagem"], "5")


class TestRotas(BaseServidor):
    def test_a_raiz_serve_a_tela(self):
        with urllib.request.urlopen(self.url) as resposta:
            corpo = resposta.read().decode("utf-8")
        self.assertIn("<title", corpo.lower())
        self.assertIn("data-linhas", corpo)

    def test_rota_de_api_desconhecida_da_404(self):
        with self.assertRaises(urllib.error.HTTPError) as erro:
            self.get("/api/inventada")
        self.assertEqual(erro.exception.code, 404)


class TestAcoes(BaseServidor):
    def test_abrir_documento_inexistente(self):
        self.assertFalse(self.post("/api/abrir", {"id": 9999})["aberto"])

    def test_corrigir_documento_inexistente(self):
        resposta = self.post("/api/reclassificar", {"id": 9999, "categoria": "contrato"})
        self.assertFalse(resposta["ok"])

    def test_corrigir_para_categoria_inventada(self):
        alvo = self.a_revisar()
        with self.assertLogs("autodoc.web.servidor", "WARNING"):
            resposta = self.post("/api/reclassificar",
                                 {"id": alvo["id"], "categoria": "inventada"})
        self.assertFalse(resposta["ok"])
        self.assertIn("desconhecida", resposta["erro"])

    def a_revisar(self) -> dict:
        return next(l for l in self.get("/api/documentos")["linhas"]
                    if l["categoria"] == "nao_classificado")


class TestCorrecaoPelaApi(BaseServidor):
    """Instalacao propria: corrigir muda o disco e nao pode afetar os vizinhos."""

    PORTA = 8905

    def test_corrigir_move_o_documento_e_atualiza_a_tela(self):
        alvo = next(l for l in self.get("/api/documentos")["linhas"]
                    if l["categoria"] == "nao_classificado")

        resposta = self.post("/api/reclassificar",
                             {"id": alvo["id"], "categoria": "contrato"})
        self.assertTrue(resposta["ok"])
        self.assertEqual(resposta["linha"]["tipo"], "Contrato")
        self.assertEqual(resposta["linha"]["confianca"], "100%")

        # e a correcao vale para quem consultar depois
        depois = self.get("/api/documentos")
        self.assertEqual(depois["estatisticas"]["revisar"], 0)
        self.assertEqual(len(depois["linhas"]), 5, "nenhum documento se perdeu")


class TestPortaOcupada(unittest.TestCase):
    def test_segunda_instancia_escolhe_outra_porta(self):
        """Abrir o AutoDoc com uma janela ja aberta nao pode derrubar nada."""
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        base = Path(temporaria.name)

        # Pastas distintas: em uso sao dois processos, e o watchdog nao aceita
        # dois observadores da mesma pasta dentro de um processo so.
        servidores = []
        for nome in ("um", "dois"):
            config = Config(pasta_entrada=base / nome / "entrada",
                            pasta_saida=base / nome / "saida")
            config.preparar_pastas()
            catalogo = Catalogo(config.pasta_saida)
            servidor = Servidor(config, catalogo, Pipeline(config, catalogo), porta=8911)
            self.addCleanup(servidor.parar)
            servidores.append(servidor)

        primeiro, segundo = servidores

        self.assertEqual(primeiro.iniciar(), "http://127.0.0.1:8911/")
        self.assertEqual(segundo.iniciar(), "http://127.0.0.1:8912/")


if __name__ == "__main__":
    unittest.main()
