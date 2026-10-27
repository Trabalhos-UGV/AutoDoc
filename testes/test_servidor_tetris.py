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


if __name__ == "__main__":
    unittest.main()
