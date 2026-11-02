"""O caminho completo de um documento: da pasta de entrada ao arquivo."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from autodoc import pipeline as pipeline_modulo
from autodoc.catalogo import (
    PASTA_AGUARDANDO_OCR,
    PASTA_DUPLICADOS,
    PASTA_NAO_SUPORTADOS,
    PASTA_REVISAO,
    Catalogo,
)
from autodoc.classificador import NAO_CLASSIFICADO
from autodoc.config import Config
from autodoc.extrator import ExtracaoIndisponivel, OcrIndisponivel
from autodoc.pipeline import Pipeline

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


class BasePipeline(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        base = Path(self._temporaria.name)
        self.base = base
        self.config = Config(pasta_entrada=base / "entrada",
                             pasta_saida=base / "organizados")
        self.config.preparar_pastas()
        self.catalogo = Catalogo(self.config.pasta_saida)
        self.pipeline = Pipeline(self.config, self.catalogo)
        self.addCleanup(self._temporaria.cleanup)

    def largar(self, origem: Path, nome: str | None = None) -> Path:
        """Copia um arquivo para a pasta monitorada, como o usuario faria."""
        destino = self.config.pasta_entrada / (nome or origem.name)
        shutil.copy2(origem, destino)
        return destino

    def largar_exemplo(self, nome: str, como: str | None = None) -> Path:
        return self.largar(EXEMPLOS / nome, como)

    @property
    def entrada_vazia(self) -> bool:
        return not any(self.config.pasta_entrada.iterdir())


class TestArquivamento(BasePipeline):
    def test_conta_de_luz_vai_para_categoria_ano_e_mes(self):
        resultado = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt"))

        self.assertEqual(resultado.categoria, "conta_luz")
        self.assertEqual(
            resultado.destino.relative_to(self.config.pasta_saida),
            Path("conta_luz/2026/03/conta_energia_marco.txt"),
        )
        self.assertTrue(resultado.destino.exists())

    def test_o_arquivo_sai_da_pasta_de_entrada(self):
        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))
        self.assertTrue(self.entrada_vazia)

    def test_documento_duvidoso_vai_para_revisao(self):
        resultado = self.pipeline.processar(
            self.largar_exemplo("scan0031_ilegivel.txt"))

        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertEqual(resultado.destino.parent.name, PASTA_REVISAO)

    def test_revisao_nao_separa_por_ano(self):
        """E uma pilha para alguem olhar, nao um arquivo morto."""
        resultado = self.pipeline.processar(
            self.largar_exemplo("scan0031_ilegivel.txt"))
        self.assertEqual(resultado.destino.parent,
                         self.config.pasta_saida / PASTA_REVISAO)

    def test_nome_repetido_na_mesma_pasta_nao_sobrescreve(self):
        """Duas contas diferentes, mesmo nome, mesmo mes: nenhuma se perde."""
        primeiro = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt"))

        # outra conta de luz, do mesmo mes, com o mesmo nome de arquivo
        outra = self.config.pasta_entrada / "conta_energia_marco.txt"
        outra.write_text(
            "COPEL DISTRIBUICAO\nCONTA DE ENERGIA ELETRICA\n"
            "Consumo faturado: 92 kWh\nBandeira tarifaria: verde\n"
            "VENCIMENTO 20/03/2026\nTOTAL A PAGAR R$ 98,10\n",
            encoding="utf-8")
        segundo = self.pipeline.processar(outra)

        self.assertEqual(segundo.categoria, "conta_luz")
        self.assertEqual(segundo.destino.parent, primeiro.destino.parent)
        self.assertEqual(segundo.destino.name, "conta_energia_marco (2).txt")
        self.assertTrue(primeiro.destino.exists(), "o primeiro nao pode ter sumido")

    def test_formato_nao_suportado_fica_onde_esta(self):
        """Levado para `_Nao_suportados/`, ele esvaziou aplicativos de uma pasta de Downloads."""
        alvo = self.config.pasta_entrada / "planilha.xlsx"
        alvo.write_text("qualquer coisa", encoding="utf-8")

        resultado = self.pipeline.processar(alvo)
        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.ignorado, "formato nao suportado")
        self.assertTrue(alvo.exists())
        self.assertIsNone(resultado.destino)
        self.assertFalse((self.config.pasta_saida / PASTA_NAO_SUPORTADOS).exists())


class TestTodosOsExemplos(BasePipeline):
    def test_os_cinco_exemplos_terminam_onde_devem(self):
        esperado = {
            "conta_energia_marco.txt": "conta_luz/2026/03",
            "nota_fiscal_1234.txt": "nota_fiscal/2026/03",
            "contrato_aluguel.txt": "contrato/2026/03",
            "comprovante_pix.txt": "comprovante/2026/03",
            "scan0031_ilegivel.txt": PASTA_REVISAO,
        }
        for nome, pasta in esperado.items():
            with self.subTest(arquivo=nome):
                resultado = self.pipeline.processar(self.largar_exemplo(nome))
                self.assertEqual(
                    str(resultado.destino.parent.relative_to(self.config.pasta_saida)),
                    pasta,
                )

        self.assertEqual(len(self.catalogo), 5)
        self.assertTrue(self.entrada_vazia)


class TestDeduplicacao(BasePipeline):
    def setUp(self):
        super().setUp()
        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))

    def test_mesmo_conteudo_com_outro_nome_nao_e_indexado_de_novo(self):
        resultado = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt", "conta (copia).txt"))

        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.ignorado, "ja indexado")
        self.assertEqual(len(self.catalogo), 1)

    def test_a_copia_sai_da_pasta_de_entrada(self):
        """Deixada ali, seria reexaminada a cada abertura do programa."""
        self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt", "conta (copia).txt"))

        self.assertTrue(self.entrada_vazia)
        self.assertEqual(
            [p.name for p in (self.config.pasta_saida / PASTA_DUPLICADOS).iterdir()],
            ["conta (copia).txt"],
        )

    def test_a_copia_nao_e_apagada(self):
        """Arquivo de quem usa nao se apaga, se põe de lado."""
        self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt", "conta (copia).txt"))
        guardada = self.config.pasta_saida / PASTA_DUPLICADOS / "conta (copia).txt"
        self.assertTrue(guardada.exists())


class TestExplicacao(BasePipeline):
    """O trajeto do arquivo e o que permite discordar do sistema."""

    def setUp(self):
        super().setUp()
        self.resultado = self.pipeline.processar(
            self.largar_exemplo("conta_energia_marco.txt"))
        self.ficha = self.resultado.documento

    def test_o_trajeto_tem_as_cinco_etapas(self):
        titulos = [etapa["titulo"] for etapa in self.ficha.etapas]
        self.assertEqual(titulos, ["Detecção", "Extração de texto",
                                   "Classificação", "Data", "Arquivamento"])

    def test_guarda_a_regra_e_as_palavras_chave(self):
        self.assertIn("conta_luz", self.ficha.regra)
        self.assertIn("kWh", self.ficha.palavras_chave)

    def test_guarda_o_trecho_lido(self):
        self.assertTrue(self.ficha.trecho)
        self.assertLessEqual(len(self.ficha.trecho), 221)

    def test_guarda_a_origem_do_texto(self):
        self.assertEqual(self.ficha.origem, "arquivo de texto")

    def test_mostra_o_vencimento_e_arquiva_pelo_mes_de_referencia(self):
        """A tela mostra a data escrita (vencimento); a pasta é a do mês da conta."""
        self.assertEqual(self.ficha.data_documento, "2026-03-12")
        self.assertEqual(self.ficha.data_pasta, "2026-03-01")
        self.assertIn("mês de referência", self.ficha.etapas[3]["detalhe"])


class TestCorrecaoManual(BasePipeline):
    def setUp(self):
        super().setUp()
        self.pipeline.processar(self.largar_exemplo("scan0031_ilegivel.txt"))
        self.ficha = self.catalogo.por_id(1)

    def test_corrigir_move_o_arquivo_para_a_categoria_nova(self):
        corrigida = self.pipeline.reclassificar(self.ficha, "contrato")

        self.assertEqual(corrigida.categoria, "contrato")
        self.assertTrue(self.catalogo.caminho_de(corrigida).exists())
        self.assertFalse(any((self.config.pasta_saida / PASTA_REVISAO).iterdir()))

    def test_corrigir_registra_que_foi_decisao_humana(self):
        corrigida = self.pipeline.reclassificar(self.ficha, "contrato")

        self.assertEqual(corrigida.confianca, 1.0)
        self.assertIn("a mao", corrigida.regra)
        self.assertEqual(corrigida.etapas[-1]["titulo"], "Correção manual")

    def test_correcao_sobrevive_ao_fechamento(self):
        self.pipeline.reclassificar(self.ficha, "contrato")
        relido = Catalogo(self.config.pasta_saida)
        self.assertEqual(relido.por_id(1).categoria, "contrato")

    def test_correcao_entra_no_diario(self):
        antes = self.catalogo.caminho_de(self.ficha)
        corrigida = self.pipeline.reclassificar(self.ficha, "contrato")
        ultima = json.loads(self.catalogo.movimentos.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((ultima["origem"], ultima["destino"]),
                         (str(antes), str(self.catalogo.caminho_de(corrigida))))

    def test_categoria_inventada_e_recusada(self):
        with self.assertRaises(ValueError):
            self.pipeline.reclassificar(self.ficha, "categoria_que_nao_existe")


class TestBackup(BasePipeline):
    def test_copia_para_a_pasta_de_backup(self):
        self.config.pasta_backup = self.base / "drive"
        self.config.preparar_pastas()

        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))
        self.assertTrue(
            (self.config.pasta_backup / "conta_luz" / "conta_energia_marco.txt").exists())

    def test_backup_indisponivel_nao_impede_o_arquivamento(self):
        self.config.pasta_backup = Path("/proc/nao/existe")

        with self.assertLogs("autodoc.pipeline", "WARNING"):
            resultado = self.pipeline.processar(
                self.largar_exemplo("conta_energia_marco.txt"))

        self.assertTrue(resultado.sucesso)
        self.assertTrue(resultado.destino.exists())


class TestFormatacao(unittest.TestCase):
    """Números que vão para a tela, e por isso são lidos por gente."""

    def test_tamanho_em_bytes_kilobytes_e_megabytes(self):
        from autodoc.pipeline import _formatar_tamanho

        self.assertEqual(_formatar_tamanho(512), "512 B")
        self.assertEqual(_formatar_tamanho(1023), "1023 B")
        self.assertEqual(_formatar_tamanho(2048), "2 KB")
        self.assertEqual(_formatar_tamanho(3 * 1024 * 1024), "3,0 MB")

    def test_o_tamanho_usa_virgula_como_se_escreve_em_portugues(self):
        from autodoc.pipeline import _formatar_tamanho

        self.assertIn(",", _formatar_tamanho(int(1.5 * 1024 * 1024)))

    def test_trecho_curto_sai_inteiro(self):
        from autodoc.pipeline import _trecho

        self.assertEqual(_trecho("conta de luz"), "conta de luz")

    def test_trecho_junta_os_espacos(self):
        from autodoc.pipeline import _trecho

        self.assertEqual(_trecho("conta   de\n\n luz"), "conta de luz")

    def test_trecho_comprido_e_cortado_numa_palavra_inteira(self):
        from autodoc.pipeline import TAMANHO_TRECHO, _trecho

        cortado = _trecho("palavra " * 100)
        self.assertTrue(cortado.endswith("…"))
        self.assertLessEqual(len(cortado), TAMANHO_TRECHO + 1)
        self.assertNotIn("palavr…", cortado, "não pode cortar no meio da palavra")


class TestDocumentoSemData(BasePipeline):
    def test_vai_para_sem_data(self):
        """Nem o texto nem o arquivo deram data: o documento não some."""
        alvo = self.config.pasta_entrada / "contrato_sem_data.txt"
        alvo.write_text("CONTRATO DE LOCACAO\nCLAUSULA PRIMEIRA\nLOCADOR\n"
                        "LOCATARIO\nForo da comarca", encoding="utf-8")

        with mock.patch.object(pipeline_modulo.Pipeline, "_resolver_data",
                               return_value=(None, "nenhuma data encontrada")):
            resultado = self.pipeline.processar(alvo)

        self.assertEqual(resultado.destino.parent.name, "sem-data")
        self.assertTrue(resultado.destino.exists())


class TestCaminhoRelativo(BasePipeline):
    def test_destino_fora_da_pasta_de_saida_sai_absoluto(self):
        """Pode acontecer se alguém trocar a pasta de saída com documentos já fichados."""
        fora = self.base / "outro" / "lugar" / "arquivo.txt"
        self.assertEqual(self.pipeline._relativo(fora), str(fora.parent) + "/")


class TestFalhasAoMover(BasePipeline):
    def test_recolher_que_falha_devolve_nada_sem_derrubar(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")

        with mock.patch.object(pipeline_modulo.shutil, "move",
                               side_effect=OSError("disco cheio")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            self.assertIsNone(self.pipeline._recolher(alvo, "_Duplicados"))

    def test_arquivo_travado_fica_na_entrada_para_nova_tentativa(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")

        with mock.patch.object(pipeline_modulo.shutil, "move",
                               side_effect=PermissionError("em uso por outro programa")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            resultado = self.pipeline.processar(alvo)

        self.assertFalse(resultado.sucesso)
        self.assertIn("mover", resultado.ignorado)
        self.assertTrue(alvo.exists())
        self.assertEqual(len(self.catalogo), 0, "nada pode ser fichado sem ter sido movido")

        # na proxima tentativa, ja destravado, ele vai
        self.assertTrue(self.pipeline.processar(alvo).sucesso)

    def test_copia_que_ficou_no_destino_e_desfeita(self):
        """Entre volumes o move copia e depois apaga; se apagar falha, a copia
        no destino faria a proxima tentativa virar "nome (2)"."""
        alvo = self.largar_exemplo("conta_energia_marco.txt")

        def copia_e_falha(origem, destino):
            shutil.copy2(origem, destino)
            raise PermissionError("origem em uso")

        with mock.patch.object(pipeline_modulo.shutil, "move", copia_e_falha), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            self.pipeline.processar(alvo)

        self.assertTrue(alvo.exists())
        saida = self.config.pasta_saida
        self.assertEqual([c for c in saida.rglob("*.txt")], [])

    def test_arquivo_que_ja_saiu_da_pasta_nao_e_processado(self):
        """O watchdog e a varredura acharam o mesmo arquivo; o segundo chega tarde."""
        resultado = self.pipeline.processar(self.config.pasta_entrada / "ja-foi.txt")
        self.assertFalse(resultado.sucesso)
        self.assertIn("nao esta mais", resultado.ignorado)

    def test_arquivo_ilegivel_no_hash_e_avisado(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")

        with mock.patch.object(pipeline_modulo, "hash_arquivo",
                               side_effect=OSError("sem permissao")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            resultado = self.pipeline.processar(alvo)

        self.assertFalse(resultado.sucesso)
        self.assertIn("ilegivel", resultado.ignorado)

    def test_corrigir_documento_cujo_arquivo_sumiu(self):
        """Alguém apagou no Finder entre a tela carregar e o clique."""
        self.pipeline.processar(self.largar_exemplo("scan0031_ilegivel.txt"))
        ficha = self.catalogo.por_id(1)
        self.catalogo.caminho_de(ficha).unlink()

        with self.assertLogs("autodoc.pipeline", "WARNING"):
            corrigida = self.pipeline.reclassificar(ficha, "contrato")

        # a ficha acompanha a decisão mesmo sem o arquivo
        self.assertEqual(corrigida.categoria, "contrato")


class TestSemOcr(BasePipeline):
    """Foto boa numa maquina sem Tesseract: espera o OCR, nao vai para a revisao."""

    def processar_sem_ocr(self, alvo):
        with mock.patch.object(pipeline_modulo, "extrair_com_origem",
                               side_effect=OcrIndisponivel("Tesseract nao esta instalado")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            return self.pipeline.processar(alvo)

    def test_vai_para_a_pasta_de_espera_sem_ficha(self):
        resultado = self.processar_sem_ocr(self.largar_exemplo("conta_energia_marco.txt"))

        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.ignorado, "aguardando OCR")
        self.assertEqual(resultado.destino.parent.name, PASTA_AGUARDANDO_OCR)
        self.assertTrue(self.entrada_vazia)
        self.assertEqual(len(self.catalogo), 0)

    def test_quem_ja_esperava_nao_e_renomeado(self):
        primeiro = self.processar_sem_ocr(self.largar_exemplo("conta_energia_marco.txt"))
        de_novo = self.processar_sem_ocr(primeiro.destino)

        self.assertEqual(de_novo.destino, primeiro.destino)
        self.assertTrue(primeiro.destino.exists())

    def test_com_ocr_sai_da_espera_e_e_arquivado(self):
        esperando = self.processar_sem_ocr(self.largar_exemplo("conta_energia_marco.txt")).destino
        resultado = self.pipeline.processar(esperando)

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.categoria, "conta_luz")
        self.assertFalse(esperando.exists())


class TestDocumentoIlegivel(BasePipeline):
    """Não deu para ler: o arquivo não pode ficar preso na pasta de entrada.

    Deixado ali, ele seria reexaminado a cada abertura do programa e ninguém
    saberia que existe.
    """

    def processar_ilegivel(self, motivo="Tesseract nao esta instalado"):
        alvo = self.largar_exemplo("conta_energia_marco.txt")
        with mock.patch.object(pipeline_modulo, "extrair_com_origem",
                               side_effect=ExtracaoIndisponivel(motivo)), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            return self.pipeline.processar(alvo)

    def test_vai_para_revisao(self):
        resultado = self.processar_ilegivel()

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertEqual(resultado.destino.parent.name, PASTA_REVISAO)

    def test_a_pasta_de_entrada_esvazia(self):
        self.processar_ilegivel()
        self.assertTrue(self.entrada_vazia)

    def test_o_motivo_fica_escrito_na_ficha(self):
        resultado = self.processar_ilegivel("Tesseract nao esta instalado")

        self.assertIn("Tesseract", resultado.documento.regra)
        self.assertIn("não foi possível ler", resultado.documento.regra)
        self.assertEqual(resultado.documento.confianca, 0.0)

    def test_o_motivo_aparece_no_trajeto(self):
        resultado = self.processar_ilegivel("PDF ilegível: arquivo truncado")
        extracao = resultado.documento.etapas[1]

        self.assertEqual(extracao["titulo"], "Extração de texto")
        self.assertIn("truncado", extracao["detalhe"])

    def test_erro_do_sistema_de_arquivos_tambem_conta(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")
        with mock.patch.object(pipeline_modulo, "extrair_com_origem",
                               side_effect=OSError("sem permissao")), \
             self.assertLogs("autodoc.pipeline", "WARNING"):
            resultado = self.pipeline.processar(alvo)

        self.assertEqual(resultado.categoria, NAO_CLASSIFICADO)
        self.assertIn("sem permissao", resultado.documento.regra)


class TestNomeLivre(BasePipeline):
    def test_terceira_colisao_vira_3(self):
        pasta = self.config.pasta_saida / "conta_luz"
        pasta.mkdir(parents=True)
        for nome in ("a.txt", "a (2).txt"):
            (pasta / nome).write_text("ocupado", encoding="utf-8")

        self.assertEqual(self.pipeline._nome_livre(pasta / "a.txt").name, "a (3).txt")


class TestBackupDeRevisao(BasePipeline):
    def test_o_backup_usa_a_mesma_pasta_de_revisao(self):
        """Para o backup não virar uma organização paralela e diferente."""
        self.config.pasta_backup = self.base / "drive"
        self.config.preparar_pastas()

        self.pipeline.processar(self.largar_exemplo("scan0031_ilegivel.txt"))

        self.assertTrue(
            (self.config.pasta_backup / PASTA_REVISAO / "scan0031_ilegivel.txt").exists())


class TestAnalisar(BasePipeline):
    """A releitura que a reconciliação usa — sem mover nada."""

    def test_le_e_classifica_sem_mover(self):
        destino = self.config.pasta_saida / "conta_luz" / "2026" / "03"
        destino.mkdir(parents=True)
        alvo = destino / "conta_energia_marco.txt"
        alvo.write_text((EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8"),
                        encoding="utf-8")

        ficha = self.pipeline.analisar(alvo)

        self.assertEqual(ficha.categoria, "conta_luz")
        self.assertTrue(alvo.exists(), "não pode ter sido movido")
        self.assertEqual(ficha.etapas[0]["titulo"], "Releitura")

    def test_arquivo_ilegivel_vira_ficha_com_o_motivo(self):
        alvo = self.config.pasta_saida / "quebrado.pdf"
        alvo.write_bytes(b"isto nao e um PDF")

        # o pypdf reclama no log dele ao ver o arquivo torto; é o esperado aqui
        pypdf = logging.getLogger("pypdf")
        nivel = pypdf.level
        pypdf.setLevel(logging.CRITICAL)
        self.addCleanup(pypdf.setLevel, nivel)

        with self.assertLogs("autodoc.pipeline", "WARNING"):
            ficha = self.pipeline.analisar(alvo)

        self.assertEqual(ficha.texto, "")
        self.assertIn("nao foi possivel ler", ficha.origem)


class TestDiario(BasePipeline):
    """Todo arquivo que sai do lugar deixa anotado de onde veio."""

    def movimentos(self):
        return [json.loads(l) for l in self.catalogo.movimentos.read_text(encoding="utf-8").splitlines()]

    def test_arquivado(self):
        alvo = self.largar_exemplo("conta_energia_marco.txt")
        resultado = self.pipeline.processar(alvo)
        self.assertEqual(self.movimentos(), [{**self.movimentos()[0],
                                              "origem": str(alvo), "destino": str(resultado.destino)}])

    def test_duplicado(self):
        self.pipeline.processar(self.largar_exemplo("conta_energia_marco.txt"))
        copia = self.largar_exemplo("conta_energia_marco.txt", "copia.txt")
        resultado = self.pipeline.processar(copia)
        self.assertEqual(self.movimentos()[-1]["origem"], str(copia))
        self.assertEqual(self.movimentos()[-1]["destino"], str(resultado.destino))

    def test_o_que_nao_sai_do_lugar_nao_e_anotado(self):
        alvo = self.config.pasta_entrada / "instalador.dmg"
        alvo.write_bytes(b"x")
        self.pipeline.processar(alvo)
        self.assertFalse(self.catalogo.movimentos.exists())


class TestIdentificadoPeloTipo(BasePipeline):
    """O que nao e documento sai identificado, e nao em `_Revisar/` com 0%."""

    def imagem(self, nome: str, tamanho: tuple[int, int], capturada: str | None = None) -> Path:
        from PIL import Image

        alvo = self.config.pasta_entrada / nome
        exif = Image.Exif()
        if capturada:
            exif.get_ifd(0x8769)[36867] = capturada
        Image.new("RGB", tamanho, "white").save(alvo, exif=exif)
        return alvo

    def processar_com_ocr(self, alvo: Path, lido: str):
        with mock.patch.object(pipeline_modulo, "extrair_com_origem",
                               return_value=(lido, "imagem — OCR")):
            return self.pipeline.processar(alvo)

    def pasta_de(self, resultado) -> str:
        return resultado.destino.parent.relative_to(self.config.pasta_saida).as_posix()

    def test_icone_sem_texto(self):
        resultado = self.processar_com_ocr(self.imagem("botao.jpg", (16, 16)), "")

        self.assertEqual(self.pasta_de(resultado), "imagens/sem-data")
        self.assertIn("ícone ou elemento de interface (16×16)", resultado.documento.regra)
        self.assertEqual(resultado.documento.confianca, 1.0)

    def test_foto_vai_para_o_mes_da_captura(self):
        alvo = self.imagem("praia.jpg", (1600, 900), "2025:12:24 18:30:00")
        resultado = self.processar_com_ocr(alvo, "a 7 ~~")

        self.assertEqual(self.pasta_de(resultado), "imagens/2025/12")
        self.assertIn("foto ou imagem (1600×900)", resultado.documento.regra)
        self.assertIn("EXIF", resultado.etapas[3]["detalhe"])

    def test_imagem_que_o_pillow_nao_mede(self):
        alvo = self.config.pasta_entrada / "estranha.png"
        alvo.write_bytes(b"nada")
        resultado = self.processar_com_ocr(alvo, "")

        self.assertEqual(self.pasta_de(resultado), "imagens/sem-data")
        self.assertTrue(resultado.documento.regra.startswith("imagem, sem texto"))

    def test_foto_de_conta_continua_conta(self):
        alvo = self.imagem("conta.jpg", (1600, 1200))
        resultado = self.processar_com_ocr(alvo, (EXEMPLOS / "conta_energia_marco.txt").read_text(encoding="utf-8"))

        self.assertEqual(resultado.categoria, "conta_luz")

    def test_foto_com_termo_fraco_e_duvida_de_verdade(self):
        resultado = self.processar_com_ocr(self.imagem("tela.jpg", (800, 600)), "pague com pix")

        self.assertEqual(self.pasta_de(resultado), PASTA_REVISAO)

    def test_arquivo_de_versao(self):
        alvo = self.config.pasta_entrada / "mono-version.txt"
        alvo.write_text("8.0.29\n", encoding="utf-8")
        resultado = self.pipeline.processar(alvo)

        self.assertEqual(self.pasta_de(resultado), "textos/sem-data")
        self.assertIn('("8.0.29")', resultado.documento.regra)

    def test_texto_com_frase_nao_identificada_vai_para_revisao(self):
        alvo = self.config.pasta_entrada / "lista.txt"
        alvo.write_text("arroz, feijao, cafe", encoding="utf-8")

        self.assertEqual(self.pasta_de(self.pipeline.processar(alvo)), PASTA_REVISAO)

    def test_texto_vazio_vai_para_revisao(self):
        alvo = self.config.pasta_entrada / "vazio.txt"
        alvo.write_text("   \n", encoding="utf-8")

        self.assertEqual(self.pasta_de(self.pipeline.processar(alvo)), PASTA_REVISAO)

    def test_releitura_tambem_identifica(self):
        pasta = self.config.pasta_saida / "imagens" / "sem-data"
        pasta.mkdir(parents=True)
        alvo = pasta / "logo.jpg"
        from PIL import Image
        Image.new("RGB", (64, 64)).save(alvo)

        with mock.patch.object(pipeline_modulo, "extrair_com_origem", return_value=("", "imagem — OCR")):
            ficha = self.pipeline.analisar(alvo)

        self.assertEqual(ficha.categoria, "imagens")
        self.assertEqual(ficha.data_pasta, None)


if __name__ == "__main__":
    unittest.main()
