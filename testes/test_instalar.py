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

    def test_sem_argumento_usa_o_venv_do_projeto_daquele_momento(self):
        """Um padrão no parâmetro ficaria preso ao VENV da hora do import."""
        self.configuracao.write_text(
            "include-system-site-packages = false\n", encoding="utf-8")

        with mock.patch.object(instalar, "VENV", self.venv):
            self.assertTrue(instalar.abrir_venv_ao_sistema())
        self.assertEqual(self.chave(), "true")


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
    def setUp(self):
        # Nenhum teste pode instalar programa de verdade na maquina de quem roda.
        self.programas = self.enterContext(mock.patch.object(
            instalar, "instalar_programas_do_sistema", return_value=[]))

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
        self.programas.assert_called_once()


def resultado(codigo=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=codigo, stdout=stdout, stderr=stderr)


class BaseProgramas(unittest.TestCase):
    """Todo comando e dublado: o que se confere e o que teria sido rodado."""

    def setUp(self):
        self.rodados: list[list[str]] = []
        self.falhar: set[str] = set()
        self.enterContext(mock.patch.object(subprocess, "run", self.dublar))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self._temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)

    def dublar(self, comando, *args, **kwargs):
        comando = [str(c) for c in comando]
        self.rodados.append(comando)
        texto = " ".join(comando)
        return resultado(1 if any(f in texto for f in self.falhar) else 0)

    def no(self, plataforma, which=None, **extras):
        caminhos = which or {}
        contextos = [
            mock.patch.object(instalar.sys, "platform", plataforma),
            mock.patch.object(instalar.shutil, "which", lambda nome: caminhos.get(nome)),
        ]
        for nome, valor in extras.items():
            contextos.append(mock.patch.object(instalar, nome, valor))
        pilha = contextlib.ExitStack()
        for contexto in contextos:
            pilha.enter_context(contexto)
        self.addCleanup(pilha.close)

    def faltando(self, tesseract=True, ocr=True, janela=False):
        return {"tesseract": tesseract, "ocr": ocr, "janela": janela}


class TestOQueFalta(BaseProgramas):
    def test_tudo_instalado_nao_instala_nada(self):
        self.no("darwin", o_que_falta=lambda: self.faltando(False, False))
        self.assertEqual(instalar.instalar_programas_do_sistema(), [])
        self.assertEqual(self.rodados, [])

    def test_le_portugues_pela_lista_de_idiomas(self):
        with mock.patch.object(subprocess, "run",
                               return_value=resultado(stdout="List of languages:\neng\npor\n")):
            self.assertTrue(instalar.le_portugues("tesseract"))
        with mock.patch.object(subprocess, "run", return_value=resultado(stderr="eng\nosd")):
            self.assertFalse(instalar.le_portugues("tesseract"))

    def test_o_portugues_baixado_no_windows_conta(self):
        (self.pasta / "por.traineddata").touch()
        self.no("win32", tessdata_do_usuario=lambda: self.pasta)
        with mock.patch.object(subprocess, "run", return_value=resultado(stdout="por")) as rodou:
            self.assertTrue(instalar.le_portugues("tesseract.exe"))
        self.assertEqual(rodou.call_args.kwargs["env"]["TESSDATA_PREFIX"], str(self.pasta))

    def test_acha_o_tesseract_fora_do_path_no_windows(self):
        (self.pasta / "tesseract.exe").touch()
        self.no("win32", PASTAS_TESSERACT_WINDOWS=(self.pasta / "nada", self.pasta))
        self.assertEqual(instalar.achar_tesseract(), str(self.pasta / "tesseract.exe"))
        self.no("darwin")
        self.assertIsNone(instalar.achar_tesseract())
        self.no("linux", which={"tesseract": "/usr/bin/tesseract"})
        self.assertEqual(instalar.achar_tesseract(), "/usr/bin/tesseract")

    def test_o_que_falta_junta_as_tres_perguntas(self):
        self.no("linux", achar_tesseract=lambda: "/usr/bin/tesseract",
                le_portugues=lambda _: False, tem_motor_da_janela=lambda: True)
        self.assertEqual(instalar.o_que_falta(),
                         {"tesseract": False, "ocr": True, "janela": False})

    def test_motor_da_janela_aceita_o_webkit_antigo(self):
        self.falhar = {"'4.1'"}
        self.assertTrue(instalar.tem_motor_da_janela())
        self.falhar = {"'4.1'", "'4.0'"}
        self.assertFalse(instalar.tem_motor_da_janela())

    def test_pasta_do_portugues_no_windows(self):
        with mock.patch.dict(instalar.os.environ, {"LOCALAPPDATA": "C:/Local"}):
            self.assertEqual(instalar.tessdata_do_usuario(),
                             Path("C:/Local") / "AutoDoc" / "tessdata")
        with mock.patch.dict(instalar.os.environ, {}, clear=True):
            self.assertEqual(instalar.tessdata_do_usuario(),
                             Path.home() / "AppData" / "Local" / "AutoDoc" / "tessdata")

    def test_sistema_desconhecido_avisa_e_segue(self):
        self.no("sunos5", o_que_falta=lambda: self.faltando())
        self.assertTrue(instalar.instalar_programas_do_sistema())


