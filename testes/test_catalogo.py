"""O catalogo: fichas, busca e a pasta como fonte da verdade."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoc.catalogo import (
    NOME_CATALOGO,
    PASTA_CATALOGO,
    Catalogo,
    Ficha,
)


def ficha(nome="conta.txt", categoria="conta_luz", data="2026-03-12",
          texto="CEMIG consumo faturado 187 kWh", assinatura="h1", **extra):
    pasta = "_Revisar" if categoria == "nao_classificado" else f"{categoria}/2026/03"
    return Ficha(arquivo=nome, caminho=f"{pasta}/{nome}", categoria=categoria,
                 data_documento=data, texto=texto, hash=assinatura, **extra)


class BaseCatalogo(unittest.TestCase):
    def setUp(self):
        self._temporaria = tempfile.TemporaryDirectory()
        self.saida = Path(self._temporaria.name)
        self.catalogo = Catalogo(self.saida)
        self.addCleanup(self._temporaria.cleanup)

    def recarregar(self) -> Catalogo:
        """Um catalogo novo lendo o mesmo disco — prova o que foi gravado."""
        return Catalogo(self.saida)


class TestGravacao(BaseCatalogo):
    def test_catalogo_novo_nasce_vazio(self):
        self.assertEqual(len(self.catalogo), 0)
        self.assertTrue((self.saida / PASTA_CATALOGO).is_dir())

    def test_inserir_devolve_id_crescente(self):
        self.assertEqual(self.catalogo.inserir(ficha(assinatura="a")), 1)
        self.assertEqual(self.catalogo.inserir(ficha(nome="b.txt", assinatura="b")), 2)

    def test_documento_repetido_nao_entra_duas_vezes(self):
        self.catalogo.inserir(ficha(assinatura="mesma"))
        self.assertIsNone(self.catalogo.inserir(ficha(nome="copia.txt", assinatura="mesma")))
        self.assertEqual(len(self.catalogo), 1)

    def test_dedupe_e_por_conteudo_e_nao_por_nome(self):
        self.catalogo.inserir(ficha(nome="boleto.pdf", assinatura="igual"))
        self.catalogo.inserir(ficha(nome="boleto (1).pdf", assinatura="igual"))
        self.assertEqual(len(self.catalogo), 1)

    def test_ficha_sobrevive_ao_fechamento(self):
        self.catalogo.inserir(ficha())
        self.assertEqual(len(self.recarregar()), 1)

    def test_uma_linha_por_ficha(self):
        for i in range(3):
            self.catalogo.inserir(ficha(nome=f"{i}.txt", assinatura=f"h{i}"))
        linhas = (self.saida / PASTA_CATALOGO / NOME_CATALOGO).read_text(
            encoding="utf-8").strip().splitlines()
        self.assertEqual(len(linhas), 3)
        self.assertEqual(json.loads(linhas[0])["arquivo"], "0.txt")

    def test_linha_corrompida_nao_impede_a_leitura(self):
        """Uma queda no meio da escrita corta a ultima linha; o resto vale."""
        self.catalogo.inserir(ficha())
        caderno = self.saida / PASTA_CATALOGO / NOME_CATALOGO
        with caderno.open("a", encoding="utf-8") as arquivo:
            arquivo.write('{"arquivo": "cortada pela met\n')

        with self.assertLogs("autodoc.catalogo", "WARNING") as registro:
            relido = self.recarregar()
        self.assertEqual(len(relido), 1)
        self.assertIn("ilegivel", registro.output[0])

    def test_linha_em_branco_no_caderno_e_pulada(self):
        """Um editor de texto costuma deixar linha vazia no fim do arquivo."""
        self.catalogo.inserir(ficha())
        caderno = self.saida / PASTA_CATALOGO / NOME_CATALOGO
        with caderno.open("a", encoding="utf-8") as arquivo:
            arquivo.write("\n   \n")

        self.assertEqual(len(self.recarregar()), 1)

    def test_texto_gigante_e_truncado(self):
        from autodoc.catalogo import LIMITE_TEXTO
        guardada = ficha(texto="a" * (LIMITE_TEXTO + 5000))
        self.assertEqual(len(guardada.texto), LIMITE_TEXTO)


class TestAtualizacao(BaseCatalogo):
    def test_ficha_alterada_nao_deixa_a_versao_antiga(self):
        self.catalogo.inserir(ficha(categoria="nao_classificado", assinatura="h"))
        alvo = self.catalogo.por_id(1)
        alvo.categoria = "contrato"
        alvo.caminho = "contrato/2026/03/conta.txt"
        self.catalogo.atualizar(alvo)

        relido = self.recarregar()
        self.assertEqual(len(relido), 1)
        self.assertEqual(relido.por_id(1).categoria, "contrato")

    def test_correcao_aparece_na_contagem(self):
        self.catalogo.inserir(ficha(categoria="nao_classificado", assinatura="h"))
        alvo = self.catalogo.por_id(1)
        alvo.categoria = "contrato"
        self.catalogo.atualizar(alvo)
        self.assertEqual(self.catalogo.contar_por_categoria(), {"contrato": 1})


class TestCaminhos(BaseCatalogo):
    def test_caminho_dentro_da_saida_e_guardado_relativo(self):
        dentro = self.saida / "conta_luz" / "2026" / "03" / "a.txt"
        self.assertEqual(self.catalogo.relativo(dentro), "conta_luz/2026/03/a.txt")

    def test_caminho_fora_da_saida_e_guardado_absoluto(self):
        """Não dá para relativizar; guardar absoluto ao menos aponta para o arquivo."""
        fora = Path("/outro/lugar/documento.txt")
        self.assertEqual(self.catalogo.relativo(fora), str(fora))

    def test_pasta_de_saida_inexistente_nao_quebra_a_varredura(self):
        vazio = Catalogo(self.saida)
        vazio.pasta_saida = self.saida / "nao-existe"
        self.assertEqual(vazio.arquivos_no_disco(), [])

    def test_categoria_do_caminho(self):
        casos = [
            ("conta_luz/2026/03/a.txt", "conta_luz"),
            ("_Revisar/scan.txt", "nao_classificado"),
            ("pasta_inventada/2026/a.txt", None),
            ("solto.txt", None),
        ]
        for relativo, esperado in casos:
            with self.subTest(caminho=relativo):
                self.assertEqual(
                    self.catalogo.categoria_do_caminho(self.saida / relativo), esperado)


class TestReconciliarSemAnalisador(BaseCatalogo):
    """Sem o pipeline emprestado, a pasta sozinha já diz o essencial."""

    def test_ficha_minima_a_partir_do_caminho(self):
        destino = self.saida / "contrato" / "2026" / "03"
        destino.mkdir(parents=True)
        (destino / "aluguel.txt").write_text("contrato", encoding="utf-8")

        self.catalogo.reconciliar()

        ficha = self.catalogo.por_id(1)
        self.assertEqual(ficha.categoria, "contrato")
        self.assertIn("remontada", ficha.regra)
        self.assertGreater(ficha.tamanho, 0)

    def test_arquivo_que_some_no_meio_da_varredura(self):
        destino = self.saida / "contrato" / "2026" / "03"
        destino.mkdir(parents=True)
        alvo = destino / "some.txt"
        alvo.write_text("contrato", encoding="utf-8")

        def some_antes_de_fichar(caminho):
            alvo.unlink()
            raise OSError("arquivo sumiu")

        with self.assertLogs("autodoc.catalogo", "WARNING"):
            self.catalogo.reconciliar(some_antes_de_fichar)

        self.assertEqual(len(self.catalogo), 0)

    def test_analisador_que_devolve_nada_nao_ficha(self):
        destino = self.saida / "contrato" / "2026" / "03"
        destino.mkdir(parents=True)
        (destino / "a.txt").write_text("contrato", encoding="utf-8")

        self.catalogo.reconciliar(lambda _: None)
        self.assertEqual(len(self.catalogo), 0)


class TestConsulta(BaseCatalogo):
    def setUp(self):
        super().setUp()
        self.catalogo.inserir(ficha(
            nome="conta_energia_marco.txt", assinatura="a",
            texto="CEMIG consumo faturado 187 kWh demarcado",
            palavras_chave=["kWh", "CEMIG"], origem="arquivo de texto"))
        self.catalogo.inserir(ficha(
            nome="nota_fiscal_1234.txt", categoria="nota_fiscal", data="2026-03-08",
            texto="DANFE valor total da nota", assinatura="b", origem="imagem — OCR"))
        self.catalogo.inserir(ficha(
            nome="scan0031.txt", categoria="nao_classificado", data=None,
            texto="ilegivel", assinatura="c"))

    def nomes(self, resultado):
        return [linha["arquivo"] for linha in resultado]

    def test_lista_da_mais_recente_para_a_mais_antiga(self):
        self.assertEqual(self.nomes(self.catalogo.listar())[:2],
                         ["conta_energia_marco.txt", "nota_fiscal_1234.txt"])

    def test_documento_sem_data_vai_para_o_fim(self):
        self.assertEqual(self.nomes(self.catalogo.listar())[-1], "scan0031.txt")

    def test_filtra_por_categoria(self):
        self.assertEqual(self.nomes(self.catalogo.listar(categoria="nota_fiscal")),
                         ["nota_fiscal_1234.txt"])

    def test_caminho_sai_absoluto(self):
        caminho = Path(self.catalogo.listar()[0]["caminho"])
        self.assertTrue(caminho.is_absolute())
        self.assertTrue(str(caminho).startswith(str(self.saida)))

    def test_estatisticas(self):
        numeros = self.catalogo.estatisticas()
        self.assertEqual(numeros["arquivados"], 3)
        self.assertEqual(numeros["ocr"], 1)
        self.assertEqual(numeros["revisar"], 1)
        self.assertEqual(numeros["hoje"], 3)


class TestBusca(BaseCatalogo):
    def setUp(self):
        super().setUp()
        self.catalogo.inserir(ficha(
            nome="conta_energia_marco.txt", assinatura="a",
            texto="CEMIG consumo faturado 187 kWh demarcado no mês",
            palavras_chave=["kWh"]))
        self.catalogo.inserir(ficha(
            nome="nota_fiscal_1234.txt", categoria="nota_fiscal", data="2026-03-08",
            texto="DANFE valor total da nota", assinatura="b"))

    def nomes(self, termo):
        return sorted(linha["arquivo"] for linha in self.catalogo.buscar(termo))

    def test_acha_pelo_conteudo(self):
        self.assertEqual(self.nomes("kwh"), ["conta_energia_marco.txt"])

    def test_acha_por_prefixo(self):
        self.assertEqual(self.nomes("marc"), ["conta_energia_marco.txt"])

    def test_prefixo_nao_casa_no_meio_da_palavra(self):
        """O defeito que o LIKE tinha: "marco" nao pode vir de "demarcado"."""
        self.assertEqual(self.nomes("emarcado"), [])

    def test_ignora_acento_dos_dois_lados(self):
        self.assertEqual(self.nomes("mes"), ["conta_energia_marco.txt"])
        self.assertEqual(self.nomes("mês"), ["conta_energia_marco.txt"])

    def test_acha_pelo_rotulo_da_categoria(self):
        """Procurar "energia" acha o que esta guardado como conta_luz."""
        self.assertIn("conta_energia_marco.txt", self.nomes("energia"))

    def test_todas_as_palavras_precisam_aparecer(self):
        self.assertEqual(self.nomes("cemig kwh"), ["conta_energia_marco.txt"])
        self.assertEqual(self.nomes("cemig danfe"), [])

    def test_termo_vazio_devolve_a_listagem(self):
        self.assertEqual(len(self.catalogo.buscar("")), 2)
        self.assertEqual(len(self.catalogo.buscar("   ")), 2)

    def test_termo_sem_resultado(self):
        self.assertEqual(self.nomes("bicicleta"), [])

    def test_pontuacao_digitada_nao_quebra_a_busca(self):
        """Aspas e asteriscos tem significado no FTS5 e quebravam a consulta.

        Aqui eles sao so pontuacao: viram separador de palavra e somem.
        """
        for termo in ['"kwh"', "kwh!!!", "*kwh*", "kwh, 187"]:
            with self.subTest(termo=termo):
                self.assertEqual(self.nomes(termo), ["conta_energia_marco.txt"])

    def test_palavra_solta_a_mais_restringe_em_vez_de_ampliar(self):
        """Toda palavra digitada e uma exigencia, inclusive "OR"."""
        self.assertEqual(self.nomes("kwh OR danfe"), [])

    def test_busca_funciona_depois_de_recarregar(self):
        self.catalogo = self.recarregar()
        self.assertEqual(self.nomes("kwh"), ["conta_energia_marco.txt"])


if __name__ == "__main__":
    unittest.main()
