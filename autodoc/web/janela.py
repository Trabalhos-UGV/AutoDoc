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

import contextlib
import logging
import shutil
import sys
import webbrowser

logger = logging.getLogger(__name__)

# O que instalar, por familia de distribuicao, para o pywebview achar um motor.
#
# No Linux o motor nao vem do pip: ele e o WebKitGTK do proprio sistema, mais o
# `gi` (PyGObject) que faz a ponte. Mandar "pip install" aqui e o conselho
# errado — as dependencias Python ja estao instaladas, e tentar resolver com
# `pip install pywebview[gtk]` cai na compilacao do PyGObject, que pede
# gobject-introspection, cairo e pkgconf. E o caminho mais rapido para se
# perder.
PACOTES_DO_MOTOR: dict[str, tuple[str, str]] = {
    "pacman": ("Arch, Manjaro", "sudo pacman -S python-gobject webkit2gtk-4.1"),
    "apt": ("Debian, Ubuntu, Mint", "sudo apt install python3-gi gir1.2-webkit2-4.1"),
    "dnf": ("Fedora, RHEL", "sudo dnf install python3-gobject webkit2gtk4.1"),
    "zypper": ("openSUSE", "sudo zypper install python3-gobject typelib-1_0-WebKit2-4_1"),
}


def receita_do_motor() -> tuple[str, str] | None:
    """O comando que instala o motor grafico nesta maquina, se for Linux.

    Descobre a familia pelo gerenciador de pacotes que existe no PATH, que e
    mais confiavel do que ler /etc/os-release e mapear nomes de distribuicao.
    """
    if not sys.platform.startswith("linux"):
        return None
    for gerenciador, (familia, comando) in PACOTES_DO_MOTOR.items():
        if shutil.which(gerenciador):
            return familia, comando
    return None

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


def _como_resolver() -> str:
    """A instrucao certa para esta maquina — e nao a generica de sempre."""
    receita = receita_do_motor()
    if receita:
        familia, comando = receita
        return (
            f"\n  Para ter a janela propria ({familia}), instale o motor do sistema:"
            f"\n      {comando}"
            f"\n  Depois rode a instalacao de novo. Nao use `pip install"
            f" pywebview[gtk]`:"
            f"\n  ele tenta compilar o PyGObject e falha sem os headers de"
            f" desenvolvimento."
        )
    if sys.platform.startswith("linux"):
        return (
            "\n  Para ter a janela propria, instale o PyGObject e o WebKitGTK"
            "\n  pelo gerenciador de pacotes da sua distribuicao."
        )
    return (
        "\n  Para ter a janela propria, instale as dependencias:"
        "\n      pip install -r requirements.txt"
    )


@contextlib.contextmanager
def _pywebview_calado():
    """Cala o log do pywebview enquanto se descobre se ha motor grafico.

    Ao procurar um motor, ele tenta importar GTK e depois Qt e registra cada
    tentativa fracassada com `logger.exception` — dois tracebacks completos, um
    pelo handler proprio dele e outro pela raiz. Num Linux sem WebKitGTK isso
    enche a tela de pilha de excecao para depois cair no navegador e funcionar,
    e quem ve conclui que o programa quebrou. Nao quebrou: a busca por motor
    falhar e uma resposta, nao um defeito.
    """
    registro = logging.getLogger("pywebview")
    nivel, propaga = registro.level, registro.propagate
    registro.setLevel(logging.CRITICAL)
    registro.propagate = False
    try:
        yield
    finally:
        registro.setLevel(nivel)
        registro.propagate = propaga


def _ha_motor_grafico() -> str | None:
    """Descobre se existe motor para desenhar a janela.

    Devolve None quando ha, e o motivo quando nao ha. A pergunta e feita ao
    proprio pywebview, em silencio, **antes** de abrir a janela — assim a queda
    para o navegador acontece limpa, com uma explicacao no lugar de dois
    tracebacks.
    """
    try:
        from webview.guilib import initialize
    except ImportError:  # versao de pywebview que nao expoe a sondagem
        return None

    with _pywebview_calado():
        try:
            initialize()
        except Exception as erro:
            return f"{type(erro).__name__}: {erro}"
    return None


def _cair_no_navegador(url: str, motivo: str) -> str:
    logger.warning("janela nativa indisponivel (%s); abrindo no navegador", motivo)
    print(
        f"\n  Nao consegui abrir a janela do AutoDoc: {motivo}."
        f"\n  Abrindo no navegador: {url}"
        f"{_como_resolver()}\n"
    )
    webbrowser.open(url)
    return "navegador"


def abrir(
    url: str,
    titulo: str = "AutoDoc",
    largura: int = LARGURA_PADRAO,
    altura: int = ALTURA_PADRAO,
    redimensionavel: bool = True,
    minimo: tuple[int, int] = TAMANHO_MINIMO,
    fundo: str = "#110f0b",
    ao_criar=None,
) -> str:
    """Abre a janela e bloqueia ate ela ser fechada.

    Devolve 'nativa' ou 'navegador', conforme o que deu para fazer. Precisa ser
    chamada da thread principal.

    `ao_criar` recebe a janela recem-criada. E por onde o instalador guarda a
    referencia de que precisa para abrir o seletor de pastas do sistema — sem
    isso ele teria que repetir aqui toda a logica de queda para o navegador, e
    foi exatamente essa copia que deixou o instalador quebrando no Linux
    enquanto o aplicativo caia no navegador direitinho.
    """
    try:
        import webview
    except ImportError:
        return _cair_no_navegador(url, "pywebview nao instalado")

    sem_motor = _ha_motor_grafico()
    if sem_motor:
        return _cair_no_navegador(url, sem_motor)

    try:
        janela = webview.create_window(
            titulo,
            url,
            width=largura,
            height=altura,
            min_size=minimo,
            resizable=redimensionavel,
            background_color=fundo,  # evita o flash branco antes de pintar
        )
        if ao_criar is not None:
            ao_criar(janela)
        webview.start()
    except Exception as erro:  # o motor nativo pode faltar no Linux
        return _cair_no_navegador(url, f"{type(erro).__name__}: {erro}")

    return "nativa"
