"""Monitoramento da pasta de entrada com watchdog.

Ao detectar um arquivo novo (ou movido para dentro da pasta), aguarda a copia
terminar e entrega o arquivo ao pipeline.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .pipeline import Pipeline

logger = logging.getLogger(__name__)

# Intervalo entre checagens de tamanho para saber se a copia terminou.
INTERVALO_ESTABILIDADE = 0.5
TENTATIVAS_ESTABILIDADE = 20


def aguardar_arquivo_pronto(caminho: Path) -> bool:
    """Espera o arquivo parar de crescer (copia/download em andamento)."""
    anterior = -1
    for _ in range(TENTATIVAS_ESTABILIDADE):
        if not caminho.exists():
            return False
        atual = caminho.stat().st_size
        if atual == anterior and atual > 0:
            return True
        anterior = atual
        time.sleep(INTERVALO_ESTABILIDADE)
    return caminho.exists()


def processar_pendentes(pipeline: Pipeline) -> int:
    """Processa o que ja estava na pasta antes do monitor subir."""
    total = 0
    for caminho in sorted(pipeline.config.pasta_entrada.iterdir()):
        if caminho.is_file() and not caminho.name.startswith("."):
            if pipeline.processar(caminho).sucesso:
                total += 1
    return total


def monitorar(pipeline: Pipeline) -> None:
    """Bloqueia observando a pasta de entrada ate Ctrl+C."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise RuntimeError(
            "watchdog nao instalado (pip install -r requirements.txt)"
        ) from erro

    class Manipulador(FileSystemEventHandler):
        def on_created(self, evento) -> None:
            self._tratar(evento)

        def on_moved(self, evento) -> None:
            self._tratar(evento, destino=True)

        def _tratar(self, evento, destino: bool = False) -> None:
            if evento.is_directory:
                return
            caminho = Path(evento.dest_path if destino else evento.src_path)
            if caminho.name.startswith("."):
                return
            if aguardar_arquivo_pronto(caminho):
                pipeline.processar(caminho)

    observador = Observer()
    observador.schedule(Manipulador(), str(pipeline.config.pasta_entrada), recursive=False)
    observador.start()
    logger.info("monitorando %s (Ctrl+C para sair)", pipeline.config.pasta_entrada)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("encerrando monitoramento")
    finally:
        observador.stop()
        observador.join()
