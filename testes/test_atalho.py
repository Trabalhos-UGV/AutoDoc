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


class TestMacOS(BaseAtalho):
    def setUp(self):
        super().setUp()
        self.resultado = atalho._criar_macos(self.base)
        self.pacote = self.base / "AutoDoc.app"

    def test_cria_o_pacote_com_a_estrutura_esperada(self):
        self.assertTrue(self.resultado.criado)
        self.assertTrue((self.pacote / "Contents" / "MacOS").is_dir())
        self.assertTrue((self.pacote / "Contents" / "Resources").is_dir())

    def test_o_info_plist_volta_a_ser_lido(self):
        """Um plist malformado faz o Finder ignorar o pacote em silêncio."""
        dados = plistlib.loads((self.pacote / "Contents" / "Info.plist").read_bytes())

        self.assertEqual(dados["CFBundleName"], "AutoDoc")
        self.assertEqual(dados["CFBundleIdentifier"], "br.edu.ugv.autodoc")
        self.assertEqual(dados["CFBundleExecutable"], "AutoDoc")
        self.assertEqual(dados["CFBundleShortVersionString"], __version__)
        self.assertTrue(dados["NSHighResolutionCapable"])

    def test_o_lancador_e_executavel(self):
        lancador = self.pacote / "Contents" / "MacOS" / "AutoDoc"
        self.assertTrue(lancador.exists())
        self.assertTrue(lancador.stat().st_mode & stat.S_IXUSR)

    def test_o_lancador_entra_na_raiz_e_chama_o_app(self):
        """O ícone é clicado meses depois, de qualquer lugar do sistema."""
        texto = (self.pacote / "Contents" / "MacOS" / "AutoDoc").read_text(encoding="utf-8")

        self.assertTrue(texto.startswith("#!/bin/bash"))
        self.assertIn(f'cd "{atalho.RAIZ}"', texto)
        self.assertIn("main.py app", texto)

    def test_o_lancador_usa_o_python_do_venv(self):
        texto = (self.pacote / "Contents" / "MacOS" / "AutoDoc").read_text(encoding="utf-8")
        self.assertIn("venv/bin/python", texto)

    def test_copia_o_icone_quando_existe(self):
        icone = self.pacote / "Contents" / "Resources" / "autodoc.icns"
        if (atalho.RECURSOS / "autodoc.icns").exists():
            self.assertTrue(icone.exists())
            self.assertGreater(icone.stat().st_size, 0)

    def test_sem_icone_o_pacote_ainda_e_criado(self):
        outra = self.base / "sem-icone"
        with mock.patch.object(atalho, "RECURSOS", self.base / "nao-existe"):
            resultado = atalho._criar_macos(outra)
        self.assertTrue(resultado.criado)

    def test_rodar_de_novo_nao_quebra(self):
        """A instalação é idempotente; o atalho também precisa ser."""
        segundo = atalho._criar_macos(self.base)
        self.assertTrue(segundo.criado)


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
