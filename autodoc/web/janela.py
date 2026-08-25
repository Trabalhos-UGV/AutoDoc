"""Janela nativa do AutoDoc.

O AutoDoc e um programa local, e programa local nao mora numa aba de navegador.
Aqui as telas sao desenhadas numa janela do proprio sistema — WebKit no macOS,
WebView2 no Windows, GTK no Linux —, sem barra de endereco e sem aba. E o mesmo
arranjo que VS Code, Slack e Spotify usam: o conteudo e HTML, mas a moldura e do
programa.

Por dentro continua havendo um servidor local, que e quem entrega o HTML e
responde a API. O usuario nunca ve isso.

**A janela precisa da thread principal.** No macOS o Cocoa so aceita criar
janela na thread principal do processo, entao quem roda em segundo plano e o
servidor; `abrir()` bloqueia ate a janela ser fechada.

Se o webview nativo nao estiver disponivel — comum no Linux, que costuma exigir
pacotes do sistema —, cai no navegador e avisa, em vez de morrer. E o mesmo
padrao que o extrator usa quando falta o Tesseract: perde-se o recurso, nao o
programa.
"""

from __future__ import annotations

import logging
import webbrowser

logger = logging.getLogger(__name__)

LARGURA_PADRAO = 1280
ALTURA_PADRAO = 840

# Abaixo disto a tela de gerenciamento comeca a empilhar as colunas; nao faz
# sentido deixar encolher mais do que o proprio layout aguenta com folga.
TAMANHO_MINIMO = (960, 640)


class JanelaIndisponivel(RuntimeError):
    """Nao ha webview nativo utilizavel nesta maquina."""


def disponivel() -> bool:
    """Diz se da para abrir janela nativa aqui, sem tentar abrir."""
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


def _cair_no_navegador(url: str, motivo: str) -> str:
    logger.warning("janela nativa indisponivel (%s); abrindo no navegador", motivo)
    print(
        f"\n  Nao consegui abrir a janela do AutoDoc: {motivo}."
        f"\n  Abrindo no navegador: {url}"
        f"\n  Para ter a janela propria, instale as dependencias:"
        f"\n      pip install -r requirements.txt\n"
    )
    webbrowser.open(url)
    return "navegador"


def abrir(
    url: str,
    titulo: str = "AutoDoc",
    largura: int = LARGURA_PADRAO,
    altura: int = ALTURA_PADRAO,
    redimensionavel: bool = True,
) -> str:
    """Abre a janela e bloqueia ate ela ser fechada.

    Devolve 'nativa' ou 'navegador', conforme o que deu para fazer. Precisa ser
    chamada da thread principal.
    """
    try:
        import webview
    except ImportError:
        return _cair_no_navegador(url, "pywebview nao instalado")

    try:
        webview.create_window(
            titulo,
            url,
            width=largura,
            height=altura,
            min_size=TAMANHO_MINIMO,
            resizable=redimensionavel,
            background_color="#110f0b",  # evita o flash branco antes de pintar
        )
        webview.start()
    except Exception as erro:  # o motor nativo pode faltar no Linux
        return _cair_no_navegador(url, f"{type(erro).__name__}: {erro}")

    return "nativa"