class TestLinux(BaseProgramas):
    def instalar(self, gerenciador, faltando, root=False):
        self.no("linux", which={gerenciador: f"/usr/bin/{gerenciador}", "sudo": "/usr/bin/sudo"},
                o_que_falta=lambda: faltando)
        with mock.patch.object(instalar.os, "geteuid", return_value=0 if root else 1000, create=True):
            return instalar.instalar_programas_do_sistema()

    def test_arch_instala_ocr_e_janela_de_uma_vez_com_sudo(self):
        pendente = self.instalar("pacman", self.faltando(janela=True))
        self.assertEqual(pendente, [])
        self.assertEqual(self.rodados, [["sudo", "pacman", "-S", "--needed", "--noconfirm",
                                         "tesseract", "tesseract-data-por",
                                         "python-gobject", "webkit2gtk-4.1"]])

    def test_so_o_que_falta(self):
        self.instalar("dnf", self.faltando(tesseract=False, ocr=False, janela=True))
        self.assertEqual(self.rodados[-1][-2:], ["python3-gobject", "webkit2gtk4.1"])

    def test_como_root_nao_precisa_de_sudo(self):
        self.instalar("zypper", self.faltando(), root=True)
        self.assertEqual(self.rodados[0][0], "zypper")

    def test_ubuntu_atualiza_a_lista_e_cai_no_webkit_antigo(self):
        self.falhar = {"webkit2-4.1"}
        pendente = self.instalar("apt-get", self.faltando(janela=True))

        self.assertEqual(pendente, [])
        self.assertEqual(self.rodados[0], ["sudo", "apt-get", "update"])
        self.assertIn("gir1.2-webkit2-4.0", self.rodados[-1])

    def test_falha_diz_o_comando_para_fazer_a_mao(self):
        self.falhar = {"pacman"}
        pendente = self.instalar("pacman", self.faltando())
        self.assertIn("sudo pacman", pendente[0])

    def test_distribuicao_sem_gerenciador_conhecido(self):
        self.no("linux", o_que_falta=lambda: self.faltando())
        self.assertIn("gerenciador", instalar.instalar_programas_do_sistema()[0])

    def test_os_pacotes_da_janela_sao_os_que_a_janela_recomenda(self):
        """Repetidos de propósito, porque este arquivo não importa o pacote."""
        from autodoc.web.janela import PACOTES_DO_MOTOR

        recomendados = " ".join(comando for _, comando in PACOTES_DO_MOTOR.values())
        for _, _, pacotes in instalar.GERENCIADORES_LINUX.values():
            for pacote in pacotes:
                self.assertIn(pacote, recomendados)

    def test_comando_que_nem_existe_e_falha_e_nao_excecao(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("sudo")):
            self.assertFalse(instalar._rodar(["sudo", "nada"]))


class TestMacOS(BaseProgramas):
    def test_com_homebrew_instala_tesseract_e_idiomas(self):
        self.no("darwin", which={"brew": "/opt/homebrew/bin/brew"},
                o_que_falta=lambda: self.faltando())
        self.assertEqual(instalar.instalar_programas_do_sistema(), [])
        self.assertEqual(self.rodados,
                         [["/opt/homebrew/bin/brew", "install", "tesseract", "tesseract-lang"]])

    def test_brew_fora_do_path_tambem_e_achado(self):
        brew = self.pasta / "brew"
        brew.touch()
        self.no("darwin", BREW=(str(self.pasta / "nada"), str(brew)))
        self.assertEqual(instalar._achar_brew(), str(brew))

    def test_brew_que_falha(self):
        self.falhar = {"brew install"}
        self.no("darwin", which={"brew": "/opt/homebrew/bin/brew"},
                o_que_falta=lambda: self.faltando())
        self.assertIn("brew install", instalar.instalar_programas_do_sistema()[0])

    def test_sem_homebrew_pergunta_antes_de_instalar(self):
        self.no("darwin", o_que_falta=lambda: self.faltando(), perguntar=lambda _: False, BREW=())
        pendente = instalar.instalar_programas_do_sistema()
        self.assertIn("brew.sh", pendente[0])
        self.assertEqual(self.rodados, [])

    def test_aceitando_instala_o_homebrew_e_depois_o_tesseract(self):
        achados = iter([None, "/opt/homebrew/bin/brew"])
        self.no("darwin", o_que_falta=lambda: self.faltando(), perguntar=lambda _: True,
                _achar_brew=lambda: next(achados))
        self.assertEqual(instalar.instalar_programas_do_sistema(), [])
        self.assertEqual(self.rodados[0][:2], ["curl", "-fsSL"])
        self.assertEqual(self.rodados[1][:2], ["/bin/bash", "-c"])
        self.assertEqual(self.rodados[2][1:], ["install", "tesseract", "tesseract-lang"])

    def test_homebrew_que_nao_instala(self):
        self.falhar = {"curl"}
        self.no("darwin", o_que_falta=lambda: self.faltando(), perguntar=lambda _: True,
                _achar_brew=lambda: None)
        self.assertIn("Homebrew não instalou", instalar.instalar_programas_do_sistema()[0])

    def test_homebrew_instalado_mas_nao_achado(self):
        self.no("darwin", o_que_falta=lambda: self.faltando(), perguntar=lambda _: True,
                _achar_brew=lambda: None)
        self.assertIn("terminal novo", instalar.instalar_programas_do_sistema()[0])


