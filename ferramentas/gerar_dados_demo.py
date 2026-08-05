"""Gera autodoc/web/estatico/js/dados-demo.js a partir do prototipo original.

O prototipo das 17 telas foi construido por um script `_build.py` que carrega
os dados mockados (6 documentos, 6 categorias, 6 etapas do instalador) em
constantes Python. Em vez de transcrever tudo a mao para JavaScript — que e
como se erra um acento ou um numero —, este script importa aquele modulo e
serializa as mesmas estruturas.

O `_build.py` nao faz parte deste repositorio: ele vive na pasta de saida da
sessao que gerou os frames. Passe o caminho dela como argumento.

    python3 ferramentas/gerar_dados_demo.py /caminho/para/outputs

Se a pasta original nao existir mais, nao tem problema: o dados-demo.js ja
esta versionado e so precisa ser regerado se o prototipo mudar.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "autodoc" / "web" / "estatico" / "js" / "dados-demo.js"

CABECALHO = """/* Dados de demonstracao — os mesmos seis documentos, seis categorias e seis
   etapas do prototipo. Servem para os tres front-ends ficarem clicaveis antes
   do backend existir; quando a API responde, sao descartados.

   Gerado por ferramentas/gerar_dados_demo.py a partir do _build.py original. */

"""


def carregar_prototipo(pasta: Path):
    """Importa o _build.py da pasta de saida do prototipo."""
    caminho = pasta / "_build.py"
    if not caminho.exists():
        raise SystemExit(f"nao encontrei {caminho}")

    # O _build.py le o _src.html do proprio diretorio, entao precisa estar no path.
    sys.path.insert(0, str(pasta))
    spec = importlib.util.spec_from_file_location("_build_prototipo", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def montar_js(proto) -> str:
    etapas = [
        dict(titulo=s["title"], detalhe=s["detail"], logs=s["logs"])
        for s in proto.STEPS
    ]
    documentos = [
        dict(
            id=i + 1,
            arquivo=d["file"], origem=d["source"], tipo=d["type"],
            confianca=d["conf"], data=d["date"], destino=d["dest"],
            regra=d["rule"], chaves=d["keywords"], trecho=d["snippet"],
            etapas=[dict(titulo=p["title"], detalhe=p["detail"]) for p in d["pipeline"]],
        )
        for i, d in enumerate(proto.DOCS)
    ]
    categorias = [dict(nome=c["name"], contagem=c["count"]) for c in proto.CATS]

    def const(nome, valor):
        return "export const %s = %s;\n\n" % (
            nome, json.dumps(valor, ensure_ascii=False, indent=2)
        )

    return (
        CABECALHO
        + const("ETAPAS", etapas)
        + const("DOCUMENTOS", documentos)
        + const("CATEGORIAS", categorias)
        + 'export const ESTATISTICAS = '
          '{ arquivados: "1.284", hoje: "18", ocr: "7", revisar: "2" };\n'
        + 'export const PASTA_MONITORADA = '
          '"C:\\\\Users\\\\rafael\\\\AutoDoc\\\\Entrada";\n'
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    proto = carregar_prototipo(Path(sys.argv[1]).expanduser())
    SAIDA.write_text(montar_js(proto), encoding="utf-8")
    print(f"{SAIDA.relative_to(RAIZ)} — {len(proto.DOCS)} documentos, "
          f"{len(proto.STEPS)} etapas, {len(proto.CATS)} categorias")


if __name__ == "__main__":
    main()
