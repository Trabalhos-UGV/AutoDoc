"""Cobertura de linhas dos testes, usando so a biblioteca padrao.

    python3 ferramentas/cobertura.py                    # tabela por modulo
    python3 ferramentas/cobertura.py autodoc/monitor.py # so um modulo, com as
                                                        # linhas nao cobertas

Nao ha `coverage` instalado, e nao deve haver: o AutoDoc nao acrescenta
dependencia para medir a si mesmo. O `trace` da biblioteca padrao conta quais
linhas rodaram, e o `dis` diz quais linhas eram executaveis — a razao entre as
duas e a cobertura.

**O detalhe que muda tudo:** `threading.settrace()` antes de rodar a suite. O
`sys.settrace` vale por thread, e sem registrar o rastreador para as threads
novas o servidor HTTP e o observador do watchdog ficam invisiveis — o
`servidor.py` aparecia com 35% quando na verdade tinha 73%.

Como o resto de ferramentas/, este script nao entra no caminho de execucao do
programa; existe para o grupo poder repetir a medida.
"""

from __future__ import annotations

import dis
import io
import sys
import threading
import trace
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_TESTES = RAIZ / "testes"

# Abaixo disto o modulo aparece marcado, para saltar aos olhos na tabela.
ALVO = 90


def linhas_executaveis(caminho: Path) -> set[int]:
    """As linhas do arquivo que geram bytecode — as unicas que podem ser cobertas.

    Linha em branco, comentario e continuacao de expressao nao contam. O `dis`
    sabe disso melhor do que qualquer heuristica de texto.
    """
    try:
        codigo = compile(caminho.read_text(encoding="utf-8"), str(caminho), "exec")
    except (SyntaxError, UnicodeDecodeError):
        return set()

    encontradas: set[int] = set()
    pilha = [codigo]
    while pilha:
        atual = pilha.pop()
        for _, linha in dis.findlinestarts(atual):
            # `None` e `0` sao artefatos do bytecode de nivel de modulo, e nao
            # linhas do arquivo: contá-los deixaria todo modulo abaixo de 100%
            # sem que houvesse nada para cobrir.
            if linha:
                encontradas.add(linha)
        pilha.extend(c for c in atual.co_consts if hasattr(c, "co_code"))
    return encontradas


def rodar_suite() -> dict[str, set[int]]:
    """Roda os testes sob o rastreador e devolve as linhas visitadas por arquivo."""
    rastreador = trace.Trace(count=1, trace=0,
                             ignoredirs=[sys.prefix, sys.exec_prefix])

    def suite():
        carregador = unittest.TestLoader()
        testes = carregador.discover(str(PASTA_TESTES), top_level_dir=str(RAIZ))
        unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(testes)

    # Sem isto, tudo que roda em thread — servidor HTTP, watchdog — fica de fora.
    threading.settrace(rastreador.globaltrace)
    try:
        rastreador.runfunc(suite)
    finally:
        threading.settrace(None)

    visitadas: dict[str, set[int]] = {}
    for (arquivo, linha), _ in rastreador.results().counts.items():
        visitadas.setdefault(arquivo, set()).add(linha)
    return visitadas


def faixas(numeros: list[int]) -> str:
    """[3, 4, 5, 9] -> "3-5, 9" — mais curto de ler do que a lista inteira."""
    if not numeros:
        return ""

    grupos: list[tuple[int, int]] = []
    inicio = anterior = numeros[0]
    for numero in numeros[1:]:
        if numero != anterior + 1:
            grupos.append((inicio, anterior))
            inicio = numero
        anterior = numero
    grupos.append((inicio, anterior))

    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in grupos)


def modulos(filtro: str | None) -> list[Path]:
    todos = sorted(list((RAIZ / "autodoc").rglob("*.py"))
                   + [RAIZ / "main.py", RAIZ / "instalar.py"])
    todos = [c for c in todos if "__pycache__" not in str(c)]
    if not filtro:
        return todos
    return [c for c in todos if filtro in str(c.relative_to(RAIZ))]


def main() -> int:
    filtro = sys.argv[1] if len(sys.argv) > 1 else None
    alvos = modulos(filtro)
    if not alvos:
        print(f"nenhum modulo casa com {filtro!r}")
        return 1

    print("rodando a suite sob o rastreador...\n")
    visitadas = rodar_suite()

    print(f"{'modulo':38} {'linhas':>7} {'cobertas':>9} {'%':>6}   nao cobertas")
    print("-" * 100)

    total_executaveis = total_cobertas = 0
    for alvo in alvos:
        executaveis = linhas_executaveis(alvo)
        if not executaveis:
            continue

        cobertas = visitadas.get(str(alvo), set()) & executaveis
        faltando = sorted(executaveis - cobertas)
        porcentagem = 100 * len(cobertas) / len(executaveis)

        total_executaveis += len(executaveis)
        total_cobertas += len(cobertas)

        marca = " " if porcentagem >= ALVO else "!"
        print(f"{str(alvo.relative_to(RAIZ)):38} {len(executaveis):>7} "
              f"{len(cobertas):>9} {porcentagem:>5.0f}%{marca}  {faixas(faltando)[:140]}")

    print("-" * 100)
    geral = 100 * total_cobertas / total_executaveis if total_executaveis else 100
    print(f"{'TOTAL':38} {total_executaveis:>7} {total_cobertas:>9} {geral:>5.0f}%")

    if geral < ALVO:
        print(f"\nabaixo do alvo de {ALVO}%")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