class TestPerguntar(unittest.TestCase):
    def responder(self, texto, terminal=True):
        entrada = mock.Mock(isatty=lambda: terminal)
        with mock.patch.object(instalar.sys, "stdin", entrada), \
             mock.patch("builtins.input", return_value=texto):
            return instalar.perguntar("Instalar?")

    def test_enter_e_sim(self):
        self.assertTrue(self.responder(""))
        self.assertTrue(self.responder("s"))
        self.assertFalse(self.responder("n"))

    def test_sem_terminal_e_nao(self):
        self.assertFalse(self.responder("s", terminal=False))

    def test_entrada_fechada_e_nao(self):
        with mock.patch.object(instalar.sys, "stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(instalar.perguntar("Instalar?"))


class TestWindows(BaseProgramas):
    def preparar(self, tesseract="C:/TO/tesseract.exe", portugues=False, winget=True):
        self.tessdata = self.pasta / "tessdata"
        instalado = self.pasta / "Tesseract-OCR" / "tessdata"
        instalado.mkdir(parents=True)
        (instalado / "eng.traineddata").write_text("ingles", encoding="utf-8")
        executavel = str(self.pasta / "Tesseract-OCR" / "tesseract.exe") if tesseract else None
        self.no("win32", which={"winget": "C:/winget.exe"} if winget else {},
                o_que_falta=lambda: self.faltando(tesseract=executavel is None),
                achar_tesseract=lambda: executavel, le_portugues=lambda _: portugues,
                tessdata_do_usuario=lambda: self.tessdata,
                baixar=lambda url, destino: destino.write_text("por") is not None)

    def test_instala_pelo_winget_e_baixa_o_portugues(self):
        self.preparar(tesseract=None)
        # o winget instala; depois dele o Tesseract aparece
        with mock.patch.object(instalar, "achar_tesseract",
                               return_value=str(self.pasta / "Tesseract-OCR" / "tesseract.exe")):
            self.assertEqual(instalar.instalar_programas_do_sistema(), [])

        self.assertIn(instalar.WINGET_TESSERACT, self.rodados[0])
        self.assertTrue((self.tessdata / "por.traineddata").exists())
        self.assertTrue((self.tessdata / "eng.traineddata").exists(), "o inglês vai junto")

    def test_ja_com_portugues_nao_baixa(self):
        self.preparar(portugues=True)
        with mock.patch.object(instalar, "o_que_falta",
                               return_value=self.faltando(tesseract=False, ocr=True)):
            self.assertEqual(instalar.instalar_programas_do_sistema(), [])
        self.assertFalse(self.tessdata.exists())

    def test_sem_winget(self):
        self.preparar(tesseract=None, winget=False)
        self.assertIn("UB-Mannheim", instalar.instalar_programas_do_sistema()[0])

    def test_winget_que_falha(self):
        self.preparar(tesseract=None)
        self.falhar = {"winget"}
        self.assertIn("winget install", instalar.instalar_programas_do_sistema()[0])

    def test_instalado_mas_nao_achado(self):
        self.preparar(tesseract=None)
        self.assertIn("de novo", instalar.instalar_programas_do_sistema()[0])

    def test_portugues_que_nao_baixa(self):
        self.preparar()
        with mock.patch.object(instalar, "baixar", return_value=False):
            self.assertIn("não baixou", instalar.instalar_programas_do_sistema()[0])


class TestBaixar(BaseProgramas):
    def test_pelo_curl(self):
        self.no("win32", which={"curl": "C:/curl.exe"})
        self.assertTrue(instalar.baixar("https://x/por", self.pasta / "a" / "por"))
        self.assertEqual(self.rodados[0][:3], ["curl", "-fsSL", "-o"])

    def test_sem_curl_pelo_urllib(self):
        self.no("win32")
        with mock.patch.object(instalar.urllib.request, "urlretrieve") as baixou:
            self.assertTrue(instalar.baixar("https://x/por", self.pasta / "por"))
        baixou.assert_called_once()
        with mock.patch.object(instalar.urllib.request, "urlretrieve", side_effect=OSError("rede")):
            self.assertFalse(instalar.baixar("https://x/por", self.pasta / "por"))


if __name__ == "__main__":
    unittest.main()
