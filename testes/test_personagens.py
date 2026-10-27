"""Os personagens do Tetris: a lista e os arquivos que ela promete."""

from __future__ import annotations

import struct
import unittest

from autodoc.gestos import personagens


class TestPersonagens(unittest.TestCase):
    def test_todo_personagem_tem_o_seu_png(self):
        for nome in personagens.NOMES:
            dados = personagens.arquivo(nome).read_bytes()
            self.assertEqual(dados[:8], b"\x89PNG\r\n\x1a\n", nome)
            largura, altura, _, cor = struct.unpack(">IIBB", dados[16:26])
            self.assertEqual((largura, altura), (256, 256), nome)
            self.assertEqual(cor, 6, f"{nome} precisa ter transparencia (RGBA)")

    def test_nomes_unicos_e_licenca_junto(self):
        self.assertEqual(len(set(personagens.NOMES)), len(personagens.NOMES))
        self.assertIn("MIT", (personagens.PASTA / "LICENCA-fluent-emoji.txt").read_text())

    def test_todo_avatar_tem_ficha_no_javascript(self):
        fichas = (personagens.PASTA.parent / "js" / "avatar" / "fichas.js").read_text(encoding="utf-8")
        for nome in personagens.NOMES_AVATARES:
            self.assertIn(f"  {nome}: {{", fichas, nome)
        self.assertEqual(personagens.para_tela(avatar=True)[0], {"nome": "caramelo", "rotulo": "Vira-lata caramelo"})

    def test_lista_para_a_tela(self):
        primeiro = personagens.para_tela()[0]
        self.assertEqual(primeiro, {"nome": "cachorro", "rotulo": "Cachorro", "imagem": "personagens/cachorro.png"})
        self.assertEqual(len(personagens.para_tela()), 15)


if __name__ == "__main__":
    unittest.main()
