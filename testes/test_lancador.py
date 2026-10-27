"""O aplicativo abrindo o Tetris e instalando os gestos.

Nenhum teste abre o Tetris nem roda o pip de verdade: o `Popen` da abertura e
trocado por um falso, e a instalacao roda um "python" de mentira que imprime
linhas como o pip imprimiria.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from autodoc.gestos import lancador
from autodoc.gestos.lancador import Lancador, gestos_instalados, resumir_linha_do_pip


class ProcessoFalso:
    criados: list["ProcessoFalso"] = []

    def __init__(self, comando, cwd, stdout, stderr):
        self.comando = comando
        self.codigo = None
        ProcessoFalso.criados.append(self)

    def poll(self):
        return self.codigo

    @property
    def returncode(self):
        return self.codigo


class Base(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.lancador = Lancador(python="python-do-app", registro=self.pasta / "logs" / "tetris.log")
        ProcessoFalso.criados.clear()

    def com_gestos(self, instalados: bool):
        return mock.patch.object(lancador, "gestos_instalados", return_value=instalados)


class TestAbrir(Base):
    def abrir(self, instalados=True, sem_camera=False):
        with self.com_gestos(instalados), mock.patch.object(lancador.subprocess, "Popen", ProcessoFalso):
            return self.lancador.abrir(sem_camera)

    def test_abre_o_tetris_com_camera(self):
        estado = self.abrir()
        self.assertTrue(estado["aberto"])
        self.assertIsNone(estado["erro"])
        comando = ProcessoFalso.criados[0].comando
        self.assertEqual(comando[0], "python-do-app")
        self.assertEqual(comando[2:], ["gestos", "--tetris"])
        self.assertTrue(comando[1].endswith("main.py"))

    def test_nao_abre_dois(self):
        self.abrir()
        self.abrir()
        self.assertEqual(len(ProcessoFalso.criados), 1)

    def test_sem_os_gestos_nao_abre_com_camera(self):
        estado = self.abrir(instalados=False)
        self.assertFalse(estado["aberto"])
        self.assertIn("não está instalado", estado["erro"])
        self.assertEqual(ProcessoFalso.criados, [])

    def test_pelo_teclado_nao_precisa_dos_gestos(self):
        self.assertTrue(self.abrir(instalados=False, sem_camera=True)["aberto"])
        self.assertEqual(ProcessoFalso.criados[0].comando[-1], "--sem-camera")

    def test_fechou_normalmente(self):
        self.abrir()
        ProcessoFalso.criados[0].codigo = 0
        with self.com_gestos(True):
            estado = self.lancador.estado()
        self.assertEqual((estado["aberto"], estado["erro"]), (False, None))

    def test_fechou_com_erro_mostra_o_motivo(self):
        self.abrir()
        self.lancador.registro.write_text("baixando...\ngestos indisponiveis: nao consegui abrir a camera 0\n\n", encoding="utf-8")
        ProcessoFalso.criados[0].codigo = 1
        with self.com_gestos(True):
            estado = self.lancador.estado()
        self.assertFalse(estado["aberto"])
        self.assertEqual(estado["erro"], "nao consegui abrir a camera 0")

    def test_erro_sem_nada_no_registro(self):
        self.abrir()
        self.lancador.registro.write_text("", encoding="utf-8")
        ProcessoFalso.criados[0].codigo = 3
        with self.com_gestos(True):
            self.assertEqual(self.lancador.estado()["erro"], "código 3")

    def test_reabrir_limpa_o_erro(self):
        self.abrir(instalados=False)
        self.assertIsNone(self.abrir()["erro"])


class TestInstalar(Base):
    def python_falso(self, linhas: list[str], codigo: int = 0) -> str:
        """Um executavel que ignora os argumentos e imprime como o pip."""
        script = self.pasta / "python"
        corpo = "\n".join(f"print({linha!r}, flush=True)" for linha in linhas)
        script.write_text(f"#!{sys.executable}\nimport sys, time\n{corpo}\nsys.exit({codigo})\n", encoding="utf-8")
        script.chmod(0o755)
        return str(script)

    def esperar(self) -> dict:
        for _ in range(200):
            with self.com_gestos(False):
                estado = self.lancador.estado()
            if not estado["instalando"]:
                return estado
            time.sleep(0.02)
        self.fail("a instalacao nao terminou")

    def test_instala_e_avisa_o_progresso(self):
        self.lancador.python = self.python_falso([
            "Collecting mediapipe>=0.10.30 (from -r requirements-gestos.txt (line 15))",
            "  Downloading mediapipe-1.1.1-cp313-cp313-macosx_11_0_arm64.whl (50.0 MB)",
            "     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 50.0/50.0 MB 9.1 MB/s eta 0:00:00",
            "Installing collected packages: mediapipe",
            "Successfully installed mediapipe-1.1.1",
        ])
        with self.com_gestos(False):
            estado = self.lancador.instalar()
        self.assertTrue(estado["instalando"])
        final = self.esperar()
        self.assertEqual(final["mensagem"], "controle por gestos instalado")
        self.assertIsNone(final["erro"])

    def test_falha_mostra_a_ultima_linha(self):
        self.lancador.python = self.python_falso(["ERROR: No matching distribution found for mediapipe"], codigo=1)
        with self.com_gestos(False):
            self.lancador.instalar()
        final = self.esperar()
        self.assertEqual(final["erro"], "a instalação falhou: ERROR: No matching distribution found for mediapipe")
        self.assertIsNone(final["mensagem"])

    def test_falha_sem_saida(self):
        self.lancador.python = self.python_falso([], codigo=1)
        with self.com_gestos(False):
            self.lancador.instalar()
        self.assertEqual(self.esperar()["erro"], "a instalação falhou: sem detalhes")

    def test_ja_instalado_nao_instala_de_novo(self):
        with self.com_gestos(True), mock.patch.object(lancador.threading, "Thread") as thread:
            self.assertFalse(self.lancador.instalar()["instalando"])
        thread.assert_not_called()

    def test_duas_vezes_seguidas_instala_uma(self):
        self.lancador.python = self.python_falso(["Collecting cv2"])
        with self.com_gestos(False):
            self.lancador.instalar()
            with mock.patch.object(lancador.threading, "Thread") as thread:
                self.lancador.instalar()
        thread.assert_not_called()
        self.esperar()


class TestApoio(unittest.TestCase):
    def test_gestos_instalados_pergunta_sem_importar(self):
        with mock.patch.object(lancador.importlib.util, "find_spec", side_effect=lambda nome: object()):
            self.assertTrue(gestos_instalados())
        with mock.patch.object(lancador.importlib.util, "find_spec", side_effect=lambda nome: None if nome == "mediapipe" else object()):
            self.assertFalse(gestos_instalados())

    def test_resumo_das_linhas_do_pip(self):
        for linha, resumo in (
            ("Collecting opencv-python>=4.8 (from -r x (line 9))", "baixando opencv-python>=4.8"),
            ("  Downloading mediapipe-1.1.1.whl (50 MB)", "baixando mediapipe-1.1.1.whl"),
            ("Installing collected packages: numpy, cv2", "instalando os pacotes"),
            ("Successfully installed numpy-2", "pronto"),
            ("Requirement already satisfied: numpy in /x", "já instalado: numpy"),
            ("   ━━━━━━━━━━━━ 50/50 MB", None),
            ("[notice] A new release of pip is available", None),
            ("", None),
            ("Using cached x.whl", None),
        ):
            self.assertEqual(resumir_linha_do_pip(linha), resumo, linha)


if __name__ == "__main__":
    unittest.main()
