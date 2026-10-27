"""O aplicativo abrindo o Tetris, e instalando os gestos quando faltam.

O AutoDoc aberto pelo icone nao tem terminal. Tudo que antes era comando —
`pip install -r requirements-gestos.txt`, `python main.py gestos --tetris` —
passa a ser um botao na lateral, e este modulo e o que o servidor do app chama.

**O Tetris roda em outro processo.** A camera e a janela do Tetris precisam da
thread principal, e no aplicativo ela ja e da janela do AutoDoc; no macOS nao
da para ter as duas no mesmo processo. Processo separado tambem protege: se a
camera travar, o organizador de documentos continua de pe.

**A instalacao roda em segundo plano** e deixa a ultima linha do pip como
recado, para a tela mostrar que esta andando — sao uns 150 MB, e uma tela
parada por um minuto parece travada.

Nada aqui importa OpenCV ou MediaPipe: so pergunta se existem.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import threading
from pathlib import Path

from autodoc.gestos.camera import pasta_cache

RAIZ = Path(__file__).resolve().parent.parent.parent
REQUISITOS = RAIZ / "requirements-gestos.txt"

# Sem estes dois o Tetris abre so pelo teclado.
DEPENDENCIAS = ("cv2", "mediapipe")


def gestos_instalados() -> bool:
    # O pip acabou de instalar? O importlib guarda o que ja procurou, e sem
    # limpar ele continuaria dizendo que nao existe.
    importlib.invalidate_caches()
    return all(importlib.util.find_spec(nome) is not None for nome in DEPENDENCIAS)


def resumir_linha_do_pip(linha: str) -> str | None:
    """A linha do pip que vale mostrar, curta; None para as que nao valem."""
    linha = linha.strip()
    if not linha or linha.startswith(("━", "[notice]")) or set(linha) <= set("━╸ ."):
        return None
    for prefixo, texto in (
        ("Collecting ", "baixando "),
        ("Downloading ", "baixando "),
        ("Installing collected packages", "instalando os pacotes"),
        ("Successfully installed", "pronto"),
        ("Requirement already satisfied: ", "já instalado: "),
    ):
        if linha.startswith(prefixo):
            resto = linha[len(prefixo):].split(" ", 1)[0] if prefixo.endswith(" ") else ""
            return (texto + resto)[:70]
    return None


class Lancador:
    """Estado do Tetris aberto pelo app e da instalacao dos gestos."""

    def __init__(self, python: str = sys.executable, registro: Path | None = None) -> None:
        self.python = python
        self.registro = registro or pasta_cache() / "tetris.log"
        self._processo: subprocess.Popen | None = None
        self._instalando = False
        self._mensagem: str | None = None
        self._erro: str | None = None
        self._trava = threading.Lock()

    def estado(self) -> dict:
        with self._trava:
            self._verificar_fim()
            return {
                "gestos": gestos_instalados(),
                "aberto": self._processo is not None,
                "instalando": self._instalando,
                "mensagem": self._mensagem,
                "erro": self._erro,
            }

    def abrir(self, sem_camera: bool = False) -> dict:
        """Abre o Tetris, a nao ser que ja esteja aberto."""
        with self._trava:
            self._verificar_fim()
            if self._processo is None:
                if not sem_camera and not gestos_instalados():
                    self._erro = "o controle por gestos ainda não está instalado"
                else:
                    self._iniciar(sem_camera)
        return self.estado()

    def instalar(self) -> dict:
        with self._trava:
            if not self._instalando and not gestos_instalados():
                self._instalando = True
                self._erro = None
                self._mensagem = "começando"
                threading.Thread(target=self._instalar, daemon=True).start()
        return self.estado()

    # ------------------------------------------------------------ por dentro

    def _iniciar(self, sem_camera: bool) -> None:
        self.registro.parent.mkdir(parents=True, exist_ok=True)
        comando = [self.python, str(RAIZ / "main.py"), "gestos", "--tetris"]
        if sem_camera:
            comando.append("--sem-camera")
        # A saida vai para um arquivo, e nao para um cano: um cano que ninguem
        # le enche e trava o processo filho.
        with open(self.registro, "w", encoding="utf-8") as saida:
            self._processo = subprocess.Popen(comando, cwd=RAIZ, stdout=saida, stderr=subprocess.STDOUT)
        self._erro = None

    def _verificar_fim(self) -> None:
        """Se o Tetris fechou; se fechou com erro, guarda a ultima linha dele."""
        if self._processo is None or self._processo.poll() is None:
            return
        if self._processo.returncode != 0:
            linhas = [l for l in self.registro.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
            ultima = linhas[-1] if linhas else f"código {self._processo.returncode}"
            self._erro = ultima.removeprefix("gestos indisponiveis: ")[:200]
        self._processo = None

    def _instalar(self) -> None:
        processo = subprocess.Popen(
            [self.python, "-m", "pip", "install", "-r", str(REQUISITOS)],
            cwd=RAIZ,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ultimas: list[str] = []
        for linha in processo.stdout:
            ultimas = (ultimas + [linha.strip()])[-5:]
            resumo = resumir_linha_do_pip(linha)
            if resumo:
                with self._trava:
                    self._mensagem = resumo
        processo.wait()
        with self._trava:
            self._instalando = False
            if processo.returncode == 0:
                self._mensagem = "controle por gestos instalado"
            else:
                self._mensagem = None
                self._erro = "a instalação falhou: " + (next((l for l in reversed(ultimas) if l), "sem detalhes"))[:160]
