"""Monitoramento da pasta de entrada com watchdog.

Ao detectar um arquivo novo (ou movido para dentro da pasta), aguarda a copia
terminar e entrega o arquivo ao pipeline. Uma varredura periodica da pasta
pega o que o watchdog deixou para depois: copia que nao terminou a tempo,
arquivo travado por outro programa, evento que o sistema nao entregou.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .pipeline import Pipeline

logger = logging.getLogger(__name__)

# Intervalo entre checagens de tamanho para saber se a copia terminou.
INTERVALO_ESTABILIDADE = 0.5
TENTATIVAS_ESTABILIDADE = 20

# De quanto em quanto tempo a pasta e varrida de novo, em segundos.
INTERVALO_VARREDURA = 30

# Sufixos de arquivo pela metade. Navegador e programa de escritorio escrevem
# num arquivo temporario e so depois renomeiam para o nome final — processar o
# temporario arquivaria um pedaco do documento e ainda deixaria o de verdade
# parecendo repetido.
SUFIXOS_TEMPORARIOS = (".crdownload", ".part", ".partial", ".download", ".tmp", ".swp")

# Prefixos do mesmo problema: o Office abre "~$relatorio.docx" ao lado do
# arquivo, e o macOS espalha "._" em pen drive.
PREFIXOS_TEMPORARIOS = ("~$", "._")

# Arquivos que o proprio sistema cria dentro das pastas (o Windows os esconde,
# mas a pasta sincronizada ou o pen drive os traz a vista).
NOMES_DO_SISTEMA = {"desktop.ini", "thumbs.db"}


def deve_ignorar(caminho: Path) -> bool:
    """Diz se o arquivo nao e um documento de ninguem.

    Arquivo oculto, temporario de download ou de programa de escritorio. Sem
    isto o `.DS_Store` do macOS entraria na fila a cada abertura de pasta.
    """
    nome = caminho.name
    return (
        nome.lower() in NOMES_DO_SISTEMA
        or nome.startswith(".")
        or nome.startswith(PREFIXOS_TEMPORARIOS)
        or caminho.suffix.lower() in SUFIXOS_TEMPORARIOS
    )


def _assinatura(caminho: Path) -> tuple[int, int]:
    """Tamanho e data de modificacao: os dois param quando a copia termina."""
    estatistica = caminho.stat()
    return estatistica.st_size, estatistica.st_mtime_ns


def _abre_para_leitura(caminho: Path) -> bool:
    """No Windows, quem ainda esta escrevendo trava o arquivo para os outros."""
    try:
        with caminho.open("rb"):
            return True
    except OSError:
        return False


def aguardar_arquivo_pronto(caminho: Path) -> bool:
    """Espera a copia ou o download terminar.

    Pronto e: tamanho **e** data de modificacao iguais em duas olhadas, e o
    arquivo abrindo para leitura. So o tamanho nao bastava — uma copia que
    sobrescreve no lugar mantem o tamanho e muda a data.

    Se o tempo esgotar com o arquivo ainda mudando, a resposta e "nao": antes
    ele era processado mesmo assim, e um PDF pela metade ia parar no arquivo
    como documento ilegivel. Agora ele fica na entrada e a varredura periodica
    tenta de novo.
    """
    anterior = None
    for _ in range(TENTATIVAS_ESTABILIDADE):
        try:
            atual = _assinatura(caminho)
        except OSError:  # sumiu no meio da espera
            return False
        if atual == anterior and atual[0] > 0 and _abre_para_leitura(caminho):
            return True
        anterior = atual
        time.sleep(INTERVALO_ESTABILIDADE)

    # Zero byte e parado do comeco ao fim e um arquivo vazio de verdade, e nao
    # uma copia que ainda nao comecou: processar e melhor do que ignora-lo.
    try:
        return anterior is not None and anterior[0] == 0 and _assinatura(caminho) == anterior
    except OSError:
        return False


def _avisar(ao_processar, resultado) -> None:
    """Um erro no callback nao pode derrubar quem vigia a pasta."""
    if not (resultado.sucesso and ao_processar):
        return
    try:
        ao_processar(resultado)
    except Exception:
        logger.exception("falha ao notificar documento novo")


def arquivos_da_entrada(pasta: Path, saida: Path) -> list[Path]:
    """Os documentos da pasta vigiada, subpastas inclusive.

    Arrastar uma pasta inteira de contas para a entrada e o jeito natural de
    usar; antes as subpastas eram ignoradas e os arquivos dentro delas nunca
    saiam dali. Pasta oculta fica de fora, e a pasta organizada tambem — se
    alguem a configurou dentro da entrada, ela se reprocessaria sem fim.
    """
    achados = []
    for caminho in sorted(pasta.rglob("*")):
        relativo = caminho.relative_to(pasta)
        if any(parte.startswith(".") for parte in relativo.parts[:-1]):
            continue
        if not caminho.is_file() or deve_ignorar(caminho):
            continue
        if caminho == saida or saida in caminho.parents:
            continue
        achados.append(caminho)
    return achados


def processar_pendentes(pipeline: Pipeline, ao_processar=None) -> int:
    """Processa o que ja estava na pasta antes do monitor subir.

    Cada arquivo e tratado por conta propria: um documento problematico nao
    pode impedir o AutoDoc de abrir, que e o que acontecia quando a excecao
    subia daqui — o programa inteiro deixava de subir por causa de um arquivo.
    """
    pasta = pipeline.config.pasta_entrada
    if not pasta.is_dir():
        logger.warning("pasta monitorada nao existe: %s", pasta)
        return 0

    total = 0
    for caminho in arquivos_da_entrada(pasta, pipeline.config.pasta_saida):
        # Um arquivo ainda sendo copiado quando o programa abre tem que ser
        # esperado aqui tambem, e nao so no caminho do watchdog.
        if not aguardar_arquivo_pronto(caminho):
            continue
        try:
            resultado = pipeline.processar(caminho)
        except Exception:
            logger.exception("falha ao processar %s", caminho.name)
            continue
        if resultado.sucesso:
            total += 1
        _avisar(ao_processar, resultado)
    return total


class _Manipulador:
    """Traduz um evento da pasta em uma passada do pipeline.

    Nao herda de `FileSystemEventHandler` de proposito. O watchdog so precisa de
    um objeto com `dispatch()` — e uma classe comum, no nivel do modulo, pode
    ser construida e exercitada num teste com eventos falsos, sem thread, sem
    disco e sem esperar o sistema de arquivos avisar. Declarada dentro de
    `criar_observador`, ela era inalcancavel de fora.

    De quebra, o watchdog continua sendo dependencia opcional: nao ha import
    dele aqui em cima.
    """

    # Os unicos eventos que interessam. Alterar e apagar arquivo ja arquivado
    # nao passam por aqui; quem cuida disso e a reconciliacao do catalogo.
    EVENTOS = {"created", "moved"}

    def __init__(self, pipeline: Pipeline, ao_processar=None) -> None:
        self.pipeline = pipeline
        self.ao_processar = ao_processar

    def dispatch(self, evento) -> None:
        """Ponto de entrada que o watchdog chama."""
        if evento.event_type not in self.EVENTOS:
            return
        self._tratar(evento, destino=evento.event_type == "moved")

    def on_created(self, evento) -> None:
        self._tratar(evento)

    def on_moved(self, evento) -> None:
        self._tratar(evento, destino=True)

    def _tratar(self, evento, destino: bool = False) -> None:
        if evento.is_directory:
            return
        # Num evento de movimento o arquivo esta no destino; usar o `src_path`
        # apontaria para de onde ele saiu, que ja nao existe mais.
        caminho = Path(evento.dest_path if destino else evento.src_path)
        if deve_ignorar(caminho):
            return
        saida = self.pipeline.config.pasta_saida
        if saida in caminho.parents:
            return
        if not aguardar_arquivo_pronto(caminho):
            return

        try:
            resultado = self.pipeline.processar(caminho)
        except Exception:
            # O observador precisa sobreviver ao arquivo que o derrubaria:
            # perder um documento e ruim, parar de vigiar a pasta e pior.
            logger.exception("falha ao processar %s", caminho.name)
            return

        _avisar(self.ao_processar, resultado)


class Vigia:
    """O observador do watchdog mais a varredura periodica, parados juntos.

    O watchdog sozinho perde arquivo: o que nao ficou pronto a tempo, o que
    nao conseguiu ser movido (travado no Windows) e o evento que o sistema nao
    entregou (pasta de rede, pen drive) ficavam na entrada ate a proxima
    abertura do programa — que podia ser dias depois.
    """

    def __init__(self, observador, pipeline: Pipeline, ao_processar=None) -> None:
        self.observador = observador
        self.pipeline = pipeline
        self.ao_processar = ao_processar
        self._parar = threading.Event()
        self._varredura = threading.Thread(target=self._varrer, daemon=True)

    def start(self) -> None:
        self.observador.start()
        self._varredura.start()

    def _varrer(self) -> None:
        while not self._parar.wait(INTERVALO_VARREDURA):
            try:
                processar_pendentes(self.pipeline, self.ao_processar)
            except Exception:
                logger.exception("falha na varredura da pasta monitorada")

    def stop(self) -> None:
        self._parar.set()
        self.observador.stop()

    def join(self) -> None:
        self.observador.join()
        if self._varredura.is_alive():
            self._varredura.join()


def criar_observador(pipeline: Pipeline, ao_processar=None) -> Vigia:
    """Monta e inicia o observador da pasta de entrada, com a varredura.

    `ao_processar` recebe cada Resultado bem-sucedido — e por onde o servidor
    web fica sabendo que ha documento novo para empurrar para a tela. Devolve o
    observador ja rodando; quem chamou decide se bloqueia ou nao, porque o CLI
    quer bloquear e o servidor nao.
    """
    try:
        from watchdog.observers import Observer
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise RuntimeError(
            "watchdog nao instalado (pip install -r requirements.txt)"
        ) from erro

    observador = Observer()
    observador.schedule(
        _Manipulador(pipeline, ao_processar),
        str(pipeline.config.pasta_entrada),
        recursive=True,
    )
    vigia = Vigia(observador, pipeline, ao_processar)
    vigia.start()
    return vigia


def monitorar(pipeline: Pipeline) -> None:
    """Bloqueia observando a pasta de entrada ate Ctrl+C."""
    observador = criar_observador(pipeline)
    logger.info("monitorando %s (Ctrl+C para sair)", pipeline.config.pasta_entrada)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("encerrando monitoramento")
    finally:
        observador.stop()
        observador.join()
