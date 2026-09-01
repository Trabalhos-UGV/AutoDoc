"""A API que as telas consomem, exercitada por HTTP de verdade."""

from __future__ import annotations

import errno
import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from autodoc import monitor
from autodoc.catalogo import Catalogo
from autodoc.config import Config
from autodoc.pipeline import Pipeline, Resultado
from autodoc.web import servidor
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

    def test_post_em_rota_desconhecida_tambem_da_404(self):
        with self.assertRaises(urllib.error.HTTPError) as erro:
            self.post("/api/tambem-inventada", {})
        self.assertEqual(erro.exception.code, 404)

    def test_serve_o_css_e_o_js_da_tela(self):
        for arquivo, marca in (("/js/app.js", "ouvirNovidades"),
                               ("/css/app.css", ".linha")):
            with self.subTest(arquivo=arquivo):
                with urllib.request.urlopen(self.url.rstrip("/") + arquivo) as resposta:
                    self.assertIn(marca, resposta.read().decode("utf-8"))


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


class TestLinhaForaDaPasta(BaseServidor):
    PORTA = 8927

    def test_documento_fora_da_pasta_de_saida_mostra_o_caminho_inteiro(self):
        """Pode acontecer com uma ficha antiga, de quando a saída era outra."""
        ficha = self.catalogo.por_id(1)
        ficha.caminho = "/outro/lugar/conta.txt"

        linha = self.servidor._linha(self.catalogo.como_dict(ficha))
        self.assertEqual(linha["destino"], "/outro/lugar/")


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

    def test_erro_que_nao_e_porta_ocupada_sobe(self):
        """Só "endereço em uso" justifica tentar outra porta."""
        servidor_app = self.montar()
        with mock.patch.object(servidor, "ServidorHTTP",
                               side_effect=OSError(13, "sem permissao")):
            with self.assertRaises(OSError) as erro:
                servidor_app._escutar()
        self.assertEqual(erro.exception.errno, 13)

    def test_nenhuma_porta_livre(self):
        servidor_app = self.montar()
        ocupada = OSError(errno.EADDRINUSE, "endereco em uso")

        with mock.patch.object(servidor, "ServidorHTTP", side_effect=ocupada):
            with self.assertRaises(OSError) as erro:
                servidor_app._escutar()

        self.assertIn("nenhuma porta livre", str(erro.exception))

    def montar(self) -> Servidor:
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        base = Path(temporaria.name)

        config = Config(pasta_entrada=base / "entrada", pasta_saida=base / "saida")
        config.preparar_pastas()
        catalogo = Catalogo(config.pasta_saida)
        return Servidor(config, catalogo, Pipeline(config, catalogo), porta=8951)


class TestFormatarData(unittest.TestCase):
    def test_iso_vira_formato_brasileiro(self):
        self.assertEqual(servidor._formatar_data("2026-03-12"), "12/03/2026")

    def test_sem_data(self):
        self.assertEqual(servidor._formatar_data(None), "—")
        self.assertEqual(servidor._formatar_data(""), "—")

    def test_data_estranha_volta_como_esta(self):
        """Uma ficha antiga ou mexida à mão não pode quebrar a listagem."""
        self.assertEqual(servidor._formatar_data("marco de 2026"), "marco de 2026")


