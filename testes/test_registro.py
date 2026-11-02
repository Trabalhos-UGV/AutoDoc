"""O registro em arquivo: o unico lugar onde um erro aparece sem terminal."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc import registro


class TestPastaDeRegistro(unittest.TestCase):
    def test_cada_sistema_no_seu_lugar(self):
        casos = (
            ("darwin", {}, Path.home() / "Library" / "Logs" / "AutoDoc"),
            ("win32", {"LOCALAPPDATA": "C:/Local"}, Path("C:/Local") / "AutoDoc" / "logs"),
            ("linux", {"XDG_STATE_HOME": "/estado"}, Path("/estado") / "autodoc"),
        )
        for plataforma, ambiente, esperado in casos:
            with self.subTest(sistema=plataforma), \
                 mock.patch.object(registro.sys, "platform", plataforma), \
                 mock.patch.dict(registro.os.environ, ambiente):
                self.assertEqual(registro.pasta_de_registro(), esperado)

    def test_sem_variavel_de_ambiente_usa_a_casa(self):
        with mock.patch.dict(registro.os.environ, {}, clear=True):
            with mock.patch.object(registro.sys, "platform", "linux"):
                self.assertEqual(registro.pasta_de_registro(),
                                 Path.home() / ".local" / "state" / "autodoc")
            with mock.patch.object(registro.sys, "platform", "win32"):
                self.assertEqual(registro.pasta_de_registro(),
                                 Path.home() / "AppData" / "Local" / "AutoDoc" / "logs")


class TestConfigurar(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)
        self.enterContext(mock.patch.object(registro.logging, "basicConfig"))
        raiz = logging.getLogger()
        antes = list(raiz.handlers)

        def restaurar():
            for manipulador in raiz.handlers[:]:
                if manipulador not in antes:
                    manipulador.close()
                    raiz.removeHandler(manipulador)
        self.addCleanup(restaurar)

    def test_o_aviso_vai_para_o_arquivo(self):
        caminho = registro.configurar(self.pasta / "logs")
        logging.getLogger("autodoc.pipeline").warning("nao foi possivel mover conta.pdf")
        for manipulador in logging.getLogger().handlers:
            manipulador.flush()

        self.assertEqual(caminho, self.pasta / "logs" / "autodoc.log")
        self.assertIn("conta.pdf", caminho.read_text(encoding="utf-8"))

    def test_sem_onde_gravar_o_programa_abre_mesmo_assim(self):
        bloqueio = self.pasta / "arquivo"
        bloqueio.write_text("x", encoding="utf-8")
        with self.assertLogs("autodoc.registro", "WARNING"):
            self.assertIsNone(registro.configurar(bloqueio / "logs"))


if __name__ == "__main__":
    unittest.main()
