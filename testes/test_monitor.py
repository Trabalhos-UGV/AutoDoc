"""Monitoramento da pasta de entrada.

O que se testa aqui é o que separa "funciona na demonstração" de "funciona na
pasta de alguém": arquivo pela metade, `.DS_Store`, documento que faz o pipeline
levantar. Nenhum deles pode parar o AutoDoc de vigiar a pasta.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoc import monitor
from autodoc.monitor import aguardar_arquivo_pronto, deve_ignorar


class TestDeveIgnorar(unittest.TestCase):
    """Nem tudo que cai na pasta é documento de alguém."""

    IGNORADOS = [
        ".DS_Store",           # macOS, em toda pasta que alguém abre
        ".gitkeep",
        "~$relatorio.docx",    # Word, enquanto o arquivo está aberto
        "._foto.jpg",          # macOS em pen drive
        "conta.pdf.crdownload",  # Chrome, download em andamento
        "nota.part",
        "boleto.partial",
        "arquivo.download",
        "rascunho.tmp",
        ".conta.txt.swp",
    ]

    ACEITOS = ["nota.pdf", "conta_energia.txt", "scan0031.png", "documento.jpeg"]

    def test_temporarios_e_ocultos_sao_ignorados(self):
        for nome in self.IGNORADOS:
            with self.subTest(arquivo=nome):
                self.assertTrue(deve_ignorar(Path(nome)))

    def test_documentos_de_verdade_passam(self):
        for nome in self.ACEITOS:
            with self.subTest(arquivo=nome):
                self.assertFalse(deve_ignorar(Path(nome)))

    def test_extensao_em_maiuscula_tambem_passa(self):
        """`boleto.PDF` é um documento; comparar sem baixar a caixa o perderia."""
        self.assertFalse(deve_ignorar(Path("boleto.PDF")))

    def test_sufixo_temporario_em_maiuscula_e_ignorado(self):
        self.assertTrue(deve_ignorar(Path("rascunho.TMP")))

    def test_decide_pelo_nome_e_nao_pela_pasta(self):
        """Uma pasta oculta no caminho não faz do arquivo um arquivo oculto."""
        self.assertFalse(deve_ignorar(Path("/home/.config/AutoDoc/nota.pdf")))


class TestAguardarArquivoPronto(unittest.TestCase):
    """Um arquivo ainda sendo copiado seria arquivado pela metade."""

    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporaria.name)
        self.addCleanup(self._temporaria.cleanup)
        # A espera de verdade custa meio segundo por rodada; o que se testa é a
        # decisão, não o relógio.
        self.enterContext(mock.patch.object(monitor, "INTERVALO_ESTABILIDADE", 0))

    def test_arquivo_estavel_esta_pronto(self):
        alvo = self.pasta / "conta.txt"
        alvo.write_text("conteudo completo", encoding="utf-8")
        self.assertTrue(aguardar_arquivo_pronto(alvo))

    def test_arquivo_inexistente_nao_esta_pronto(self):
        self.assertFalse(aguardar_arquivo_pronto(self.pasta / "nao-existe.txt"))

    def test_arquivo_que_some_no_meio_da_espera(self):
        """Alguém apagou o arquivo antes de a cópia terminar."""
        alvo = self.pasta / "sumindo.txt"
        alvo.write_text("x", encoding="utf-8")

        # existe na primeira olhada, sumiu na segunda
        with mock.patch.object(Path, "exists", side_effect=[True, False]):
            self.assertFalse(aguardar_arquivo_pronto(alvo))

    def test_arquivo_vazio_nunca_estabiliza(self):
        """Zero byte é o estado de quem acabou de ser criado, não de quem acabou.

        A espera se esgota sem nunca considerá-lo estável, e no fim a função
        cai no "pelo menos ele existe" — que é a resposta certa: melhor tentar
        processar um arquivo estranho do que ignorá-lo em silêncio.
        """
        alvo = self.pasta / "vazio.txt"
        alvo.touch()

        # `sleep` roda uma vez por volta do laço — é o contador honesto aqui,
        # porque espiar `stat` atrapalharia o `exists`, que chama `stat` dentro.
        with mock.patch.object(monitor, "TENTATIVAS_ESTABILIDADE", 3), \
             mock.patch.object(monitor.time, "sleep") as dormiu:
            self.assertTrue(aguardar_arquivo_pronto(alvo))

        self.assertEqual(dormiu.call_count, 3, "deveria ter esgotado as tentativas")

    def test_arquivo_que_cresce_sem_parar_esgota_as_tentativas(self):
        """Download lento: a função desiste em vez de esperar para sempre."""
        tamanhos = iter(range(1, 100))
        estatistica = type("Estatistica", (), {})

        def crescendo(*a, **k):
            resultado = estatistica()
            resultado.st_size = next(tamanhos)
            return resultado

        alvo = self.pasta / "crescendo.txt"
        alvo.write_text("a", encoding="utf-8")

        with mock.patch.object(monitor, "TENTATIVAS_ESTABILIDADE", 4), \
             mock.patch.object(monitor.time, "sleep") as dormiu, \
             mock.patch.object(Path, "stat", crescendo):
            aguardar_arquivo_pronto(alvo)

        # desistiu depois das 4 tentativas em vez de esperar para sempre
        self.assertEqual(dormiu.call_count, 4)


if __name__ == "__main__":
    unittest.main()
