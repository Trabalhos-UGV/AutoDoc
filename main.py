"""Ponto de entrada do AutoDoc.

Uso:
    python main.py app                # abre a janela do AutoDoc
    python main.py monitorar          # observa a pasta pelo terminal
    python main.py buscar "luz marco" # busca nos documentos indexados
    python main.py listar             # ultimos documentos processados
    python main.py gestos             # controla o mouse com a mao, pela webcam
    python main.py gestos --quadro    # quadro de desenho para treinar os gestos
    python main.py gestos --tetris    # Tetris comandado pela mao
"""

from __future__ import annotations

import argparse
import logging
import sys

from autodoc import __version__
from autodoc.catalogo import Catalogo
from autodoc.config import Config
from autodoc.gestos import GestosIndisponiveis
from autodoc.gestos import camera as camera_gestos
from autodoc.gestos import camera_tetris, servidor_tetris
from autodoc.gestos import quadro as quadro_gestos
from autodoc.monitor import monitorar, processar_pendentes
from autodoc.pipeline import Pipeline
from autodoc.web import janela
from autodoc.web.servidor import PORTA_PADRAO, Servidor


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autodoc", description="Organizador automatico de documentos")
    parser.add_argument("--versao", action="version", version=f"AutoDoc {__version__}")
    subcomandos = parser.add_subparsers(dest="comando")

    aplicativo = subcomandos.add_parser("app", help="abre a janela do AutoDoc")
    aplicativo.add_argument("--porta", type=int, default=PORTA_PADRAO)

    subcomandos.add_parser("monitorar", help="observa a pasta pelo terminal")

    buscar = subcomandos.add_parser("buscar", help="busca por conteudo, categoria ou data")
    buscar.add_argument("termo")
    buscar.add_argument("--limite", type=int, default=20)

    listar = subcomandos.add_parser("listar", help="ultimos documentos processados")
    listar.add_argument("--limite", type=int, default=20)

    gestos = subcomandos.add_parser("gestos", help="controla o mouse com gestos da mao, pela webcam")
    gestos.add_argument("--camera", type=int, default=0, help="indice da webcam (padrao 0)")
    gestos.add_argument("--canhoto", action="store_true", help="a mao esquerda move o cursor")
    telas = gestos.add_mutually_exclusive_group()
    telas.add_argument("--quadro", action="store_true", help="abre o quadro de desenho em vez de mexer no mouse")
    telas.add_argument("--tetris", action="store_true", help="joga Tetris com a mao")
    gestos.add_argument("--sem-camera", action="store_true", help="com --tetris: joga so pelo teclado")

    return parser


def imprimir(linhas) -> None:
    if not linhas:
        print("nenhum documento encontrado")
        return
    for linha in linhas:
        data = linha["data_documento"] or "sem data"
        print(f'[{linha["id"]:>4}] {data}  {linha["categoria"]:<18} {linha["arquivo"]}')
        print(f'       {linha["caminho"]}')


def abrir_aplicativo(config: Config, catalogo: Catalogo, porta: int) -> int:
    """Sobe o servidor local e abre a janela do AutoDoc.

    O servidor fica em threads e a janela toma a thread principal, porque no
    macOS o sistema so deixa criar janela na principal. Quando a janela fecha,
    o servidor e o monitoramento vao junto — nao faz sentido continuar
    vigiando a pasta com o programa fechado.
    """
    servidor = Servidor(config, catalogo, Pipeline(config, catalogo), porta)
    url = servidor.iniciar()

    print(f"AutoDoc v{__version__} — monitorando {config.pasta_entrada}")
    try:
        janela.abrir(url, titulo="AutoDoc")
    finally:
        servidor.parar()
    return 0


def controlar_por_gestos(camera: int, destro: bool, modo: str = "mouse") -> int:
    executores = {
        "mouse": camera_gestos.executar,
        "quadro": quadro_gestos.executar_quadro,
        "tetris": camera_tetris.jogar_com_camera,
        "tetris sem camera": lambda _camera, _destro: servidor_tetris.jogar_pelo_teclado(),
    }
    try:
        return executores[modo](camera, destro)
    except GestosIndisponiveis as erro:
        print(f"gestos indisponiveis: {erro}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = montar_parser()
    args = parser.parse_args(argv)

    if args.comando == "gestos":
        if args.sem_camera and not args.tetris:
            parser.error("--sem-camera so vale com --tetris")
        # Nao toca em pasta nem catalogo: o controle por gestos nao tem nada a
        # ver com os documentos, e nao deve criar pasta so por ter sido aberto.
        if args.tetris:
            modo = "tetris sem camera" if args.sem_camera else "tetris"
        else:
            modo = "quadro" if args.quadro else "mouse"
        return controlar_por_gestos(args.camera, destro=not args.canhoto, modo=modo)

    config = Config.carregar()
    config.preparar_pastas()
    catalogo = Catalogo(config.pasta_saida)

    comando = args.comando or "app"

    if comando != "app":
        # A pasta organizada e a verdade, e nao so quando a janela abre: quem
        # consulta pelo terminal tem que ver o mesmo que a tela veria. Sem isto,
        # apagar o catalogo deixava `listar` e `buscar` mudos ate alguem abrir o
        # aplicativo — e a promessa de que o catalogo se remonta sozinho valia
        # pela metade. No `app` quem reconcilia e o servidor, ao subir.
        catalogo.reconciliar(Pipeline(config, catalogo).analisar)

    if comando == "app":
        # `porta` só existe quando o subcomando foi escrito. Sem isto, rodar
        # `python main.py` sozinho — que a ajuda diz ser o mesmo que `app` —
        # quebrava com AttributeError antes de abrir coisa alguma.
        return abrir_aplicativo(config, catalogo, getattr(args, "porta", PORTA_PADRAO))

    if comando == "buscar":
        imprimir(catalogo.buscar(args.termo, args.limite))
        return 0

    if comando == "listar":
        imprimir(catalogo.listar(args.limite))
        return 0

    pipeline = Pipeline(config, catalogo)
    pendentes = processar_pendentes(pipeline)
    if pendentes:
        print(f"{pendentes} documento(s) pendente(s) processado(s)")
    monitorar(pipeline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
