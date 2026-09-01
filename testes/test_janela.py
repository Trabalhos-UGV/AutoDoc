"""A janela nativa e a queda para o navegador.

O AutoDoc precisa abrir mesmo onde o webview nativo não existe — é comum no
Linux, que costuma exigir pacote do sistema. Perder a janela própria é aceitável;
o programa não abrir, não é.

`sys.modules["webview"] = None` faz `import webview` levantar `ImportError`, que
é como se simula a ausência do pywebview sem desinstalar nada.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from unittest import mock

from autodoc.web import janela


@contextlib.contextmanager
def sem_pywebview():
    with mock.patch.dict(sys.modules, {"webview": None}):
        yield


@contextlib.contextmanager
def com_pywebview(falso):
    with mock.patch.dict(sys.modules, {"webview": falso}):
        yield


def webview_falso(erro_ao_iniciar: Exception | None = None):
    """Um dublê do pywebview que registra o que recebeu."""
    modulo = mock.MagicMock()
    modulo.FOLDER_DIALOG = 20
    if erro_ao_iniciar:
        modulo.start.side_effect = erro_ao_iniciar
    return modulo


class TestDisponivel(unittest.TestCase):
    def test_com_o_pywebview_instalado(self):
        with com_pywebview(webview_falso()):
            self.assertTrue(janela.disponivel())

    def test_sem_o_pywebview(self):
        with sem_pywebview():
            self.assertFalse(janela.disponivel())

    def test_nao_tenta_abrir_janela_so_para_responder(self):
        """`disponivel()` é uma pergunta, não uma tentativa."""
        falso = webview_falso()
        with com_pywebview(falso):
            janela.disponivel()
        falso.create_window.assert_not_called()
        falso.start.assert_not_called()


class TestQuedaParaONavegador(unittest.TestCase):
    def abrir(self, **kwargs) -> tuple[str, str]:
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            resultado = janela.abrir("http://127.0.0.1:8757/", **kwargs)
        return resultado, saida.getvalue()

    def test_sem_pywebview_abre_no_navegador(self):
        with sem_pywebview(), \
             mock.patch.object(janela.webbrowser, "open") as navegador, \
             self.assertLogs("autodoc.web.janela", "WARNING"):
            resultado, saida = self.abrir()

        self.assertEqual(resultado, "navegador")
        navegador.assert_called_once_with("http://127.0.0.1:8757/")
        self.assertIn("pywebview nao instalado", saida)

    def test_explica_como_resolver(self):
        """Quem cai no navegador precisa saber o que instalar para ter a janela."""
        with sem_pywebview(), mock.patch.object(janela.webbrowser, "open"), \
             self.assertLogs("autodoc.web.janela", "WARNING"):
            _, saida = self.abrir()

        self.assertIn("requirements.txt", saida)
        self.assertIn("http://127.0.0.1:8757/", saida)

    def test_motor_nativo_ausente_tambem_cai_no_navegador(self):
        """O caso do Linux sem os pacotes do GTK: o import passa, o start não."""
        falso = webview_falso(RuntimeError("nenhum motor de webview encontrado"))

        with com_pywebview(falso), \
             mock.patch.object(janela.webbrowser, "open") as navegador, \
             self.assertLogs("autodoc.web.janela", "WARNING"):
            resultado, saida = self.abrir()

        self.assertEqual(resultado, "navegador")
        navegador.assert_called_once()
        self.assertIn("RuntimeError", saida, "o motivo tem que aparecer")
        self.assertIn("nenhum motor de webview", saida)


class TestJanelaNativa(unittest.TestCase):
    def test_abre_a_janela_e_bloqueia_ate_fechar(self):
        falso = webview_falso()
        with com_pywebview(falso):
            self.assertEqual(janela.abrir("http://127.0.0.1:8757/"), "nativa")

        falso.create_window.assert_called_once()
        falso.start.assert_called_once()

    def test_passa_titulo_e_endereco(self):
        falso = webview_falso()
        with com_pywebview(falso):
            janela.abrir("http://127.0.0.1:8757/", titulo="AutoDoc")

        titulo, url = falso.create_window.call_args.args
        self.assertEqual(titulo, "AutoDoc")
        self.assertEqual(url, "http://127.0.0.1:8757/")

    def test_usa_o_tamanho_padrao_e_o_minimo(self):
        falso = webview_falso()
        with com_pywebview(falso):
            janela.abrir("http://127.0.0.1:8757/")

        opcoes = falso.create_window.call_args.kwargs
        self.assertEqual(opcoes["width"], janela.LARGURA_PADRAO)
        self.assertEqual(opcoes["height"], janela.ALTURA_PADRAO)
        self.assertEqual(opcoes["min_size"], janela.TAMANHO_MINIMO)

    def test_tamanho_pode_ser_escolhido(self):
        falso = webview_falso()
        with com_pywebview(falso):
            janela.abrir("http://x/", largura=980, altura=760, redimensionavel=False)

        opcoes = falso.create_window.call_args.kwargs
        self.assertEqual((opcoes["width"], opcoes["height"]), (980, 760))
        self.assertFalse(opcoes["resizable"])

    def test_pinta_o_fundo_escuro_antes_de_desenhar(self):
        """Sem isto a janela pisca branco antes de a tela carregar."""
        falso = webview_falso()
        with com_pywebview(falso):
            janela.abrir("http://x/")

        self.assertEqual(falso.create_window.call_args.kwargs["background_color"],
                         "#110f0b")

    def test_o_minimo_acompanha_o_que_o_layout_aguenta(self):
        self.assertEqual(janela.TAMANHO_MINIMO, (960, 640))
        self.assertLess(janela.TAMANHO_MINIMO[0], janela.LARGURA_PADRAO)


if __name__ == "__main__":
    unittest.main()
