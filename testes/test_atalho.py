"""O atalho do AutoDoc em cada sistema.

É o que separa "um programa que roda" de "um programa instalado". Cada sistema
tem seu formato e nenhum deles usa biblioteca extra — então o que se testa aqui
é o **conteúdo gerado**: o `.app`, o `.desktop` e a chamada do PowerShell.

`criar()` aceita `destino_base`, então nada toca em `~/Applications`.
"""

from __future__ import annotations

import plistlib
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc import __version__
from autodoc.instalacao import atalho


class BaseAtalho(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.base = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)


def osacompile_falso(chamadas: list):
    """Faz o papel do osacompile e do codesign: monta o esqueleto de um applet."""

    def rodar(comando, check, capture_output):
        chamadas.append(comando)
        if comando[0] == "osacompile":
            pacote = Path(comando[comando.index("-o") + 1])
            (pacote / "Contents" / "MacOS").mkdir(parents=True)
            (pacote / "Contents" / "Resources").mkdir(parents=True)
            (pacote / "Contents" / "MacOS" / "applet").write_bytes(b"binario")
            (pacote / "Contents" / "Resources" / "Assets.car").write_bytes(b"catalogo")
            (pacote / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleExecutable": "applet", "CFBundleIconName": "applet", "OSAAppletStayOpen": True,
            }))

    return rodar


