"""
Lista curada de FIIs por segmento (sem ações misturadas).
"""

from __future__ import annotations

from typing import Optional

FIIS_DATABASE = {
    "papel": [
        {"ticker": "MXRF11", "nome": "Maxi Renda", "setor": "Papel"},
        {"ticker": "KNCR11", "nome": "Kinea Rendimentos", "setor": "Papel"},
        {"ticker": "KNHY11", "nome": "Kinea High Yield", "setor": "Papel"},
        {"ticker": "CPTS11", "nome": "Capitânia Securities", "setor": "Papel"},
        {"ticker": "MCCI11", "nome": "Mauá Capital", "setor": "Papel"},
        {"ticker": "IRDM11", "nome": "Iridium Recebíveis", "setor": "Papel"},
        {"ticker": "KNSC11", "nome": "Kinea Securities", "setor": "Papel"},
        {"ticker": "VGIR11", "nome": "Valora CRI CDI", "setor": "Papel"},
        {"ticker": "BTCI11", "nome": "BTG CRI", "setor": "Papel"},
    ],
    "logistica": [
        {"ticker": "HGLG11", "nome": "CSHG Logística", "setor": "Logística/Galpão"},
        {"ticker": "BTLG11", "nome": "BTG Pactual Logística", "setor": "Logística/Galpão"},
        {"ticker": "VILG11", "nome": "Vinci Logística", "setor": "Logística/Galpão"},
        {"ticker": "GGRC11", "nome": "GGR Covepi", "setor": "Logística/Galpão"},
        {"ticker": "XPLG11", "nome": "XP Log", "setor": "Logística/Galpão"},
    ],
    "shopping": [
        {"ticker": "XPML11", "nome": "XP Malls", "setor": "Shopping"},
        {"ticker": "VISC11", "nome": "Vinci Shopping Centers", "setor": "Shopping"},
        {"ticker": "HSML11", "nome": "HSI Malls", "setor": "Shopping"},
        {"ticker": "MALL11", "nome": "Malls Brasil Plural", "setor": "Shopping"},
    ],
    "empresarial": [
        {"ticker": "KNRI11", "nome": "Kinea Renda Imobiliária", "setor": "Empresarial"},
        {"ticker": "HGRE11", "nome": "CSHG Real Estate", "setor": "Empresarial"},
        {"ticker": "RCRB11", "nome": "Rio Bravo Renda Corporativa", "setor": "Empresarial"},
    ],
    "hibrido": [
        {"ticker": "RBRR11", "nome": "RBR Rendimento High Grade", "setor": "Híbrido"},
        {"ticker": "TRXF11", "nome": "TRX Real Estate", "setor": "Híbrido"},
        {"ticker": "HFOF11", "nome": "Hedge Top FOFII", "setor": "FOF"},
        {"ticker": "RZTR11", "nome": "Riza Terrax", "setor": "Outro/Híbrido"},
    ],
}

FIIS_POPULARES = [
    "MXRF11",
    "KNCR11",
    "CPTS11",
    "MCCI11",
    "IRDM11",
    "HGLG11",
    "XPML11",
    "KNRI11",
    "BTLG11",
    "VISC11",
    "HSML11",
    "KNHY11",
    "VILG11",
    "VGIR11",
    "BTCI11",
]

FIIS_DATABASE["todos"] = []
for setor, lista in FIIS_DATABASE.items():
    if setor != "todos" and isinstance(lista, list):
        FIIS_DATABASE["todos"].extend(lista)


def buscar_fii_por_ticker(ticker: str) -> Optional[dict]:
    ticker = ticker.upper()
    for setor, fiis in FIIS_DATABASE.items():
        if setor == "todos":
            continue
        for fii in fiis:
            if fii["ticker"] == ticker:
                return fii
    return None


def listar_fiis_por_setor(setor: str) -> list:
    return FIIS_DATABASE.get(setor.lower(), [])


def obter_todos_tickers() -> list:
    return [fii["ticker"] for fii in FIIS_DATABASE["todos"]]


def obter_estatisticas() -> dict:
    por_setor = {
        setor: len(fiis)
        for setor, fiis in FIIS_DATABASE.items()
        if setor != "todos" and isinstance(fiis, list)
    }
    return {"total": len(FIIS_DATABASE["todos"]), "por_setor": por_setor}
