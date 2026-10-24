"""O servidor do Tetris: a partida protegida, as rotas e a transmissao."""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from autodoc.gestos.reconhecimento import Gesto
from autodoc.gestos.servidor_tetris import FILA_POR_TELA, Partida, ServidorTetris, rodar_sem_camera
from autodoc.gestos.tetris import Jogo, Peca
from testes.apoio_gestos import montar_mao


def partida_parada() -> Partida:
    partida = Partida(Jogo(semente=3))
    partida.jogo.peca = Peca("T", linha=5, coluna=3)
    partida.jogo.tirar_eventos()
    return partida


class TestPartida(unittest.TestCase):
    def test_passo_sem_gesto_e_so_o_tempo(self):
        partida = partida_parada()
        for i in range(80):
            partida.passo(i / 60)
        self.assertEqual(partida.jogo.peca.linha, 6)
        self.assertEqual(partida.maos, [])

    def test_passo_com_gesto_comanda_e_guarda_as_maos(self):
        partida = partida_parada()
        maos = [{"principal": True, "pontos": [[0.5, 0.5]] * 21}]
        partida.passo(0.0, Gesto.MOVER, montar_mao(), maos)
        self.assertEqual(partida.maos, maos)
        self.assertEqual(partida.retrato()["controle"]["gesto"], "mover")

    def test_tecla(self):
        partida = partida_parada()
        self.assertTrue(partida.tecla("ArrowUp"))
        self.assertFalse(partida.tecla("F5"))
        self.assertEqual([e["tipo"] for e in partida.retrato()["eventos"]], ["girou"])

    def test_eventos_saem_uma_vez_so(self):
        partida = partida_parada()
        partida.tecla(" ")
        self.assertTrue(partida.retrato(consumir=False)["eventos"])
        self.assertTrue(partida.retrato()["eventos"])
        self.assertEqual(partida.retrato()["eventos"], [])

    def test_retrato_tem_o_jogo_e_o_resto(self):
        retrato = partida_parada().retrato()
        for chave in ("tabuleiro", "peca", "sombra", "proximas", "pontos", "controle", "camera", "maos", "eventos"):
            self.assertIn(chave, retrato)
        self.assertFalse(retrato["camera"])


class TestRotas(unittest.TestCase):
    def setUp(self):
        self.partida = partida_parada()
        self.servidor = ServidorTetris(self.partida, porta=18758)
        self.url = self.servidor.iniciar()
        self.addCleanup(self.servidor.parar)

    def pedir(self, rota: str, corpo: dict | None = None):
        dados = None if corpo is None else json.dumps(corpo).encode()
        pedido = urllib.request.Request(self.url + rota, data=dados, method="POST" if corpo is not None else "GET")
        with urllib.request.urlopen(pedido, timeout=5) as resposta:
            return resposta.status, resposta.read()

    def test_raiz_e_a_tela_do_tetris(self):
        status, corpo = self.pedir("")
        self.assertEqual(status, 200)
        self.assertIn(b"js/tetris.js", corpo)

    def test_formas_vao_junto_para_a_tela(self):
        _, corpo = self.pedir("api/estado")
        self.assertEqual(json.loads(corpo)["formas"]["O"], [[0, 1], [0, 2], [1, 1], [1, 2]])

    def test_serve_os_arquivos_das_telas(self):
        status, corpo = self.pedir("css/base.css")
        self.assertEqual(status, 200)
        self.assertIn(b"--ad-acento", corpo)

    def test_estado(self):
        _, corpo = self.pedir("api/estado")
        self.assertEqual(json.loads(corpo)["peca"]["tipo"], "T")

    def test_tecla_pela_rede(self):
        _, corpo = self.pedir("api/tecla", {"tecla": "ArrowLeft"})
        self.assertEqual(json.loads(corpo), {"aceita": True})
        self.assertEqual(self.partida.jogo.peca.coluna, 2)
        _, corpo = self.pedir("api/tecla", {})
        self.assertEqual(json.loads(corpo), {"aceita": False})

    def test_rotas_desconhecidas(self):
        for rota, corpo in (("api/nada", None), ("api/nada", {})):
            with self.assertRaises(urllib.error.HTTPError) as erro:
                self.pedir(rota, corpo)
            self.assertEqual(erro.exception.code, 404)

    def test_porta_ocupada_usa_a_proxima(self):
        outro = ServidorTetris(self.partida, porta=self.servidor.porta)
        self.addCleanup(outro.parar)
        self.assertNotEqual(outro.iniciar(), self.url)

    def test_transmissao_pelo_sse(self):
        recebido = []

        def escutar():
            with urllib.request.urlopen(self.url + "api/eventos", timeout=5) as fluxo:
                for linha in fluxo:
                    if linha.startswith(b"data: "):
                        recebido.append(json.loads(linha[6:]))
                        return

        ouvinte = threading.Thread(target=escutar, daemon=True)
        ouvinte.start()
        for _ in range(100):
            if self.servidor._ouvintes:
                break
            time.sleep(0.02)
        self.servidor.publicar(self.partida.retrato())
        ouvinte.join(5)
        self.assertEqual(recebido[0]["peca"]["tipo"], "T")

    def test_tela_engasgada_fica_com_os_mais_novos(self):
        fila = self.servidor._inscrever()
        self.addCleanup(self.servidor._desinscrever, fila)
        for numero in range(10):
            self.servidor.publicar({"numero": numero})
        self.assertEqual([fila.get_nowait()["numero"] for _ in range(fila.qsize())], list(range(10 - FILA_POR_TELA, 10)))

    def test_desinscrever_duas_vezes(self):
        fila = self.servidor._inscrever()
        self.servidor._desinscrever(fila)
        self.servidor._desinscrever(fila)
        self.assertEqual(self.servidor._ouvintes, [])


