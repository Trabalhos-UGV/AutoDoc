"""Os personagens que cobrem o rosto de quem joga.

Sao os emojis 3D do Fluent Emoji, da Microsoft (licenca MIT), em PNG de
256x256 com fundo transparente. Ficam versionados em
`autodoc/web/estatico/personagens/` — a tela de escolha os mostra, e a mascara
os desenha por cima do rosto. Funciona sem internet, como as fontes.

A lista abaixo e a unica: `ferramentas/baixar_personagens.py` baixa a partir
dela, e o jogo so aceita nomes que estao nela. So entram rostos de frente — o
unicornio do Fluent, de perfil, nao cobre um rosto.
"""

from __future__ import annotations

from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "web" / "estatico" / "personagens"

# (nome interno, nome na tela, nome da pasta no Fluent Emoji)
PERSONAGENS = (
    ("cachorro", "Cachorro", "Dog face"),
    ("gato", "Gato", "Cat face"),
    ("raposa", "Raposa", "Fox"),
    ("panda", "Panda", "Panda"),
    ("leao", "Leão", "Lion"),
    ("tigre", "Tigre", "Tiger face"),
    ("sapo", "Sapo", "Frog"),
    ("macaco", "Macaco", "Monkey face"),
    ("coala", "Coala", "Koala"),
    ("porco", "Porco", "Pig face"),
    ("coelho", "Coelho", "Rabbit face"),
    ("urso", "Urso", "Bear"),
    ("hamster", "Hamster", "Hamster"),
    ("vaca", "Vaca", "Cow face"),
    ("lobo", "Lobo", "Wolf"),
)

NOMES = tuple(nome for nome, _, _ in PERSONAGENS)

# Os personagens 3D do avatar, feitos em js/avatar/fichas.js. O nome aqui
# precisa ser a chave da ficha la — um teste confere.
AVATARES = (
    ("caramelo", "Vira-lata caramelo"),
)

NOMES_AVATARES = tuple(nome for nome, _ in AVATARES)


def arquivo(nome: str) -> Path:
    return PASTA / f"{nome}.png"


def para_tela(avatar: bool = False) -> list[dict]:
    """A lista que a tela de escolha desenha: os 3D, ou os emojis da mascara 2D."""
    if avatar:
        return [{"nome": nome, "rotulo": rotulo} for nome, rotulo in AVATARES]
    return [{"nome": nome, "rotulo": rotulo, "imagem": f"personagens/{nome}.png"} for nome, rotulo, _ in PERSONAGENS]