class TestMacOS(BaseAtalho):
    """O pacote com applet, que e o caso de qualquer Mac."""

    def setUp(self):
        super().setUp()
        self.chamadas = []
        self.criar()
        self.pacote = self.base / "AutoDoc.app"

    def criar(self):
        with (
            mock.patch.object(atalho.shutil, "which", side_effect=lambda nome: f"/usr/bin/{nome}"),
            mock.patch.object(atalho.subprocess, "run", side_effect=osacompile_falso(self.chamadas)),
        ):
            self.resultado = atalho._criar_macos(self.base)

    def plist(self):
        return plistlib.loads((self.pacote / "Contents" / "Info.plist").read_bytes())

    def test_monta_o_applet_e_assina_depois(self):
        self.assertTrue(self.resultado.criado)
        osacompile, codesign = self.chamadas
        self.assertEqual(osacompile[:3], ["osacompile", "-s", "-o"])  # -s: fica aberto, vigiando
        self.assertIn("abrir.sh", osacompile[-1])
        self.assertEqual(codesign[:4], ["codesign", "--force", "--deep", "--sign"])

    def test_info_plist(self):
        dados = self.plist()
        self.assertEqual(dados["CFBundleName"], "AutoDoc")
        self.assertEqual(dados["CFBundleIdentifier"], "br.edu.ugv.autodoc")
        self.assertEqual(dados["CFBundleExecutable"], "applet")
        self.assertEqual(dados["CFBundleShortVersionString"], __version__)
        self.assertTrue(dados["OSAAppletStayOpen"])  # o que o osacompile pos continua la
        # O applet e invisivel: quem aparece no Dock e a janela.
        self.assertTrue(dados["LSUIElement"])

    def test_declara_a_camera(self):
        """Sem o motivo declarado, o macOS recusa a camera em silencio."""
        self.assertIn("câmera", self.plist()["NSCameraUsageDescription"])

    def test_o_icone_e_o_do_autodoc_e_nao_o_do_applescript(self):
        self.assertNotIn("CFBundleIconName", self.plist())
        self.assertFalse((self.pacote / "Contents" / "Resources" / "Assets.car").exists())
        if (atalho.RECURSOS / "autodoc.icns").exists():
            self.assertGreater((self.pacote / "Contents" / "Resources" / "applet.icns").stat().st_size, 0)

    def test_script_de_abertura(self):
        """O icone e clicado meses depois, de qualquer lugar do sistema."""
        abrir = self.pacote / "Contents" / "Resources" / "abrir.sh"
        self.assertTrue(abrir.stat().st_mode & stat.S_IXUSR)
        texto = abrir.read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("#!/bin/bash"))
        self.assertIn(f'cd "{atalho.RAIZ}"', texto)
        self.assertIn("main.py app", texto)
        self.assertIn("venv/bin/python", texto)
        # Sem isto o macOS abria o app pelo Rosetta e o numpy nao carregava.
        self.assertIn("hw.optional.arm64", texto)
        self.assertIn("exec arch -arm64", texto)
        # A janela usa isto para aparecer como AutoDoc no Dock.
        self.assertIn("export AUTODOC_PELO_ICONE=1", texto)

    def test_rodar_de_novo_refaz_o_pacote(self):
        """A instalacao e idempotente; o atalho tambem precisa ser."""
        (self.pacote / "Contents" / "Resources" / "sobra.txt").write_text("de antes")
        self.criar()
        self.assertTrue(self.resultado.criado)
        self.assertFalse((self.pacote / "Contents" / "Resources" / "sobra.txt").exists())

    def test_nao_apaga_um_autodoc_app_de_outra_pessoa(self):
        (self.pacote / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.outro.app"}))
        self.criar()
        self.assertFalse(self.resultado.criado)
        self.assertEqual(self.plist()["CFBundleIdentifier"], "com.outro.app")

    def test_pacote_quebrado_nao_e_considerado_nosso(self):
        (self.pacote / "Contents" / "Info.plist").write_bytes(b"nao e plist")
        self.assertFalse(atalho._e_nosso(self.pacote))

    def test_sem_icone_o_pacote_ainda_e_criado(self):
        with mock.patch.object(atalho, "RECURSOS", self.base / "nao-existe"):
            self.criar()
        self.assertTrue(self.resultado.criado)


class TestMacOSSemOsacompile(BaseAtalho):
    """Fora do Mac (montando o pacote no Linux, por exemplo) fica o lancador de script."""

    def setUp(self):
        super().setUp()
        with mock.patch.object(atalho.shutil, "which", return_value=None):
            self.resultado = atalho._criar_macos(self.base)
        self.pacote = self.base / "AutoDoc.app"

    def test_executavel_e_o_script(self):
        lancador = self.pacote / "Contents" / "MacOS" / "AutoDoc"
        self.assertTrue(lancador.stat().st_mode & stat.S_IXUSR)
        self.assertIn("main.py app", lancador.read_text(encoding="utf-8"))
        dados = plistlib.loads((self.pacote / "Contents" / "Info.plist").read_bytes())
        self.assertEqual(dados["CFBundleExecutable"], "AutoDoc")
        self.assertIn("câmera", dados["NSCameraUsageDescription"])
        self.assertNotIn("LSUIElement", dados)


@unittest.skipUnless(sys.platform == "darwin" and atalho.shutil.which("osacompile"), "so num Mac")
class TestMacOSDeVerdade(BaseAtalho):
    def test_o_pacote_montado_tem_assinatura_valida(self):
        resultado = atalho._criar_macos(self.base)
        self.assertTrue(resultado.criado)
        verificacao = atalho.subprocess.run(["codesign", "-v", str(resultado.caminho)], capture_output=True)
        self.assertEqual(verificacao.returncode, 0, verificacao.stderr)

class TestLinux(BaseAtalho):
    def setUp(self):
        super().setUp()
        self.resultado = atalho._criar_linux(self.base)
        self.arquivo = self.base / "autodoc.desktop"

    def test_cria_o_desktop(self):
        self.assertTrue(self.resultado.criado)
        self.assertTrue(self.arquivo.exists())

    def test_tem_as_chaves_que_o_sistema_le(self):
        texto = self.arquivo.read_text(encoding="utf-8")

        self.assertTrue(texto.startswith("[Desktop Entry]"))
        for chave in ("Type=Application", "Name=AutoDoc", "Exec=", "Path=",
                      "Icon=", "Terminal=false", "Categories="):
            with self.subTest(chave=chave):
                self.assertIn(chave, texto)

    def test_aponta_para_a_raiz_do_projeto(self):
        texto = self.arquivo.read_text(encoding="utf-8")
        self.assertIn(f"Path={atalho.RAIZ}", texto)
        self.assertIn("main.py app", texto)

    def test_e_executavel(self):
        self.assertTrue(self.arquivo.stat().st_mode & stat.S_IXUSR)


class TestWindows(BaseAtalho):
    def test_chama_o_powershell_com_o_que_importa(self):
        with mock.patch.object(atalho.subprocess, "run") as rodou:
            resultado = atalho._criar_windows(self.base)

        self.assertTrue(resultado.criado)
        comando = rodou.call_args.args[0]
        self.assertEqual(comando[0], "powershell")

        script = comando[-1]
        for pedaco in ("CreateShortcut", "TargetPath", "Arguments",
                       "WorkingDirectory", "IconLocation", "Save()"):
            with self.subTest(pedaco=pedaco):
                self.assertIn(pedaco, script)
        self.assertIn("main.py app", script)
        self.assertIn(str(atalho.RAIZ), script)

    def test_sem_powershell_avisa_em_vez_de_levantar(self):
        with mock.patch.object(atalho.subprocess, "run",
                               side_effect=FileNotFoundError("powershell")):
            resultado = atalho._criar_windows(self.base)

        self.assertFalse(resultado.criado)
        self.assertIsNone(resultado.caminho)
        self.assertIn("nao foi possivel", resultado.detalhe)

    def test_powershell_que_falha_tambem_avisa(self):
        erro = atalho.subprocess.CalledProcessError(1, "powershell")
        with mock.patch.object(atalho.subprocess, "run", side_effect=erro):
            resultado = atalho._criar_windows(self.base)

        self.assertFalse(resultado.criado)


class TestDespacho(BaseAtalho):
    """`criar()` escolhe o formato pelo sistema que está rodando."""

    def test_macos(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(atalho.criar(self.base).caminho.suffix, ".app")

    def test_windows(self):
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.object(atalho.subprocess, "run"):
            self.assertEqual(atalho.criar(self.base).caminho.suffix, ".lnk")

    def test_linux(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(atalho.criar(self.base).caminho.suffix, ".desktop")

    def test_sistema_desconhecido_cai_no_desktop(self):
        """Um BSD qualquer tem mais chance de entender .desktop do que .app."""
        with mock.patch.object(sys, "platform", "freebsd14"):
            self.assertEqual(atalho.criar(self.base).caminho.suffix, ".desktop")


class TestPythonDoProjeto(unittest.TestCase):
    def test_prefere_o_venv_ao_interpretador_atual(self):
        """O ícone é clicado fora de qualquer ambiente ativado."""
        escolhido = atalho._python_do_projeto()
        if (atalho.RAIZ / "venv" / "bin" / "python").exists():
            self.assertEqual(escolhido, atalho.RAIZ / "venv" / "bin" / "python")

    def test_sem_venv_usa_o_interpretador_atual(self):
        with mock.patch.object(atalho, "RAIZ", Path("/nao/existe")):
            self.assertEqual(atalho._python_do_projeto(), Path(sys.executable))


if __name__ == "__main__":
    unittest.main()
