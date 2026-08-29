#!/usr/bin/env python3
"""Gera o PDF resumido da lista do Ricardo (sem tela no app)."""

from pathlib import Path
import sys

from lista_gestor_pdf import (
    avaliar_lista_completa,
    gerar_pdf_lista_gestor_bytes,
    montar_resumo_lista,
)

DESTINOS = [
    Path("/opt/cursor/artifacts/analise_lista_ricardo.pdf"),
    Path("/workspace/Documentos/analise_lista_ricardo.pdf"),
    Path.home() / "Documentos" / "analise_lista_ricardo.pdf",
]


def main() -> int:
    live = "--catalogo" not in sys.argv
    if live:
        avaliacoes = avaliar_lista_completa(permitir_scrape=False)
        resumo = montar_resumo_lista(avaliacoes)
    else:
        resumo = montar_resumo_lista()
    pdf = gerar_pdf_lista_gestor_bytes(resumo)
    ultimo = None
    for destino in DESTINOS:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(pdf)
        ultimo = destino
        print(f"PDF salvo: {destino}")
    return 0 if ultimo else 1


if __name__ == "__main__":
    raise SystemExit(main())
