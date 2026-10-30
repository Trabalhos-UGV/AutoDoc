"""Testes de usabilidade (UX) automaticos do AutoDoc.

Cada comando roda sozinho, sem ninguem clicar em nada, e termina com um
parecer: o que passou, o que falhou e o que fazer a respeito.

    python3 ferramentas/ux.py contraste        legibilidade: contraste das cores do texto (WCAG)
    python3 ferramentas/ux.py acessibilidade   telas usaveis por leitor de tela e teclado
    python3 ferramentas/ux.py responsivo       telas em janela grande, media e de celular
    venv/bin/python ferramentas/ux.py tempo    tempo de resposta do app e do Tetris
    venv/bin/python ferramentas/ux.py tarefa   tarefas de ponta a ponta, como uma pessoa faria
    venv/bin/python ferramentas/ux.py todos    os cinco, um atras do outro

`tempo` e `tarefa` sobem o AutoDoc de verdade numa pasta temporaria, entao
precisam das dependencias do projeto — rode com o Python do venv. Nenhum deles
toca nos seus documentos nem no config.json.

`responsivo` precisa de um Chrome ou Chromium instalado; sem ele, o teste e
pulado (e diz isso), em vez de falhar.

Saida: 0 se nada falhou, 1 se algo falhou. Avisos nao reprovam — sao coisas
que valem olhar, mas nao impedem ninguem de usar o programa.

Como o resto de ferramentas/, este script nao entra no caminho de execucao do
programa; existe para o grupo poder repetir a medida.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESTATICO = RAIZ / "autodoc" / "web" / "estatico"
SITE = RAIZ / "site"

# ---------------------------------------------------------------- relatorio

_COR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _pintar(texto: str, codigo: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if _COR else texto


class Relatorio:
    """O parecer de um teste: cada achado, e o resumo no fim."""

    def __init__(self, titulo: str, objetivo: str) -> None:
        self.titulo = titulo
        self.falhas = 0
        self.avisos = 0
        self.acertos = 0
        print()
        print(_pintar(f"■ {titulo}", "1"))
        print(_pintar(f"  {objetivo}", "2"))
        print()

    def ok(self, texto: str) -> None:
        self.acertos += 1
        print(f"  {_pintar('✔', '32')} {texto}")

    def aviso(self, texto: str, dica: str = "") -> None:
        self.avisos += 1
        print(f"  {_pintar('!', '33')} {texto}")
        if dica:
            print(_pintar(f"      → {dica}", "2"))

    def falha(self, texto: str, dica: str = "") -> None:
        self.falhas += 1
        print(f"  {_pintar('✘', '31')} {texto}")
        if dica:
            print(_pintar(f"      → {dica}", "2"))

    def pulado(self, texto: str) -> None:
        print(f"  {_pintar('–', '2')} {texto}")

    def fechar(self) -> bool:
        partes = [f"{self.acertos} ok", f"{self.avisos} aviso(s)", f"{self.falhas} falha(s)"]
        if self.falhas:
            parecer = _pintar("REPROVADO", "31;1")
        elif self.avisos:
            parecer = _pintar("APROVADO COM RESSALVAS", "33;1")
        else:
            parecer = _pintar("APROVADO", "32;1")
        print(f"\n  {parecer} — " + ", ".join(partes))
        return self.falhas == 0


# ----------------------------------------------------------- 1. contraste


def _cores_da_paleta(css: str) -> dict[str, str]:
    return {nome: valor for nome, valor in re.findall(r"--ad-([\w-]+):\s*(#[0-9a-fA-F]{3,6})\s*;", css)}


def luminancia(hexa: str) -> float:
    """Luminancia relativa da WCAG 2.x, de 0 (preto) a 1 (branco)."""
    hexa = hexa.lstrip("#")
    if len(hexa) == 3:
        hexa = "".join(c * 2 for c in hexa)
    canais = []
    for i in (0, 2, 4):
        c = int(hexa[i:i + 2], 16) / 255
        canais.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canais
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razao_de_contraste(frente: str, fundo: str) -> float:
    claro, escuro = sorted((luminancia(frente), luminancia(fundo)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


# (cor do texto, cor do fundo, minimo, onde aparece). 4,5:1 e o minimo da WCAG
# AA para texto comum; 3:1 so vale para texto grande (24 px, ou 18,7 px negrito).
PARES_DE_TEXTO = (
    ("tinta", "fundo", 4.5, "texto principal das telas"),
    ("texto", "cartao", 4.5, "texto dentro dos cartões"),
    ("apagado", "painel", 4.5, "texto secundário da lateral"),
    ("fraco", "fundo", 4.5, "rótulos em versalete (10,5 px)"),
    ("fraco", "cartao", 4.5, "rótulos dentro dos cartões"),
    # A cor mais fraca nao e para texto de leitura: so icones e botao
    # desabilitado (a WCAG dispensa os dois do 4,5:1; icone precisa de 3:1).
    ("fantasma", "cartao", 3.0, "ícones e botão desabilitado (não é texto de leitura)"),
    ("acento", "fundo", 4.5, "links e destaques em amarelo"),
    ("fundo", "acento", 4.5, "texto do botão principal (amarelo)"),
    ("verde", "painel", 4.5, "estado \"watchdog ativo\""),
)


def testar_contraste(_args) -> bool:
    r = Relatorio(
        "Contraste do texto",
        "Mede se cada cor de texto se lê contra o fundo em que aparece (WCAG 2.1, nível AA).",
    )
    cores = _cores_da_paleta((ESTATICO / "css" / "base.css").read_text(encoding="utf-8"))
    for frente, fundo, minimo, onde in PARES_DE_TEXTO:
        if frente not in cores or fundo not in cores:
            r.aviso(f"cor --ad-{frente} ou --ad-{fundo} não existe mais em base.css", "atualize PARES_DE_TEXTO")
            continue
        razao = razao_de_contraste(cores[frente], cores[fundo])
        texto = f"{onde}: {razao:.2f}:1  (--ad-{frente} sobre --ad-{fundo}, mínimo {minimo}:1)"
        if razao >= minimo:
            r.ok(texto)
        else:
            alvo = _clarear_ate(cores[frente], cores[fundo], minimo)
            r.falha(texto, f"quem tem a vista cansada não lê isto; {alvo} já passaria")
    _vigiar_cor_decorativa(r)
    return r.fechar()


# Seletores que podem usar a cor decorativa como cor de texto.
DECORATIVA_PERMITIDA = (":disabled",)


def _vigiar_cor_decorativa(r: Relatorio) -> None:
    """Texto pintado com --ad-fantasma fica abaixo do 4,5:1: so icone e desabilitado podem."""
    errados = []
    for css in sorted(ESTATICO.glob("css/*.css")) + sorted(SITE.glob("css/*.css")):
        for seletor, regras in re.findall(r"([^{}]+)\{([^{}]*)\}", css.read_text(encoding="utf-8")):
            if re.search(r"(?<![-\w])color:\s*var\(--ad-fantasma\)", regras):
                seletor = " ".join(seletor.split())
                if not any(permitido in seletor for permitido in DECORATIVA_PERMITIDA):
                    errados.append(f"{css.relative_to(RAIZ)}: {seletor}")
    if errados:
        for errado in errados:
            r.falha(f"texto com a cor decorativa --ad-fantasma — {errado}", "use --ad-fraco, que passa no 4,5:1")
    else:
        r.ok("nenhum texto de leitura usa a cor decorativa --ad-fantasma")


def _clarear_ate(frente: str, fundo: str, minimo: float) -> str:
    """A cor mais proxima de `frente`, na mesma direcao, que atinge o minimo."""
    hexa = frente.lstrip("#")
    canais = [int(hexa[i:i + 2], 16) for i in (0, 2, 4)]
    clarear = luminancia(frente) >= luminancia(fundo)
    for passo in range(1, 256):
        novos = [min(255, c + passo) if clarear else max(0, c - passo) for c in canais]
        candidata = "#" + "".join(f"{c:02x}" for c in novos)
        if razao_de_contraste(candidata, fundo) >= minimo:
            return candidata
    return "#ffffff" if clarear else "#000000"


# ------------------------------------------------------- 2. acessibilidade


DICAS = {
    "imagem": "o leitor de tela anuncia \"imagem\" sem dizer de quê; use alt=\"\" se for só enfeite",
    "canvas": "o leitor de tela pula o desenho; aria-label diz o que ele mostra, aria-hidden se for repetição",
    "botao": "o leitor de tela anuncia só \"botão\"; ponha texto, aria-label ou title",
    "campo": "quem não enxerga não sabe o que digitar; ligue um <label> ou use aria-label",
    "idioma": "sem lang, o leitor de tela lê português com sotaque de inglês",
    "titulo": "o título é o que aparece na barra e no alternador de janelas",
}


class _LeitorDeTela(HTMLParser):
    """Le o HTML como um leitor de tela leria: o que tem nome, o que nao tem."""

    VAZIOS = {"img", "input", "meta", "link", "br", "hr"}

    def __init__(self) -> None:
        super().__init__()
        self.problemas: list[tuple[str, str]] = []
        self.idioma = None
        self.titulo = ""
        self.viewport = False
        self.rotulos_para: set[str] = set()
        self.campos: list[tuple[str, dict]] = []
        self._pilha: list[dict] = []
        self._no_titulo = False
        self._dentro_de_label = 0

    def handle_starttag(self, tag, atributos):
        a = dict(atributos)
        if tag == "html":
            self.idioma = a.get("lang")
        elif tag == "title":
            self._no_titulo = True
        elif tag == "meta" and a.get("name") == "viewport":
            self.viewport = True
        elif tag == "img" and "alt" not in a:
            self.problemas.append(("imagem sem alt", self._descrever(tag, a), DICAS["imagem"]))
        elif tag == "label":
            self._dentro_de_label += 1
            if a.get("for"):
                self.rotulos_para.add(a["for"])
        elif tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button"):
            self.campos.append((self._descrever(tag, a), {**a, "_em_label": self._dentro_de_label > 0}))
        elif tag == "canvas" and not (a.get("aria-label") or a.get("aria-hidden") == "true"):
            self.problemas.append(("desenho (canvas) sem descrição", self._descrever(tag, a), DICAS["canvas"]))
        if tag in ("button", "a"):
            self._pilha.append({"tag": tag, "a": a, "texto": ""})
        if tag in self.VAZIOS and tag != "img":
            return

    def handle_endtag(self, tag):
        if tag == "title":
            self._no_titulo = False
        elif tag == "label":
            self._dentro_de_label -= 1
        elif tag in ("button", "a") and self._pilha and self._pilha[-1]["tag"] == tag:
            item = self._pilha.pop()
            a = item["a"]
            nome = item["texto"].strip() or a.get("aria-label") or a.get("title")
            # Botao preenchido pelo JavaScript (data-*) recebe o texto depois.
            preenchido_depois = any(chave.startswith("data-") for chave in a)
            if not nome and not preenchido_depois:
                tipo = "botão" if tag == "button" else "link"
                self.problemas.append((f"{tipo} sem nome", self._descrever(tag, a), DICAS["botao"]))

    def handle_data(self, dados):
        if self._no_titulo:
            self.titulo += dados
        for item in self._pilha:
            item["texto"] += dados

    @staticmethod
    def _descrever(tag, a):
        detalhe = a.get("class") or a.get("id") or a.get("src") or ""
        return f"<{tag}{' ' + detalhe if detalhe else ''}>"


def _paginas() -> list[Path]:
    return sorted(ESTATICO.glob("*.html")) + sorted(SITE.glob("*.html"))


def testar_acessibilidade(_args) -> bool:
    r = Relatorio(
        "Acessibilidade das telas",
        "Confere, em cada tela, o que um leitor de tela ou quem usa só o teclado precisa encontrar.",
    )
    for pagina in _paginas():
        leitor = _LeitorDeTela()
        leitor.feed(pagina.read_text(encoding="utf-8"))
        nome = pagina.relative_to(RAIZ)
        achados = list(leitor.problemas)
        if not leitor.idioma:
            achados.append(("sem idioma declarado", "<html lang>", DICAS["idioma"]))
        if not leitor.titulo.strip():
            achados.append(("sem título", "<title>", DICAS["titulo"]))
        for descricao, a in leitor.campos:
            rotulado = a.get("aria-label") or a.get("aria-labelledby") or a["_em_label"] or a.get("id") in leitor.rotulos_para
            if not rotulado:
                achados.append(("campo de texto sem rótulo", descricao, DICAS["campo"]))
        if not achados:
            r.ok(f"{nome}: idioma, título, botões, imagens, desenhos e campos com nome")
        for problema, onde, dica in achados:
            r.falha(f"{nome}: {problema} — {onde}", dica)
        if not leitor.viewport:
            r.aviso(f"{nome}: sem <meta name=viewport>", "no celular a tela abre minúscula")
    return r.fechar()


# ---------------------------------------------------------- 3. responsivo

# Que larguras cada tela precisa aguentar sem rolar para o lado.
TELAS = (
    ("autodoc/web/estatico/app.html", (1440, 1024, 768)),
    ("autodoc/web/estatico/instalador.html", (1280, 960, 768)),
    ("autodoc/web/estatico/tetris.html", (1440, 1280, 960)),
    ("site/index.html", (1440, 768, 390)),
)

# Escrito no fim de cada tela: mede depois de o JavaScript montar tudo.
_MEDIDOR = """<script>
setTimeout(() => {
  const d = document.documentElement;
  // A barra de abas so existe no modo demonstracao (some com o programa de
  // verdade); nao e tela de produto, entao fica fora da medida.
  const doProduto = (e) => !e.closest('.ad-abas');
  const nome = (e) => (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : e.tagName.toLowerCase());
  const pequenos = [...document.querySelectorAll('body *')].filter(doProduto).filter((e) => {
    if (!e.childNodes.length || ![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) return false;
    const caixa = e.getBoundingClientRect();
    return caixa.width > 0 && parseFloat(getComputedStyle(e).fontSize) < 10.5;
  }).map(nome);
  const alvos = [...document.querySelectorAll('button, a[href], input, select')].filter(doProduto).filter((e) => {
    const caixa = e.getBoundingClientRect();
    return caixa.width > 0 && caixa.height > 0 && (caixa.width < 24 || caixa.height < 24);
  }).map(nome);
  const lista = (itens) => [...new Set(itens)].slice(0, 4).join(' ');
  document.title = `UX|${d.scrollWidth}|${innerWidth}|${pequenos.length}|${alvos.length}|${lista(pequenos)}|${lista(alvos)}`;
}, 1200);
</script></body>"""


def _achar_chrome() -> str | None:
    candidatos = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for nome in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        achado = shutil.which(nome)
        if achado:
            candidatos.insert(0, achado)
    return next((c for c in candidatos if Path(c).exists()), None)


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _servir(pasta: Path):
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Calado(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", _porta_livre()), functools.partial(Calado, directory=str(pasta)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}/"
    finally:
        servidor.shutdown()
        servidor.server_close()


def testar_responsivo(_args) -> bool:
    r = Relatorio(
        "Telas em vários tamanhos",
        "Abre cada tela num navegador sem janela, em larguras de monitor, notebook, tablet e celular.",
    )
    chrome = _achar_chrome()
    if chrome is None:
        r.pulado("nenhum Chrome ou Chromium encontrado; instale um para rodar este teste")
        return r.fechar()

    with tempfile.TemporaryDirectory() as temporaria:
        copia = Path(temporaria) / "telas"
        # As telas sao servidas sem o backend: elas entram sozinhas em modo
        # demonstracao, e o resultado nao depende de documento nenhum.
        shutil.copytree(ESTATICO, copia / "autodoc" / "web" / "estatico")
        shutil.copytree(SITE, copia / "site")
        for tela, _ in TELAS:
            arquivo = copia / tela
            arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("</body>", _MEDIDOR), encoding="utf-8")

        with _servir(copia) as url:
            for tela, larguras in TELAS:
                for largura in larguras:
                    medida = _medir(chrome, url + tela, largura, Path(temporaria) / f"perfil-{largura}")
                    _julgar(r, tela, largura, medida)
    return r.fechar()


def _medir(chrome: str, url: str, largura: int, perfil: Path) -> tuple | None:
    altura = 844 if largura < 500 else 900
    try:
        saida = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={largura},{altura}",
             "--virtual-time-budget=4000", "--timeout=8000", f"--user-data-dir={perfil}", "--dump-dom", url],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except subprocess.TimeoutExpired:
        return None
    achado = re.search(r"<title>UX\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([^|<]*)\|([^|<]*)</title>", saida)
    if not achado:
        return None
    rolagem, janela, pequenos, alvos, quais_pequenos, quais_alvos = achado.groups()
    return int(rolagem), int(janela), int(pequenos), int(alvos), quais_pequenos, quais_alvos


def _julgar(r: Relatorio, tela: str, largura: int, medida) -> None:
    nome = f"{Path(tela).name} em {largura} px"
    if medida is None:
        r.aviso(f"{nome}: o navegador não terminou de medir", "rode de novo; se repetir, abra a tela à mão")
        return
    rolagem, janela, pequenos, alvos, quais_pequenos, quais_alvos = medida
    if rolagem > janela + 1:
        r.falha(f"{nome}: a tela passa {rolagem - janela} px da janela e rola para o lado",
                "rolar para o lado esconde conteúdo; procure a coluna larga demais")
    else:
        r.ok(f"{nome}: cabe na largura, sem rolagem lateral")
    if pequenos:
        r.aviso(f"{nome}: {pequenos} texto(s) menor(es) que 10,5 px ({quais_pequenos})",
                "letra pequena cansa; vale subir para 11 px ou mais")
    if alvos:
        r.aviso(f"{nome}: {alvos} botão(ões)/link(s) com menos de 24×24 px ({quais_alvos})",
                "alvo pequeno é difícil de acertar com o mouse ou o dedo (WCAG 2.5.8)")


# --------------------------------------------------------------- apoio app

CONTA_DE_LUZ = """CEMIG DISTRIBUICAO S.A.
CONTA DE ENERGIA ELETRICA
Instalacao 3001234567          Classe: Residencial
Mes de referencia: MAR/2026
LEITURA ATUAL      12/03/2026    8.626 kWh
CONSUMO FATURADO                   214 kWh
TOTAL A PAGAR                    R$ 187,43
VENCIMENTO                       12/03/2026
"""

ILEGIVEL = "l  m   ..  R$ ?\n   |||  ~~~   __\n rn  ci   1O   0O\n      .,,.\n"


def _importar_autodoc():
    sys.path.insert(0, str(RAIZ))
    try:
        from autodoc import monitor
        from autodoc.catalogo import Catalogo
        from autodoc.config import Config
        from autodoc.pipeline import Pipeline
        from autodoc.web.servidor import Servidor
    except ImportError as erro:
        raise SystemExit(
            f"\n  Este teste sobe o AutoDoc de verdade e precisa das dependências dele ({erro.name}).\n"
            "  Rode com o Python do venv: venv/bin/python ferramentas/ux.py ...\n"
        ) from erro
    return monitor, Catalogo, Config, Pipeline, Servidor


@contextlib.contextmanager
def _autodoc_temporario():
    """Um AutoDoc inteiro numa pasta temporaria, com o servidor no ar."""
    monitor, Catalogo, Config, Pipeline, Servidor = _importar_autodoc()
    intervalo = monitor.INTERVALO_ESTABILIDADE
    with tempfile.TemporaryDirectory() as temporaria:
        base = Path(temporaria)
        config = Config(pasta_entrada=base / "entrada", pasta_saida=base / "organizados")
        config.preparar_pastas()
        catalogo = Catalogo(config.pasta_saida)
        servidor = Servidor(config, catalogo, Pipeline(config, catalogo), porta=_porta_livre())
        inicio = time.perf_counter()
        url = servidor.iniciar()
        subiu_em = time.perf_counter() - inicio
        try:
            yield config, url, subiu_em
        finally:
            servidor.parar()
            monitor.INTERVALO_ESTABILIDADE = intervalo


def _pedir(url: str, corpo: dict | None = None) -> tuple[dict, float]:
    dados = None if corpo is None else json.dumps(corpo).encode()
    pedido = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    with urllib.request.urlopen(pedido, timeout=10) as resposta:
        conteudo = json.loads(resposta.read())
    return conteudo, time.perf_counter() - inicio


# --------------------------------------------------------------- 4. tempo

# Os limites classicos de Jakob Nielsen para tempo de resposta: ate 0,1 s a
# pessoa sente que a tela reagiu na hora; ate 1 s ela nota a espera mas nao
# perde o fio; acima disso, perde.
INSTANTANEO = 0.1
SEM_PERDER_O_FIO = 1.0


def _julgar_tempo(r: Relatorio, o_que: str, tempos: list[float]) -> None:
    mediana = statistics.median(tempos)
    pior = max(tempos)
    texto = f"{o_que}: mediana {mediana * 1000:.0f} ms, pior {pior * 1000:.0f} ms"
    if pior <= INSTANTANEO:
        r.ok(texto + " — parece instantâneo")
    elif mediana <= SEM_PERDER_O_FIO:
        r.aviso(texto + " — dá para notar a espera", "acima de 100 ms a tela deixa de parecer instantânea")
    else:
        r.falha(texto + " — a pessoa perde o fio", "acima de 1 s precisa de indicador de progresso, ou ficar mais rápido")


def testar_tempo(_args) -> bool:
    r = Relatorio(
        "Tempo de resposta",
        "Sobe o AutoDoc numa pasta temporária e cronometra o que a tela pede ao programa (limites de Nielsen).",
    )
    with _autodoc_temporario() as (config, url, subiu_em):
        (config.pasta_entrada / "conta_luz.txt").write_text(CONTA_DE_LUZ, encoding="utf-8")
        _esperar_documento(url, "conta_luz.txt", 15)

        if subiu_em <= 2:
            r.ok(f"abrir o AutoDoc (servidor e catálogo prontos): {subiu_em:.2f} s")
        else:
            r.aviso(f"abrir o AutoDoc: {subiu_em:.2f} s", "acima de 2 s a janela abre vazia por um tempo")

        for o_que, rota in (
            ("estado da tela ao abrir", "api/estado"),
            ("lista de documentos", "api/documentos"),
            ("busca por \"energia\"", "api/documentos?q=energia"),
            ("filtro por categoria", "api/documentos?cat=Conta%20de%20energia"),
        ):
            _julgar_tempo(r, o_que, [_pedir(url + rota)[1] for _ in range(15)])

    _testar_tempo_do_tetris(r)
    return r.fechar()


def _testar_tempo_do_tetris(r: Relatorio) -> None:
    from autodoc.gestos.servidor_tetris import Partida, ServidorTetris
    from autodoc.gestos.tetris import Jogo

    servidor = ServidorTetris(Partida(Jogo(semente=1)), porta=_porta_livre())
    url = servidor.iniciar()
    try:
        tempos = [_pedir(url + "api/tecla", {"tecla": tecla})[1] for tecla in ["ArrowLeft", "ArrowRight"] * 8]
        _julgar_tempo(r, "Tetris: tecla até o jogo responder", tempos)
    finally:
        servidor.parar()


def _esperar_documento(url: str, arquivo: str, limite: float) -> tuple[dict | None, float]:
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < limite:
        linhas = _pedir(url + "api/documentos")[0]["todos"]
        achado = next((linha for linha in linhas if linha["arquivo"] == arquivo), None)
        if achado:
            return achado, time.perf_counter() - inicio
        time.sleep(0.05)
    return None, limite


# -------------------------------------------------------------- 5. tarefa


def testar_tarefa(_args) -> bool:
    r = Relatorio(
        "Tarefas de ponta a ponta",
        "Faz, sem ajuda, o que uma pessoa faria no AutoDoc e no Tetris, e mede se cada passo deu certo.",
    )
    print(_pintar("  Tarefa 1 — \"guardei minha conta de luz; quero achá-la depois\"", "1"))
    with _autodoc_temporario() as (config, url, _):
        ouvidos: list[dict] = []
        ouvinte = threading.Thread(target=_ouvir_eventos, args=(url, ouvidos), daemon=True)
        ouvinte.start()
        time.sleep(0.3)

        largado = time.perf_counter()
        (config.pasta_entrada / "conta_luz.txt").write_text(CONTA_DE_LUZ, encoding="utf-8")
        linha, _ = _esperar_documento(url, "conta_luz.txt", 15)
        if linha is None:
            r.falha("o arquivo largado na pasta nunca apareceu", "confira o monitoramento (watchdog)")
            return r.fechar()

        apareceu = _esperar(lambda: any(e.get("arquivo") == "conta_luz.txt" for e in ouvidos), 5)
        demora = time.perf_counter() - largado
        if apareceu and demora <= 3:
            r.ok(f"apareceu na tela sozinho, sem recarregar: {demora:.1f} s depois de largar o arquivo")
        elif apareceu:
            r.aviso(f"apareceu na tela sozinho, mas só {demora:.1f} s depois", "acima de 3 s a pessoa acha que não funcionou")
        else:
            r.falha("o documento entrou no catálogo mas a tela não foi avisada", "confira o /api/eventos (SSE)")

        if linha["tipo"] == "Conta de energia":
            r.ok(f"classificado certo: {linha['tipo']}, confiança {linha['confianca']}")
        else:
            r.falha(f"classificado como \"{linha['tipo']}\", e era conta de energia", "revise as regras do classificador")

        if linha["data"] and linha["data"] != "—":
            r.ok(f"data encontrada sozinha: {linha['data']} (vencimento)")
        else:
            r.falha("sem data", "sem data o documento vai para o mês errado")

        if linha.get("regra") or linha.get("chaves"):
            r.ok("a tela explica a decisão (regra e palavras-chave)")
        else:
            r.aviso("a tela não diz por que classificou assim", "explicação dá confiança para corrigir")

        achados = _pedir(url + "api/documentos?q=energia")[0]["linhas"]
        # O documento diz ELETRICA, sem acento; a pessoa digita "elétrica".
        com_acento = _pedir(url + "api/documentos?q=" + urllib.parse.quote("elétrica"))[0]["linhas"]
        if achados and com_acento:
            r.ok("achado pela busca, mesmo digitando \"elétrica\" com acento num documento sem acento")
        elif achados:
            r.falha("a busca só acha se a pessoa digitar sem acento", "quem procura escreve do jeito certo, com acento")
        else:
            r.falha("a busca não achou o documento", "a pessoa vai procurar pela palavra que lembra")

        print(_pintar("\n  Tarefa 2 — \"o programa não entendeu um documento; quero corrigir\"", "1"))
        (config.pasta_entrada / "scan_borrado.txt").write_text(ILEGIVEL, encoding="utf-8")
        borrado, _ = _esperar_documento(url, "scan_borrado.txt", 15)
        if borrado and borrado["categoria"] not in ("conta_luz", "nota_fiscal", "contrato", "comprovante", "boleto"):
            r.ok(f"documento ilegível não foi chutado numa categoria: ficou em \"{borrado['tipo']}\"")
        elif borrado:
            r.falha(f"documento ilegível foi chutado em \"{borrado['tipo']}\"", "melhor pedir revisão que errar calado")
        if borrado:
            resposta, gasto = _pedir(url + "api/reclassificar", {"id": borrado["id"], "categoria": "comprovante"})
            if resposta.get("ok") and resposta["linha"]["categoria"] == "comprovante":
                r.ok(f"a correção à mão funcionou em {gasto * 1000:.0f} ms e o arquivo mudou de pasta "
                     f"({resposta['linha']['destino']})")
            else:
                r.falha(f"a correção à mão não funcionou: {resposta.get('erro')}")

    print(_pintar("\n  Tarefa 3 — \"quero jogar Tetris pelo teclado\"", "1"))
    _tarefa_do_tetris(r)
    return r.fechar()


def _ouvir_eventos(url: str, ouvidos: list[dict]) -> None:
    with contextlib.suppress(OSError):
        with urllib.request.urlopen(url + "api/eventos", timeout=30) as fluxo:
            for linha in fluxo:
                if linha.startswith(b"data: "):
                    ouvidos.append(json.loads(linha[6:]))


def _esperar(condicao, limite: float) -> bool:
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < limite:
        if condicao():
            return True
        time.sleep(0.05)
    return False


def _tarefa_do_tetris(r: Relatorio) -> None:
    from autodoc.gestos.servidor_tetris import Partida, ServidorTetris
    from autodoc.gestos.tetris import Jogo

    servidor = ServidorTetris(Partida(Jogo(semente=1)), porta=_porta_livre())
    url = servidor.iniciar()

    def estado():
        return _pedir(url + "api/estado")[0]

    def tecla(nome):
        return _pedir(url + "api/tecla", {"tecla": nome})[0]["aceita"]

    try:
        antes = estado()
        coluna = min(c for _, c in antes["peca"]["celulas"])
        tecla("ArrowLeft")
        depois = estado()
        if min(c for _, c in depois["peca"]["celulas"]) == coluna - 1:
            r.ok("seta para a esquerda move a peça uma coluna")
        else:
            r.falha("a seta para a esquerda não moveu a peça")

        forma = sorted(map(tuple, depois["peca"]["celulas"]))
        tecla("ArrowUp")
        girou = sorted(map(tuple, estado()["peca"]["celulas"])) != forma or depois["peca"]["tipo"] == "O"
        (r.ok if girou else r.falha)("seta para cima gira a peça" if girou else "a seta para cima não girou a peça")

        tecla(" ")
        jogado = estado()
        if jogado["pontos"] > 0 and any(set(linha) != {"."} for linha in jogado["tabuleiro"]):
            r.ok(f"espaço despenca a peça e já conta pontos ({jogado['pontos']})")
        else:
            r.falha("o espaço não despencou a peça")

        tecla("p")
        pausado = estado()["situacao"]
        tecla("p")
        voltou = estado()["situacao"]
        if (pausado, voltou) == ("pausado", "jogando"):
            r.ok("P pausa e P de novo continua")
        else:
            r.falha(f"pausa não funcionou como esperado ({pausado} → {voltou})")

        tecla("r")
        if estado()["pontos"] == 0:
            r.ok("R recomeça do zero")
        else:
            r.falha("R não recomeçou a partida")

        if not tecla("F5"):
            r.ok("tecla sem função é ignorada, sem quebrar o jogo")
        else:
            r.aviso("uma tecla sem função foi aceita")
    finally:
        servidor.parar()


# ----------------------------------------------------------------- entrada

COMANDOS = {
    "contraste": (testar_contraste, "legibilidade: contraste das cores do texto contra o fundo (WCAG)"),
    "acessibilidade": (testar_acessibilidade, "botões, imagens e campos com nome para leitor de tela e teclado"),
    "responsivo": (testar_responsivo, "telas sem rolagem lateral em monitor, notebook, tablet e celular"),
    "tempo": (testar_tempo, "tempo de resposta do app e do Tetris contra os limites de Nielsen"),
    "tarefa": (testar_tarefa, "tarefas reais de ponta a ponta: guardar, achar, corrigir e jogar"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ferramentas/ux.py",
        description="Testes de usabilidade automáticos do AutoDoc.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {nome:<15} {descricao}" for nome, (_, descricao) in COMANDOS.items())
        + "\n  todos           os cinco, um atrás do outro",
    )
    parser.add_argument("comando", choices=[*COMANDOS, "todos"], help="qual teste rodar")
    args = parser.parse_args(argv)

    escolhidos = list(COMANDOS) if args.comando == "todos" else [args.comando]
    resultados = {nome: COMANDOS[nome][0](args) for nome in escolhidos}

    if len(resultados) > 1:
        print(_pintar("\n■ Resumo", "1"))
        for nome, passou in resultados.items():
            marca = _pintar("✔", "32") if passou else _pintar("✘", "31")
            print(f"  {marca} {nome:<15} {COMANDOS[nome][1]}")
    return 0 if all(resultados.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
