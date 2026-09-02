"""O `instalar.py` — o script que roda com o Python do sistema.

É a primeira coisa que um integrante do grupo executa depois do `git clone`, e
onde a instalação no Linux quebrava: a parte gráfica falhando levava a
instalação inteira junto.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import instalar


class TestOpcoesDoVenv(unittest.TestCase):
    """No Linux o venv precisa enxergar os pacotes do sistema."""

    def opcoes_em(self, plataforma):
        with mock.patch.object(instalar.sys, "platform", plataforma):
            return instalar.opcoes_do_venv()

    def test_linux(self):
        self.assertEqual(self.opcoes_em("linux"), ["--system-site-packages"])
        self.assertEqual(self.opcoes_em("linux2"), ["--system-site-packages"])

    def test_macos_e_windows_ficam_isolados(self):
        self.assertEqual(self.opcoes_em("darwin"), [])
        self.assertEqual(self.opcoes_em("win32"), [])


class TestAbrirVenvAoSistema(unittest.TestCase):
    """Um venv criado antes da correção continua isolado.

    No Linux é isso que impede o pywebview de achar o `gi` instalado pelo
    gerenciador da distribuição. O conserto pedia apagar o venv e recomeçar —
    um passo fácil de esquecer e chato de descobrir. Virar a chave no
    `pyvenv.cfg`, que o interpretador lê a cada partida, faz o mesmo efeito sem
    reinstalar nada.
    """

    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.venv = Path(self._temporaria.name) / "venv"
        self.venv.mkdir()
        self.configuracao = self.venv / "pyvenv.cfg"
        self.addCleanup(self._temporaria.cleanup)

    def chave(self) -> str | None:
        for linha in self.configuracao.read_text(encoding="utf-8").splitlines():
            nome, separador, valor = linha.partition("=")
            if separador and nome.strip() == instalar.CHAVE_SISTEMA:
                return valor.strip()
        return None

    def test_venv_isolado_passa_a_enxergar_o_sistema(self):
        self.configuracao.write_text(
            "home = /usr/bin\ninclude-system-site-packages = false\nversion = 3.14.0\n",
            encoding="utf-8")

        self.assertTrue(instalar.abrir_venv_ao_sistema(self.venv))
        self.assertEqual(self.chave(), "true")

    def test_nao_mexe_no_que_ja_esta_certo(self):
        self.configuracao.write_text(
            "include-system-site-packages = true\n", encoding="utf-8")
        self.assertFalse(instalar.abrir_venv_ao_sistema(self.venv))

    def test_e_idempotente(self):
        self.configuracao.write_text(
            "include-system-site-packages = false\n", encoding="utf-8")
        self.assertTrue(instalar.abrir_venv_ao_sistema(self.venv))
        self.assertFalse(instalar.abrir_venv_ao_sistema(self.venv))

    def test_arquivo_sem_a_chave_ganha_a_chave(self):
        self.configuracao.write_text("home = /usr/bin\nversion = 3.14.0\n",
                                     encoding="utf-8")
        self.assertTrue(instalar.abrir_venv_ao_sistema(self.venv))
        self.assertEqual(self.chave(), "true")

    def test_preserva_as_outras_linhas(self):
        """O `home` e o `version` são o que faz o venv funcionar."""
        self.configuracao.write_text(
            "home = /usr/bin\ninclude-system-site-packages = false\n"
            "version = 3.14.0\nexecutable = /usr/bin/python3.14\n", encoding="utf-8")

        instalar.abrir_venv_ao_sistema(self.venv)
        texto = self.configuracao.read_text(encoding="utf-8")
        self.assertIn("home = /usr/bin", texto)
        self.assertIn("version = 3.14.0", texto)
        self.assertIn("executable = /usr/bin/python3.14", texto)

    def test_sem_pyvenv_cfg_nao_faz_nada(self):
        self.assertFalse(instalar.abrir_venv_ao_sistema(self.venv / "inexistente"))


class TestPythonDoVenv(unittest.TestCase):
    def test_caminho_por_sistema(self):
        casos = [("win32", "Scripts"), ("darwin", "bin"), ("linux", "bin")]
        for plataforma, pasta in casos:
            with self.subTest(plataforma=plataforma), \
                 mock.patch.object(instalar.sys, "platform", plataforma):
                self.assertEqual(instalar.python_do_venv().parent.name, pasta)


class TestUltimaLinha(unittest.TestCase):
    def test_pega_a_linha_que_diz_o_que_aconteceu(self):
        saida = "Collecting pygobject\nBuilding wheel ... error\nERROR: girepository not found"
        self.assertEqual(instalar._ultima_linha(saida), "ERROR: girepository not found")

    def test_ignora_linhas_em_branco(self):
        self.assertEqual(instalar._ultima_linha("erro real\n\n   \n"), "erro real")

    def test_saida_vazia(self):
        self.assertEqual(instalar._ultima_linha(""), "sem detalhes")
        self.assertEqual(instalar._ultima_linha(None), "sem detalhes")


class BasePreparo(unittest.TestCase):
    """Encena o `preparar_ambiente()` sem criar venv nem baixar nada."""

    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.base = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)
        self.python = self.base / "venv" / "bin" / "python"
        self.chamadas = []

    def encenar(self, *, venv_existe=True, tem=(), pip_essenciais=0, pip_completo=0,
                erro_completo=""):
        """`tem` lista os módulos que já estão instalados no venv fingido."""
        def run(cmd, **kwargs):
            argumentos = [str(c) for c in cmd]
            self.chamadas.append(argumentos)

            if "-c" in argumentos:
                pedidos = argumentos[argumentos.index("-c") + 1]
                falta = [m.strip() for m in pedidos.replace("import", "").split(",")
                         if m.strip() not in tem]
                return SimpleNamespace(returncode=1 if falta else 0, stdout="", stderr="")

            alvo = argumentos[-1]
            if "requirements-essenciais" in alvo:
                return SimpleNamespace(returncode=pip_essenciais, stdout="", stderr="")
            if "requirements.txt" in alvo:
                return SimpleNamespace(returncode=pip_completo, stdout="",
                                       stderr=erro_completo)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        saida = io.StringIO()
        with mock.patch.object(instalar, "python_do_venv", return_value=self.python), \
             mock.patch.object(Path, "exists", return_value=venv_existe), \
             mock.patch.object(subprocess, "run", run), \
             contextlib.redirect_stdout(saida):
            devolvido = instalar.preparar_ambiente()
        return devolvido, saida.getvalue()

    def arquivos_pedidos(self) -> list[str]:
        return [c[-1] for c in self.chamadas if c[-1].endswith(".txt")]


class TestPrepararAmbiente(BasePreparo):
    def test_tudo_instalado_nao_chama_o_pip(self):
        _, saida = self.encenar(tem=("watchdog", "pypdf", "webview", "pytesseract"))
        self.assertEqual(self.arquivos_pedidos(), [])
        self.assertEqual(saida, "")

    def test_venv_antigo_do_linux_e_ajustado(self):
        """O caso de quem já tinha instalado antes da correção."""
        with mock.patch.object(instalar.sys, "platform", "linux"), \
             mock.patch.object(instalar, "abrir_venv_ao_sistema",
                               return_value=True) as ajustou:
            _, saida = self.encenar(tem=("watchdog", "pypdf", "webview", "pytesseract"))

        ajustou.assert_called_once()
        self.assertIn("enxergar os pacotes do sistema", saida)

    def test_fora_do_linux_o_venv_nao_e_mexido(self):
        with mock.patch.object(instalar.sys, "platform", "darwin"), \
             mock.patch.object(instalar, "abrir_venv_ao_sistema") as ajustou:
            self.encenar(tem=("watchdog", "pypdf", "webview", "pytesseract"))
        ajustou.assert_not_called()

    def test_venv_ausente_e_criado_com_as_opcoes_da_plataforma(self):
        with mock.patch.object(instalar.sys, "platform", "linux"):
            self.encenar(venv_existe=False,
                         tem=("watchdog", "pypdf", "webview", "pytesseract"))

        criacao = next(c for c in self.chamadas if "venv" in c)
        self.assertIn("--system-site-packages", criacao)

    def test_instala_os_essenciais_primeiro(self):
        self.encenar(tem=())
        pedidos = self.arquivos_pedidos()
        self.assertTrue(pedidos[0].endswith("requirements-essenciais.txt"))
        self.assertTrue(pedidos[1].endswith("requirements.txt"))

    def test_so_os_opcionais_faltando(self):
        self.encenar(tem=("watchdog", "pypdf"))
        pedidos = self.arquivos_pedidos()
        self.assertEqual(len(pedidos), 1)
        self.assertTrue(pedidos[0].endswith("requirements.txt"))


class TestParteGraficaOpcional(BasePreparo):
    """O defeito do Linux: a janela nativa derrubando a instalação inteira."""

    ERRO_DO_ARCH = ("Building wheel for pygobject (pyproject.toml) ... error\n"
                    "ERROR: Dependency 'girepository-2.0' not found, tried pkgconfig")

    def test_pip_da_parte_grafica_falhando_nao_levanta(self):
        devolvido, saida = self.encenar(tem=("watchdog", "pypdf"), pip_completo=1,
                                        erro_completo=self.ERRO_DO_ARCH)

        self.assertEqual(devolvido, self.python)
        self.assertIn("funciona assim mesmo", saida)

    def test_mostra_o_motivo_verdadeiro(self):
        _, saida = self.encenar(tem=("watchdog", "pypdf"), pip_completo=1,
                                erro_completo=self.ERRO_DO_ARCH)
        self.assertIn("girepository-2.0", saida)

    def test_avisa_que_as_telas_abrem_no_navegador(self):
        _, saida = self.encenar(tem=("watchdog", "pypdf"), pip_completo=1,
                                erro_completo=self.ERRO_DO_ARCH)
        self.assertIn("navegador", saida)

    def test_os_essenciais_falhando_continuam_interrompendo(self):
        """Sem watchdog e pypdf não há programa; aí parar é o certo."""
        def run(cmd, **kwargs):
            argumentos = [str(c) for c in cmd]
            if "-c" in argumentos:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            raise subprocess.CalledProcessError(1, argumentos)

        with mock.patch.object(instalar, "python_do_venv", return_value=self.python), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(subprocess, "run", run), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                instalar.preparar_ambiente()


class TestMain(unittest.TestCase):
    def rodar(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = instalar.main()
        return codigo, saida.getvalue()

    def test_recusa_python_velho_demais(self):
        """O `/usr/bin/python3` de muitos sistemas ainda é 3.9."""
        from collections import namedtuple
        Versao = namedtuple("Versao", "major minor micro releaselevel serial")

        with mock.patch.object(instalar.sys, "version_info", Versao(3, 9, 6, "final", 0)):
            codigo, saida = self.rodar()

        self.assertEqual(codigo, 1)
        self.assertIn("3.10", saida)
        self.assertIn("3.9.6", saida)

    def test_ambiente_que_nao_prepara_e_avisado(self):
        erro = subprocess.CalledProcessError(1, ["python", "-m", "venv"])
        with mock.patch.object(instalar, "preparar_ambiente", side_effect=erro):
            codigo, saida = self.rodar()

        self.assertEqual(codigo, 1)
        self.assertIn("Não foi possível preparar o ambiente", saida)

    def test_entrega_o_comando_ao_python_do_venv(self):
        with mock.patch.object(instalar, "preparar_ambiente",
                               return_value=Path("/tmp/venv/bin/python")), \
             mock.patch.object(subprocess, "run",
                               return_value=SimpleNamespace(returncode=0)) as rodou:
            self.assertEqual(instalar.main(), 0)

        comando = [str(c) for c in rodou.call_args.args[0]]
        self.assertEqual(comando[0], "/tmp/venv/bin/python")
        self.assertIn("autodoc.instalacao.principal", comando)


if __name__ == "__main__":
    unittest.main()
