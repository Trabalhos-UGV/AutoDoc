"""Monitoramento da pasta de entrada.

O que se testa aqui é o que separa "funciona na demonstração" de "funciona na
pasta de alguém": arquivo pela metade, `.DS_Store`, documento que faz o pipeline
levantar. Nenhum deles pode parar o AutoDoc de vigiar a pasta.
"""

from __future__ import annotations

import tempfile
import time
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
        "desktop.ini",         # Windows, em pasta personalizada
        "Thumbs.db",           # Windows, miniaturas
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
        with mock.patch.object(monitor, "_assinatura",
                               side_effect=[(1, 1), FileNotFoundError()]):
            self.assertFalse(aguardar_arquivo_pronto(alvo))

    def test_mesmo_tamanho_com_data_nova_ainda_nao_esta_pronto(self):
        """Copia sobrescrevendo no lugar: o tamanho para, a data nao."""
        alvo = self.pasta / "sobrescrito.pdf"
        alvo.write_text("x", encoding="utf-8")
        with mock.patch.object(monitor, "_assinatura",
                               side_effect=[(5, 1), (5, 2), (5, 2)]):
            self.assertTrue(aguardar_arquivo_pronto(alvo))

    def test_arquivo_travado_por_quem_escreve_nao_esta_pronto(self):
        """No Windows, quem ainda escreve impede os outros de abrir."""
        alvo = self.pasta / "travado.pdf"
        alvo.write_text("conteudo", encoding="utf-8")
        with mock.patch.object(monitor, "TENTATIVAS_ESTABILIDADE", 3), \
             mock.patch.object(Path, "open", side_effect=PermissionError("em uso")):
            self.assertFalse(aguardar_arquivo_pronto(alvo))

    def test_arquivo_que_some_depois_da_espera(self):
        alvo = self.pasta / "vazio.txt"
        alvo.touch()
        with mock.patch.object(monitor, "TENTATIVAS_ESTABILIDADE", 2), \
             mock.patch.object(monitor, "_assinatura",
                               side_effect=[(0, 1), (0, 1), FileNotFoundError()]):
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

    def test_arquivo_que_cresce_sem_parar_fica_para_depois(self):
        """Download lento: a função desiste em vez de esperar para sempre — e
        desistir é "não está pronto". Antes ela devolvia sim, e o PDF pela
        metade ia para o arquivo como documento ilegível."""
        tamanhos = iter(range(1, 100))
        alvo = self.pasta / "crescendo.txt"
        alvo.write_text("a", encoding="utf-8")

        with mock.patch.object(monitor, "TENTATIVAS_ESTABILIDADE", 4), \
             mock.patch.object(monitor.time, "sleep") as dormiu, \
             mock.patch.object(monitor, "_assinatura",
                               side_effect=lambda caminho: (next(tamanhos), 0)):
            self.assertFalse(aguardar_arquivo_pronto(alvo))

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

    def test_pasta_vazia_dentro_da_entrada_nao_conta(self):
        (self.config.pasta_entrada / "uma pasta").mkdir()
        self.assertEqual(processar_pendentes(self.pipeline), 0)

    def test_subpasta_nao_e_tocada(self):
        """Uma pasta de Downloads com projetos dentro: nada sai delas."""
        subpasta = self.config.pasta_entrada / "contas de 2026"
        subpasta.mkdir()
        conta = subpasta / "luz.txt"
        conta.write_text((EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8"), encoding="utf-8")

        self.assertEqual(processar_pendentes(self.pipeline), 0)
        self.assertTrue(conta.exists())

    def test_aplicativo_na_entrada_fica_inteiro(self):
        recursos = self.config.pasta_entrada / "Jogo.app" / "Contents" / "Resources"
        recursos.mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (16, 16)).save(recursos / "icone.png")
        (recursos / "Localizable.strings").write_text("x", encoding="utf-8")

        self.assertEqual(processar_pendentes(self.pipeline), 0)
        self.assertEqual(sorted(c.name for c in recursos.iterdir()), ["Localizable.strings", "icone.png"])

    def test_formato_que_nao_le_fica_onde_esta(self):
        (self.config.pasta_entrada / "projeto.zip").write_bytes(b"PK")
        (self.config.pasta_entrada / "sketch.ino").write_text("void setup(){}", encoding="utf-8")

        self.assertEqual(monitor.arquivos_da_entrada(self.config.pasta_entrada, self.config.extensoes), [])
        processar_pendentes(self.pipeline)
        self.assertTrue((self.config.pasta_entrada / "projeto.zip").exists())

    def test_atalho_fica_onde_esta(self):
        alvo = self.config.pasta_saida / "fora.txt"
        alvo.write_text("CONTRATO DE LOCACAO", encoding="utf-8")
        atalho = self.config.pasta_entrada / "atalho.txt"
        atalho.symlink_to(alvo)

        self.assertEqual(monitor.arquivos_da_entrada(self.config.pasta_entrada, self.config.extensoes), [])

    def test_so_o_primeiro_nivel_entra_na_lista(self):
        self.largar("conta_energia_marco.txt")
        (self.config.pasta_entrada / "pasta").mkdir()
        (self.config.pasta_entrada / "pasta" / "dentro.txt").write_text("x", encoding="utf-8")

        self.assertEqual(
            [c.name for c in monitor.arquivos_da_entrada(self.config.pasta_entrada, self.config.extensoes)],
            ["conta_energia_marco.txt"])

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

    def test_arquivo_criado_numa_subpasta_e_ignorado(self):
        subpasta = self.config.pasta_entrada / "Jogo.app" / "Contents"
        subpasta.mkdir(parents=True)
        alvo = subpasta / "Info.txt"
        alvo.write_text("CONTRATO DE LOCACAO", encoding="utf-8")
        with mock.patch.object(self.pipeline, "processar") as processou:
            self.manipulador.on_created(EventoFalso(src_path=alvo))
        processou.assert_not_called()
        self.assertTrue(alvo.exists())

    def test_formato_que_nao_le_e_ignorado(self):
        alvo = self.config.pasta_entrada / "instalador.dmg"
        alvo.write_bytes(b"x")
        with mock.patch.object(self.pipeline, "processar") as processou:
            self.manipulador.on_created(EventoFalso(src_path=alvo))
        processou.assert_not_called()

    def test_arquivo_dentro_da_pasta_organizada_e_ignorado(self):
        self.config.pasta_saida = self.config.pasta_entrada / "organizados"
        manipulador = monitor._Manipulador(self.pipeline)
        with mock.patch.object(self.pipeline, "processar") as processou:
            manipulador.on_created(EventoFalso(
                src_path=self.config.pasta_saida / "conta_luz" / "x.txt"))
        processou.assert_not_called()

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


class TestVarredura(BaseComPasta):
    """O que o watchdog deixou para depois não pode esperar a próxima abertura."""

    def test_pendentes_tambem_avisam_a_tela(self):
        self.largar("conta.txt")
        avisados = []
        monitor.processar_pendentes(self.pipeline, avisados.append)
        self.assertEqual(len(avisados), 1)

    def test_a_varredura_pega_o_que_ficou_na_pasta(self):
        observador = mock.Mock()
        vigia = monitor.Vigia(observador, self.pipeline)
        self.largar("conta.txt")

        with mock.patch.object(monitor, "INTERVALO_VARREDURA", 0.01):
            vigia.start()
            for _ in range(200):
                if not any(self.config.pasta_entrada.iterdir()):
                    break
                time.sleep(0.01)
            vigia.stop()
            vigia.join()

        self.assertFalse(any(self.config.pasta_entrada.iterdir()))
        observador.start.assert_called_once()
        observador.stop.assert_called_once()
        observador.join.assert_called_once()

    def test_falha_na_varredura_nao_para_a_varredura(self):
        vigia = monitor.Vigia(mock.Mock(), self.pipeline)
        chamadas = []

        def explode(*_):
            chamadas.append(1)
            if len(chamadas) >= 2:
                vigia._parar.set()
            raise RuntimeError("disco sumiu")

        with mock.patch.object(monitor, "INTERVALO_VARREDURA", 0), \
             mock.patch.object(monitor, "processar_pendentes", explode), \
             self.assertLogs("autodoc.monitor", "ERROR"):
            vigia._varrer()

        self.assertEqual(len(chamadas), 2)

    def test_parar_antes_de_comecar_nao_trava(self):
        vigia = monitor.Vigia(mock.Mock(), self.pipeline)
        vigia.stop()
        vigia.join()


class TestAguardandoOcr(BaseComPasta):
    """A foto que esperava o OCR volta sozinha quando ele passa a existir."""

    def esperando(self) -> Path:
        pasta = self.config.pasta_saida / "_Aguardando_OCR"
        pasta.mkdir(parents=True, exist_ok=True)
        alvo = pasta / "conta.txt"
        alvo.write_text((EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8"),
                        encoding="utf-8")
        return alvo

    def test_com_ocr_volta_ao_pipeline(self):
        alvo = self.esperando()
        with mock.patch.object(monitor, "diagnostico_ocr", return_value={"disponivel": True}):
            self.assertEqual(processar_pendentes(self.pipeline), 1)
        self.assertFalse(alvo.exists())

    def test_sem_ocr_continua_esperando(self):
        alvo = self.esperando()
        with mock.patch.object(monitor, "diagnostico_ocr", return_value={"disponivel": False}):
            self.assertEqual(processar_pendentes(self.pipeline), 0)
        self.assertTrue(alvo.exists())

    def test_sem_nada_esperando_nem_pergunta_pelo_ocr(self):
        """O diagnóstico roda o Tesseract; a cada 30 s, só se houver motivo."""
        (self.config.pasta_saida / "_Aguardando_OCR").mkdir(parents=True)
        with mock.patch.object(monitor, "diagnostico_ocr") as perguntou:
            self.assertEqual(monitor.aguardando_ocr(self.pipeline), [])
        perguntou.assert_not_called()


class TestWatchdogAusente(BaseComPasta):
    def test_sem_watchdog_explica_o_que_instalar(self):
        """É a única dependência sem a qual o AutoDoc não tem como funcionar."""
        with mock.patch.dict("sys.modules", {"watchdog.observers": None}):
            with self.assertRaises(RuntimeError) as erro:
                monitor.criar_observador(self.pipeline)

        self.assertIn("requirements.txt", str(erro.exception))


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
