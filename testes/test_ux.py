"""A parte pura dos testes de usabilidade (ferramentas/ux.py).

Os cinco comandos rodam de verdade pelo terminal; aqui se confere so o que eles
calculam — a conta de contraste e a leitura do HTML —, para a ferramenta nao
aprovar ou reprovar errado sem ninguem perceber.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

_CAMINHO = Path(__file__).resolve().parent.parent / "ferramentas" / "ux.py"
_ESPEC = importlib.util.spec_from_file_location("ux", _CAMINHO)
ux = importlib.util.module_from_spec(_ESPEC)
_ESPEC.loader.exec_module(ux)


def ler(html: str):
    leitor = ux._LeitorDeTela()
    leitor.feed(html)
    return leitor


class TestContraste(unittest.TestCase):
    def test_extremos_da_wcag(self):
        self.assertAlmostEqual(ux.razao_de_contraste("#000000", "#ffffff"), 21.0)
        self.assertAlmostEqual(ux.razao_de_contraste("#777", "#777777"), 1.0)

    def test_valor_conhecido(self):
        # #767676 sobre branco e o cinza mais claro que passa no 4,5:1.
        self.assertGreaterEqual(ux.razao_de_contraste("#767676", "#ffffff"), 4.5)
        self.assertLess(ux.razao_de_contraste("#777777", "#ffffff"), 4.5)

    def test_sugestao_passa_no_minimo(self):
        sugerida = ux._clarear_ate("#65635d", "#181611", 4.5)
        self.assertGreaterEqual(ux.razao_de_contraste(sugerida, "#181611"), 4.5)
        # Impossivel de atingir: vai ate o branco (cor mais clara que o fundo) ou o preto.
        self.assertEqual(ux._clarear_ate("#131313", "#121212", 30), "#ffffff")
        self.assertEqual(ux._clarear_ate("#111111", "#121212", 30), "#000000")
        self.assertGreaterEqual(ux.razao_de_contraste(ux._clarear_ate("#888888", "#ffffff", 4.5), "#ffffff"), 4.5)

    def test_paleta_lida_do_css(self):
        cores = ux._cores_da_paleta("--ad-fundo: #110f0b;\n  --ad-acento-fraco: rgba(1, 2, 3, 0.1);")
        self.assertEqual(cores, {"fundo": "#110f0b"})


class TestLeitorDeTela(unittest.TestCase):
    def test_pagina_em_ordem(self):
        leitor = ler(
            '<html lang="pt-BR"><head><title>AutoDoc</title><meta name="viewport" content="x"></head><body>'
            '<button>Abrir</button><button aria-label="Fechar">×</button><a href="#">ir</a>'
            '<img src="a.png" alt=""><canvas aria-hidden="true"></canvas><canvas aria-label="tabuleiro"></canvas>'
            '<label for="busca">Buscar</label><input id="busca"><label>Nome <input></label>'
            '<input aria-label="pasta"><input type="hidden"></body></html>'
        )
        self.assertEqual(leitor.problemas, [])
        self.assertEqual((leitor.idioma, leitor.titulo, leitor.viewport), ("pt-BR", "AutoDoc", True))
        self.assertTrue(all(a.get("aria-label") or a["_em_label"] or a.get("id") in leitor.rotulos_para for _, a in leitor.campos))

    def test_o_que_o_leitor_de_tela_nao_consegue_anunciar(self):
        leitor = ler('<html><body><img src="x.png"><canvas class="c"></canvas><button></button><a href="#"></a></body></html>')
        problemas = [problema for problema, _, _ in leitor.problemas]
        self.assertEqual(problemas, ["imagem sem alt", "desenho (canvas) sem descrição", "botão sem nome", "link sem nome"])
        self.assertIsNone(leitor.idioma)

    def test_botao_preenchido_pelo_javascript_nao_e_cobrado(self):
        self.assertEqual(ler('<button data-jogo-abrir></button>').problemas, [])


class TestTelasDoProjeto(unittest.TestCase):
    """Os comandos rapidos rodam inteiros aqui: as telas do projeto passam."""

    def rodar(self, comando):
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            codigo = ux.main([comando])
        return codigo, saida.getvalue()

    def test_contraste_aprovado(self):
        codigo, saida = self.rodar("contraste")
        self.assertEqual(codigo, 0, saida)

    def test_acessibilidade_aprovada(self):
        codigo, saida = self.rodar("acessibilidade")
        self.assertEqual(codigo, 0, saida)


if __name__ == "__main__":
    unittest.main()
