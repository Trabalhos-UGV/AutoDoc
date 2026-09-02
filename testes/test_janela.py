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
import logging
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


class TestSondagemSilenciosa(unittest.TestCase):
    """Procurar motor e falhar é uma resposta, não um defeito.

    Ao procurar, o pywebview tenta GTK e depois Qt e registra cada tentativa
    com `logger.exception` — duas pilhas completas. Num Linux sem WebKitGTK
    isso enchia a tela de traceback para depois cair no navegador e funcionar,
    e quem via concluía que o programa tinha quebrado.
    """

    def test_sem_motor_devolve_o_motivo(self):
        falso = webview_falso()
        falso.initialize = mock.Mock(side_effect=RuntimeError("nem GTK nem Qt"))

        motivo = janela._ha_motor_grafico(falso)
        self.assertIn("RuntimeError", motivo)
        self.assertIn("nem GTK nem Qt", motivo)

    def test_com_motor_nao_devolve_motivo(self):
        falso = webview_falso()
        falso.initialize = mock.Mock()
        self.assertIsNone(janela._ha_motor_grafico(falso))

    def test_pywebview_sem_sondagem_nao_atrapalha(self):
        """Versão que não expõe `initialize`: segue o caminho antigo."""
        falso = webview_falso()
        del falso.initialize
        self.assertIsNone(janela._ha_motor_grafico(falso))

    def test_a_sondagem_nao_deixa_traceback_na_tela(self):
        registro = logging.getLogger("pywebview")

        def sondar_ruidoso():
            try:
                raise ModuleNotFoundError("No module named 'gi'")
            except ModuleNotFoundError:
                registro.exception("GTK cannot be loaded")
            raise RuntimeError("You must have either QT or GTK")

        falso = webview_falso()
        falso.initialize = sondar_ruidoso

        capturado = io.StringIO()
        manipulador = logging.StreamHandler(capturado)
        raiz = logging.getLogger()
        raiz.addHandler(manipulador)
        self.addCleanup(raiz.removeHandler, manipulador)

        janela._ha_motor_grafico(falso)
        self.assertNotIn("Traceback", capturado.getvalue())
        self.assertNotIn("GTK cannot be loaded", capturado.getvalue())

    def test_o_log_do_pywebview_e_devolvido_ao_normal(self):
        """Calar durante a sondagem não pode calar para sempre."""
        registro = logging.getLogger("pywebview")
        nivel, propaga = registro.level, registro.propagate

        falso = webview_falso()
        falso.initialize = mock.Mock(side_effect=RuntimeError("sem motor"))
        janela._ha_motor_grafico(falso)

        self.assertEqual(registro.level, nivel)
        self.assertEqual(registro.propagate, propaga)


class TestReceitaDoMotor(unittest.TestCase):
    """No Linux, o motor da janela vem do sistema — não do pip.

    Mandar `pip install -r requirements.txt` lá é conselho errado: as
    dependências Python já estão instaladas, e quem tenta `pywebview[gtk]` cai
    na compilação do PyGObject.
    """

    def receita_com(self, plataforma, gerenciador):
        def which(nome):
            return f"/usr/bin/{nome}" if nome == gerenciador else None

        with mock.patch.object(janela.sys, "platform", plataforma), \
             mock.patch.object(janela.shutil, "which", which):
            return janela.receita_do_motor()

    def test_fora_do_linux_nao_ha_receita(self):
        for plataforma in ("darwin", "win32"):
            with self.subTest(plataforma=plataforma):
                self.assertIsNone(self.receita_com(plataforma, "pacman"))

    def test_reconhece_a_familia_pelo_gerenciador_de_pacotes(self):
        esperado = {
            "pacman": ("Arch", "python-gobject"),
            "apt": ("Debian", "python3-gi"),
            "dnf": ("Fedora", "python3-gobject"),
            "zypper": ("openSUSE", "python3-gobject"),
        }
        for gerenciador, (familia, pacote) in esperado.items():
            with self.subTest(gerenciador=gerenciador):
                achado = self.receita_com("linux", gerenciador)
                self.assertIsNotNone(achado)
                self.assertIn(familia, achado[0])
                self.assertIn(pacote, achado[1])
                self.assertIn(gerenciador, achado[1])

    def test_linux_sem_gerenciador_conhecido(self):
        self.assertIsNone(self.receita_com("linux", "gerenciador-exotico"))

    def test_nenhuma_receita_manda_compilar_o_pygobject(self):
        """Era esse o beco: `pywebview[gtk]` compila e falha sem os headers."""
        for _, comando in janela.PACOTES_DO_MOTOR.values():
            with self.subTest(comando=comando):
                self.assertNotIn("pip", comando)


