"""Lista enviada pelo gestor (Ricardo, RT Tintas) em 28/08/2026."""

from __future__ import annotations

# Tickers 11/12 que são units/ações na B3, não FII.
TICKERS_ACAO_MESMO_COM_11 = frozenset(
    {
        "TAEE11",
        "ALUP11",
        "ENGI11",
        "SAPR11",
        "CPLE11",
        "SANB11",
        "KLBN11",
        "BPAC11",
        "TIET11",
    }
)

FUNDOS_GESTOR = [
    "HGLG11",
    "BTLG11",
    "MXRF11",
    "VISC11",
    "XPLG11",
    "RZTR11",
    "HSML11",
]

# BBAS3 veio duplicado no WhatsApp; entra uma vez.
ACOES_GESTOR = [
    "BBAS3",
    "ITSA3",
    "TAEE11",
    "SAPR4",
    "PETR4",
    "VALE3",
    "KLBN4",
]