class TestCamera(unittest.TestCase):
    def setUp(self):
        self.servidor = ServidorTetris(partida_parada(), porta=18778)
        self.url = self.servidor.iniciar()
        self.addCleanup(self.servidor.parar)

    def test_retrato_leva_os_ossos_da_mao(self):
        retrato = self.servidor.partida.retrato()
        self.assertEqual(len(retrato["conexoes"]), 21)
        self.assertIsNone(retrato["camera_tamanho"])

    def test_espera_sem_quadro_novo_devolve_none(self):
        self.assertIsNone(self.servidor.esperar_imagem(None, espera=0.05))
        self.servidor.publicar_imagem(b"um")
        self.assertEqual(self.servidor.esperar_imagem(None, espera=0.05), b"um")
        self.assertIsNone(self.servidor.esperar_imagem(b"um", espera=0.05))

    def test_mjpeg_entrega_o_quadro_mais_novo(self):
        recebido = []

        def assistir():
            with urllib.request.urlopen(self.url + "api/camera.mjpg", timeout=5) as fluxo:
                recebido.append(fluxo.headers["Content-Type"])
                while len(recebido) < 3:
                    linha = fluxo.readline()
                    if linha.startswith(b"Content-Length:"):
                        tamanho = int(linha.split(b":")[1])
                        fluxo.readline()
                        recebido.append(fluxo.read(tamanho))

        assistente = threading.Thread(target=assistir, daemon=True)
        assistente.start()
        time.sleep(0.2)
        for quadro in (b"\xff\xd8primeiro", b"\xff\xd8segundo"):
            self.servidor.publicar_imagem(quadro)
            time.sleep(0.15)
        assistente.join(5)
        self.assertEqual(recebido, ["multipart/x-mixed-replace; boundary=quadro", b"\xff\xd8primeiro", b"\xff\xd8segundo"])

    def test_parar_encerra_a_transmissao(self):
        terminou = threading.Event()

        def assistir():
            try:
                with urllib.request.urlopen(self.url + "api/camera.mjpg", timeout=5) as fluxo:
                    fluxo.read()
            except OSError:
                pass
            terminou.set()

        threading.Thread(target=assistir, daemon=True).start()
        time.sleep(0.2)
        self.servidor.parar()
        self.assertTrue(terminou.wait(3))

    def test_tela_fechada_no_meio_da_transmissao(self):
        fluxo = urllib.request.urlopen(self.url + "api/camera.mjpg", timeout=5)
        self.servidor.publicar_imagem(b"\xff\xd8a")
        time.sleep(0.1)
        fluxo.close()
        for numero in range(20):
            self.servidor.publicar_imagem(b"\xff\xd8" + bytes([numero]) * 70000)
            time.sleep(0.02)
        # Chegar aqui sem o servidor travar e o que se testa.
        self.assertEqual(self.pedir_estado()["peca"]["tipo"], "T")

    def pedir_estado(self):
        with urllib.request.urlopen(self.url + "api/estado", timeout=5) as resposta:
            return json.loads(resposta.read())


class EventoContado:
    """Um `threading.Event` que se arma sozinho depois de algumas esperas."""

    def __init__(self, esperas: int):
        self.esperas = esperas

    def is_set(self):
        return self.esperas <= 0

    def wait(self, _segundos):
        self.esperas -= 1


class TestSemCamera(unittest.TestCase):
    def test_laco_anda_o_tempo_e_publica_a_30_por_segundo(self):
        partida = partida_parada()
        publicados = []
        servidor = type("Falso", (), {"publicar": lambda self, retrato: publicados.append(retrato)})()
        tempos = iter(i / 60 for i in range(10_000))
        rodar_sem_camera(partida, servidor, EventoContado(120), relogio=lambda: next(tempos))
        self.assertEqual(partida.jogo.peca.linha, 6)  # dois segundos de jogo
        self.assertAlmostEqual(len(publicados), 60, delta=2)


class TestJanela(unittest.TestCase):
    def test_abre_a_janela_e_desce_tudo_ao_fechar(self):
        from unittest import mock

        from autodoc.gestos import servidor_tetris

        vistos = {}

        def abrir(url, titulo):
            # Com a janela "aberta", o servidor responde e o jogo anda.
            with urllib.request.urlopen(url + "api/estado", timeout=5) as resposta:
                vistos["estado"] = json.loads(resposta.read())
            vistos["titulo"] = titulo
            return "nativa"

        with mock.patch("autodoc.web.janela.abrir", side_effect=abrir):
            self.assertEqual(servidor_tetris.jogar_pelo_teclado(porta=18768), 0)
        self.assertEqual(vistos["titulo"], "AutoDoc — Tetris")
        self.assertFalse(vistos["estado"]["camera"])
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen("http://127.0.0.1:18768/api/estado", timeout=1)


if __name__ == "__main__":
    unittest.main()