class TestComoResolver(unittest.TestCase):
    def instrucao(self, plataforma, gerenciador=None):
        def which(nome):
            return f"/usr/bin/{nome}" if nome == gerenciador else None

        with mock.patch.object(janela.sys, "platform", plataforma), \
             mock.patch.object(janela.shutil, "which", which):
            return janela._como_resolver()

    def test_arch_recebe_o_comando_do_pacman(self):
        texto = self.instrucao("linux", "pacman")
        self.assertIn("sudo pacman -S python-gobject webkit2gtk-4.1", texto)
        self.assertIn("pywebview[gtk]", texto, "tem que avisar o que NÃO fazer")

    def test_linux_desconhecido_recebe_a_orientacao_generica(self):
        texto = self.instrucao("linux")
        self.assertIn("PyGObject", texto)
        self.assertIn("gerenciador de pacotes", texto)
        self.assertNotIn("pip install", texto)

    def test_fora_do_linux_o_conselho_continua_sendo_o_pip(self):
        texto = self.instrucao("darwin")
        self.assertIn("pip install -r requirements.txt", texto)


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

    def test_no_linux_a_mensagem_ensina_o_pacote_do_sistema(self):
        """A mensagem que teria evitado a compilação do PyGObject."""
        falso = webview_falso(RuntimeError("You must have either QT or GTK"))

        def which(nome):
            return "/usr/bin/pacman" if nome == "pacman" else None

        with com_pywebview(falso), \
             mock.patch.object(janela.sys, "platform", "linux"), \
             mock.patch.object(janela.shutil, "which", which), \
             mock.patch.object(janela.webbrowser, "open"), \
             self.assertLogs("autodoc.web.janela", "WARNING"):
            resultado, saida = self.abrir()

        self.assertEqual(resultado, "navegador")
        self.assertIn("sudo pacman -S", saida)
        self.assertNotIn("pip install -r requirements.txt", saida)

    def test_sem_motor_cai_no_navegador_sem_criar_janela(self):
        """Descoberto antes de abrir: nem chega a montar uma janela natimorta."""
        falso = webview_falso()
        falso.initialize = mock.Mock(side_effect=RuntimeError("nem GTK nem Qt"))

        with com_pywebview(falso), \
             mock.patch.object(janela.webbrowser, "open") as navegador, \
             self.assertLogs("autodoc.web.janela", "WARNING"):
            resultado, _ = self.abrir()

        self.assertEqual(resultado, "navegador")
        navegador.assert_called_once()
        falso.create_window.assert_not_called()
        falso.start.assert_not_called()

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
    def test_entrega_a_janela_criada_a_quem_pediu(self):
        """O instalador precisa da referência para abrir o seletor de pastas."""
        falso = webview_falso()
        recebida = []

        with com_pywebview(falso):
            janela.abrir("http://x/", ao_criar=recebida.append)

        self.assertEqual(len(recebida), 1)
        self.assertIs(recebida[0], falso.create_window.return_value)

    def test_o_minimo_e_o_fundo_podem_ser_escolhidos(self):
        """O instalador usa uma janela menor e um fundo diferente do app."""
        falso = webview_falso()
        with com_pywebview(falso):
            janela.abrir("http://x/", minimo=(820, 640), fundo="#16140f")

        opcoes = falso.create_window.call_args.kwargs
        self.assertEqual(opcoes["min_size"], (820, 640))
        self.assertEqual(opcoes["background_color"], "#16140f")

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
