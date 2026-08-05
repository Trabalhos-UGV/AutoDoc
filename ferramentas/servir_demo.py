"""Sobe um servidor local com as tres telas do AutoDoc em modo demonstracao.

Serve a raiz do repositorio, e nao cada pasta isolada, porque a barra de
navegacao do prototipo liga a landing (em site/) as telas do app (em
autodoc/web/estatico/) — sao pastas irmas, e os links relativos entre elas so
resolvem a partir da raiz.

    python3 ferramentas/servir_demo.py [porta]

Sem backend no ar, as tres telas usam os dados de demonstracao. Ctrl+C encerra.
"""

from __future__ import annotations

import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PORTA_PADRAO = 8000

TELAS = [
    ("Landing / download", "site/index.html"),
    ("Instalacao", "autodoc/web/estatico/instalador.html"),
    ("Gerenciamento", "autodoc/web/estatico/app.html"),
]


class Manipulador(SimpleHTTPRequestHandler):
    """Serve a raiz do projeto sem guardar nada em cache."""

    def end_headers(self) -> None:
        # Durante o desenvolvimento, cache so atrapalha: editar o CSS e
        # recarregar tem que mostrar a mudanca.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, formato, *args) -> None:
        # O log padrao polui o terminal com uma linha por arquivo servido.
        pass


def main() -> None:
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORTA_PADRAO
    servidor = ThreadingHTTPServer(
        ("127.0.0.1", porta), partial(Manipulador, directory=str(RAIZ))
    )

    base = f"http://127.0.0.1:{porta}"
    print(f"AutoDoc — demonstracao servindo {RAIZ}\n")
    for nome, caminho in TELAS:
        print(f"  {nome:22} {base}/{caminho}")
    print("\nCtrl+C para encerrar.")

    webbrowser.open(f"{base}/{TELAS[0][1]}")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")
        servidor.server_close()


if __name__ == "__main__":
    main()
