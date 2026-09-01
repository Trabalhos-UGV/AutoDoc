"""Ponto de entrada do AutoDoc.

Uso:
    python main.py app                # abre a janela do AutoDoc
    python main.py monitorar          # observa a pasta pelo terminal
    python main.py buscar "luz marco" # busca nos documentos indexados
    python main.py listar             # ultimos documentos processados
"""

from __future__ import annotations

import argparse
import logging
import sys

from autodoc import __version__
from autodoc.catalogo import Catalogo
from autodoc.config import Config
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


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args = montar_parser().parse_args(argv)
    config = Config.carregar()
    config.preparar_pastas()
    catalogo = Catalogo(config.pasta_saida)

    comando = args.comando or "app"

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
