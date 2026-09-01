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
from autodoc.catalogo import Catalogo
from autodoc.config import Config
from autodoc.monitor import (
    _Manipulador,
    aguardar_arquivo_pronto,
    deve_ignorar,
    processar_pendentes,
)
from autodoc.pipeline import Pipeline

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


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


class BaseComPasta(unittest.TestCase):
    """Um AutoDoc completo numa pasta temporária, com a espera encurtada."""

    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        base = Path(self._temporaria.name)
        self.config = Config(pasta_entrada=base / "entrada",
                             pasta_saida=base / "organizados")
        self.config.preparar_pastas()
        self.catalogo = Catalogo(self.config.pasta_saida)
        self.pipeline = Pipeline(self.config, self.catalogo)
        self.addCleanup(self._temporaria.cleanup)
        self.enterContext(mock.patch.object(monitor, "INTERVALO_ESTABILIDADE", 0))

    def largar(self, nome: str, conteudo: str | None = None) -> Path:
        alvo = self.config.pasta_entrada / nome
        alvo.write_text(conteudo or (EXEMPLOS / "conta_energia_marco.txt").read_text(
            encoding="utf-8"), encoding="utf-8")
        return alvo


class TestProcessarPendentes(BaseComPasta):
    """O que já estava na pasta quando o programa abriu."""

    def test_processa_o_que_estava_la(self):
        for nome in ("conta_energia_marco.txt", "nota_fiscal_1234.txt"):
            self.largar(nome, (EXEMPLOS / nome).read_text(encoding="utf-8"))

        self.assertEqual(processar_pendentes(self.pipeline), 2)
        self.assertEqual(len(self.catalogo), 2)

    def test_pasta_inexistente_nao_derruba_o_programa(self):
        """Alguém apagou a pasta monitorada entre uma abertura e outra."""
        self.config.pasta_entrada = self.config.pasta_entrada / "sumiu"

        with self.assertLogs("autodoc.monitor", "WARNING"):
            self.assertEqual(processar_pendentes(self.pipeline), 0)

    def test_ignora_temporarios_e_ocultos(self):
        self.largar("conta_energia_marco.txt")
        (self.config.pasta_entrada / ".DS_Store").write_bytes(b"lixo do Finder")
        (self.config.pasta_entrada / "~$doc.txt").write_text("aberto", encoding="utf-8")

        self.assertEqual(processar_pendentes(self.pipeline), 1)
        # os ignorados continuam onde estavam, sem virar documento
        self.assertTrue((self.config.pasta_entrada / ".DS_Store").exists())

    def test_ignora_subpasta(self):
        (self.config.pasta_entrada / "uma pasta").mkdir()
        self.assertEqual(processar_pendentes(self.pipeline), 0)

    def test_um_arquivo_problematico_nao_impede_os_outros(self):
        """O defeito: uma exceção aqui fazia o AutoDoc inteiro não subir."""
        self.largar("primeiro.txt")
        self.largar("explosivo.txt", "conteudo diferente para nao ser duplicata")
        self.largar("terceiro.txt", "CONTRATO DE LOCACAO\nCLAUSULA PRIMEIRA\n"
                                    "LOCADOR: X\nLOCATARIO: Y\nForo da comarca")

        original = self.pipeline.processar

        def explode_num_arquivo(caminho):
            if caminho.name == "explosivo.txt":
                raise RuntimeError("defeito inesperado")
            return original(caminho)

        with mock.patch.object(self.pipeline, "processar", explode_num_arquivo), \
             self.assertLogs("autodoc.monitor", "ERROR") as registro:
            processados = processar_pendentes(self.pipeline)

        self.assertEqual(processados, 2, "os outros dois tinham que passar")
        self.assertIn("explosivo.txt", registro.output[0])

    def test_espera_a_copia_terminar_tambem_aqui(self):
        """Não só no caminho do watchdog: o pendente também pode estar pela metade."""
        self.largar("conta_energia_marco.txt")
        with mock.patch.object(monitor, "aguardar_arquivo_pronto",
                               return_value=False) as espera:
            self.assertEqual(processar_pendentes(self.pipeline), 0)
        espera.assert_called_once()


class EventoFalso:
    """Um evento do watchdog, sem watchdog."""

    def __init__(self, src_path="", dest_path="", is_directory=False,
                 event_type="created"):
        self.src_path = str(src_path)
        self.dest_path = str(dest_path)
        self.is_directory = is_directory
        self.event_type = event_type