class TestAbrirNoSistema(unittest.TestCase):
    """Entregar o caminho ao gerenciador de arquivos de cada sistema."""

    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporaria.name)
        self.alvo = self.pasta / "conta.pdf"
        self.alvo.write_text("documento", encoding="utf-8")
        self.addCleanup(self._temporaria.cleanup)

    def comando_de(self, plataforma, revelar=False):
        with mock.patch.object(servidor.sys, "platform", plataforma), \
             mock.patch.object(servidor.subprocess, "Popen") as abriu:
            self.assertTrue(servidor.abrir_no_sistema(self.alvo, revelar=revelar))
        return abriu.call_args.args[0]

    def test_macos_abre_o_arquivo(self):
        self.assertEqual(self.comando_de("darwin"), ["open", str(self.alvo)])

    def test_macos_revela_na_pasta(self):
        self.assertEqual(self.comando_de("darwin", revelar=True),
                         ["open", "-R", str(self.alvo)])

    def test_windows_abre_o_arquivo(self):
        self.assertEqual(self.comando_de("win32")[:3], ["cmd", "/c", "start"])

    def test_windows_seleciona_na_pasta(self):
        self.assertEqual(self.comando_de("win32", revelar=True),
                         ["explorer", f"/select,{self.alvo}"])

    def test_linux_abre_o_arquivo(self):
        self.assertEqual(self.comando_de("linux"), ["xdg-open", str(self.alvo)])

    def test_linux_revela_abrindo_a_pasta(self):
        """Não há "revelar" universal no Linux; a pasta é o mais próximo."""
        self.assertEqual(self.comando_de("linux", revelar=True),
                         ["xdg-open", str(self.pasta)])

    def test_caminho_inexistente_nao_chama_nada(self):
        with mock.patch.object(servidor.subprocess, "Popen") as abriu:
            self.assertFalse(servidor.abrir_no_sistema(self.pasta / "nao-existe"))
        abriu.assert_not_called()

    def test_falha_do_sistema_vira_falso(self):
        with mock.patch.object(servidor.subprocess, "Popen",
                               side_effect=OSError("sem permissao")), \
             self.assertLogs("autodoc.web.servidor", "ERROR"):
            self.assertFalse(servidor.abrir_no_sistema(self.alvo))


class TestHandleError(unittest.TestCase):
    """Fechar a janela derruba o SSE no meio; isso é normal, não defeito."""

    def manipular(self, excecao):
        http = servidor.ServidorHTTP.__new__(servidor.ServidorHTTP)
        with mock.patch.object(servidor.sys, "exc_info",
                               return_value=(type(excecao), excecao, None)), \
             mock.patch.object(servidor.ThreadingHTTPServer, "handle_error") as padrao:
            http.handle_error(None, ("127.0.0.1", 1234))
        return padrao

    def test_conexao_derrubada_e_silenciosa(self):
        for excecao in (BrokenPipeError(), ConnectionResetError()):
            with self.subTest(excecao=type(excecao).__name__):
                self.manipular(excecao).assert_not_called()

    def test_erro_de_verdade_continua_aparecendo(self):
        self.manipular(ValueError("defeito de verdade")).assert_called_once()