class TestManipulador(BaseComPasta):
    """O manipulador de eventos, exercitado direto — sem thread e sem disco."""

    def setUp(self):
        super().setUp()
        self.avisados = []
        self.manipulador = _Manipulador(self.pipeline, self.avisados.append)

    def test_arquivo_criado_e_processado(self):
        alvo = self.largar("conta_energia_marco.txt")
        self.manipulador.on_created(EventoFalso(src_path=alvo))

        self.assertEqual(len(self.catalogo), 1)
        self.assertEqual(self.avisados[0].categoria, "conta_luz")

    def test_arquivo_movido_usa_o_destino(self):
        """No evento de movimento o `src_path` aponta para onde o arquivo não está mais."""
        alvo = self.largar("conta_energia_marco.txt")
        self.manipulador.on_moved(
            EventoFalso(src_path="/lugar/antigo/conta.txt", dest_path=alvo))

        self.assertEqual(len(self.catalogo), 1)

    def test_evento_de_pasta_e_ignorado(self):
        self.manipulador.on_created(
            EventoFalso(src_path=self.config.pasta_entrada / "nova", is_directory=True))
        self.assertEqual(len(self.catalogo), 0)

    def test_arquivo_temporario_e_ignorado(self):
        alvo = self.largar("conta.txt.crdownload")
        self.manipulador.on_created(EventoFalso(src_path=alvo))
        self.assertEqual(len(self.catalogo), 0)
        self.assertTrue(alvo.exists(), "nem foi tocado")

    def test_arquivo_que_nao_ficou_pronto_e_deixado_para_depois(self):
        alvo = self.largar("conta_energia_marco.txt")
        with mock.patch.object(monitor, "aguardar_arquivo_pronto", return_value=False):
            self.manipulador.on_created(EventoFalso(src_path=alvo))
        self.assertEqual(len(self.catalogo), 0)

    def test_excecao_no_pipeline_nao_derruba_o_observador(self):
        """Perder um documento é ruim; parar de vigiar a pasta é pior."""
        alvo = self.largar("conta_energia_marco.txt")

        with mock.patch.object(self.pipeline, "processar",
                               side_effect=RuntimeError("defeito")), \
             self.assertLogs("autodoc.monitor", "ERROR") as registro:
            self.manipulador.on_created(EventoFalso(src_path=alvo))

        self.assertIn("conta_energia_marco.txt", registro.output[0])
        self.assertEqual(self.avisados, [], "não anuncia o que não processou")

    def test_excecao_no_callback_nao_derruba_o_observador(self):
        alvo = self.largar("conta_energia_marco.txt")
        manipulador = _Manipulador(
            self.pipeline, lambda _: (_ for _ in ()).throw(RuntimeError("tela morreu")))

        with self.assertLogs("autodoc.monitor", "ERROR"):
            manipulador.on_created(EventoFalso(src_path=alvo))

        # o documento foi arquivado mesmo com a tela falhando
        self.assertEqual(len(self.catalogo), 1)

    def test_nao_avisa_quando_o_documento_foi_ignorado(self):
        """Duplicata não é documento novo; a tela não pode anunciá-la."""
        alvo = self.largar("conta_energia_marco.txt")
        self.manipulador.on_created(EventoFalso(src_path=alvo))

        copia = self.largar("outra copia.txt")
        self.manipulador.on_created(EventoFalso(src_path=copia))

        self.assertEqual(len(self.avisados), 1)

    def test_funciona_sem_callback(self):
        """O CLI cria o observador sem passar `ao_processar`."""
        alvo = self.largar("conta_energia_marco.txt")
        _Manipulador(self.pipeline).on_created(EventoFalso(src_path=alvo))
        self.assertEqual(len(self.catalogo), 1)


class TestDispatch(BaseComPasta):
    """O ponto de entrada que o watchdog chama."""

    def test_encaminha_criado_e_movido(self):
        alvo = self.largar("conta_energia_marco.txt")
        manipulador = _Manipulador(self.pipeline)

        manipulador.dispatch(EventoFalso(src_path=alvo, event_type="created"))
        self.assertEqual(len(self.catalogo), 1)

        outro = self.largar("contrato.txt", (EXEMPLOS / "contrato_aluguel.txt").read_text(
            encoding="utf-8"))
        manipulador.dispatch(
            EventoFalso(src_path="/antigo", dest_path=outro, event_type="moved"))
        self.assertEqual(len(self.catalogo), 2)

    def test_ignora_os_outros_tipos_de_evento(self):
        """Alterar e apagar o que já foi arquivado é assunto da reconciliação."""
        alvo = self.largar("conta_energia_marco.txt")
        manipulador = _Manipulador(self.pipeline)

        for tipo in ("modified", "deleted", "closed", "opened"):
            with self.subTest(evento=tipo):
                manipulador.dispatch(EventoFalso(src_path=alvo, event_type=tipo))

        self.assertEqual(len(self.catalogo), 0)


class TestMonitorar(unittest.TestCase):
    """O laço do `python main.py monitorar`."""

    def test_ctrl_c_para_e_espera_o_observador(self):
        observador = mock.Mock()
        pipeline = mock.Mock()

        with mock.patch.object(monitor, "criar_observador", return_value=observador), \
             mock.patch.object(monitor.time, "sleep", side_effect=KeyboardInterrupt):
            monitor.monitorar(pipeline)

        observador.stop.assert_called_once()
        observador.join.assert_called_once()


if __name__ == "__main__":
    unittest.main()