class TestEventos(BaseServidor):
    """O SSE — o que faz a linha aparecer sozinha quando um arquivo cai na pasta."""

    PORTA = 8921

    def test_inscrever_e_desinscrever(self):
        fila = self.servidor._inscrever()
        self.assertIn(fila, self.servidor._ouvintes)

        self.servidor._desinscrever(fila)
        self.assertNotIn(fila, self.servidor._ouvintes)

    def test_desinscrever_duas_vezes_nao_quebra(self):
        fila = self.servidor._inscrever()
        self.servidor._desinscrever(fila)
        self.servidor._desinscrever(fila)

    def test_anuncia_o_documento_que_chegou(self):
        """E não "o primeiro da listagem": ela ordena por data do documento, então
        uma conta de 2019 processada agora faria a tela anunciar outro arquivo."""
        fila = self.servidor._inscrever()
        self.addCleanup(self.servidor._desinscrever, fila)

        antiga = self.config.pasta_entrada / "conta_antiga.txt"
        antiga.write_text(
            "CEMIG\nConsumo faturado: 90 kWh\nBandeira tarifaria: verde\n"
            "VENCIMENTO 12/03/2019\nTOTAL A PAGAR R$ 90,00", encoding="utf-8")
        resultado = self.pipeline.processar(antiga)
        self.servidor._anunciar(resultado)

        anunciada = fila.get(timeout=2)
        self.assertEqual(anunciada["arquivo"], "conta_antiga.txt")
        self.assertEqual(anunciada["data"], "12/03/2019")

    def test_duas_telas_abertas_recebem_o_mesmo_documento(self):
        """Uma fila só faria o documento aparecer em uma janela apenas."""
        uma = self.servidor._inscrever()
        outra = self.servidor._inscrever()
        self.addCleanup(self.servidor._desinscrever, uma)
        self.addCleanup(self.servidor._desinscrever, outra)

        novo = self.config.pasta_entrada / "boleto_sse.txt"
        novo.write_text(
            "BOLETO BANCARIO\nLinha digitavel: 34191.79001\nCedente: Imobiliaria\n"
            "Nosso numero: 991\nVencimento: 25/05/2026", encoding="utf-8")
        self.servidor._anunciar(self.pipeline.processar(novo))

        self.assertEqual(uma.get(timeout=2)["arquivo"], "boleto_sse.txt")
        self.assertEqual(outra.get(timeout=2)["arquivo"], "boleto_sse.txt")

    def test_resultado_sem_documento_nao_anuncia_nada(self):
        fila = self.servidor._inscrever()
        self.addCleanup(self.servidor._desinscrever, fila)

        self.servidor._anunciar(Resultado(Path("qualquer.txt"), ignorado="ja indexado"))
        self.assertTrue(fila.empty())

    def test_a_tela_fechada_deixa_de_estar_inscrita(self):
        """Fechar a janela derruba a conexão no meio de uma escrita.

        Isso é comportamento normal de quem fecha um programa: o servidor
        precisa soltar o inscrito em vez de acumular fila para sempre.
        """
        fluxo = urllib.request.urlopen(self.url + "api/eventos", timeout=8)
        for _ in range(200):
            if self.servidor._ouvintes:
                break
            time.sleep(0.02)
        self.assertEqual(len(self.servidor._ouvintes), 1)

        fluxo.close()

        # o servidor só descobre a queda ao tentar escrever
        linha = self.servidor.catalogo.listar(1)[0]
        for _ in range(100):
            with self.servidor._trava:
                for fila in list(self.servidor._ouvintes):
                    fila.put(self.servidor._linha(linha))
            if not self.servidor._ouvintes:
                break
            time.sleep(0.05)

        self.assertEqual(self.servidor._ouvintes, [])

    def test_o_fluxo_entrega_o_documento_pela_conexao(self):
        """O caminho de verdade: EventSource aberto, arquivo novo, linha na tela."""
        recebido = []

        def escutar():
            with urllib.request.urlopen(self.url + "api/eventos", timeout=8) as fluxo:
                for linha in fluxo:
                    if linha.startswith(b"data: "):
                        recebido.append(json.loads(linha[6:]))
                        return

        ouvinte = threading.Thread(target=escutar, daemon=True)
        ouvinte.start()

        # espera o servidor registrar a inscrição antes de processar
        for _ in range(100):
            if self.servidor._ouvintes:
                break
            time.sleep(0.02)

        novo = self.config.pasta_entrada / "comprovante_sse.txt"
        novo.write_text(
            "COMPROVANTE DE PAGAMENTO\nPIX\nID da transacao: 7781\n"
            "Chave PIX: fulano@exemplo.br\nData: 04/04/2026", encoding="utf-8")
        self.servidor._anunciar(self.pipeline.processar(novo))

        ouvinte.join(timeout=8)
        self.assertEqual(len(recebido), 1, "nada chegou pelo fluxo")
        self.assertEqual(recebido[0]["arquivo"], "comprovante_sse.txt")
        self.assertEqual(recebido[0]["tipo"], "Comprovante")


class TestAbrirPelaApi(BaseServidor):
    PORTA = 8925

    def test_sem_id_abre_a_pasta_monitorada(self):
        with mock.patch.object(servidor, "abrir_no_sistema", return_value=True) as abriu:
            resposta = self.post("/api/abrir", {})

        self.assertTrue(resposta["aberto"])
        self.assertEqual(resposta["alvo"], str(self.config.pasta_entrada))
        self.assertEqual(abriu.call_args.args[0], self.config.pasta_entrada)

    def test_com_id_abre_o_documento(self):
        alvo = self.get("/api/documentos")["linhas"][0]
        with mock.patch.object(servidor, "abrir_no_sistema", return_value=True) as abriu:
            resposta = self.post("/api/abrir", {"id": alvo["id"]})

        self.assertTrue(resposta["aberto"])
        self.assertIn(alvo["arquivo"], resposta["alvo"])
        self.assertFalse(abriu.call_args.kwargs["revelar"])

    def test_revelar_pede_para_mostrar_na_pasta(self):
        alvo = self.get("/api/documentos")["linhas"][0]
        with mock.patch.object(servidor, "abrir_no_sistema", return_value=True) as abriu:
            self.post("/api/abrir", {"id": alvo["id"], "revelar": True})

        self.assertTrue(abriu.call_args.kwargs["revelar"])


if __name__ == "__main__":
    unittest.main()
