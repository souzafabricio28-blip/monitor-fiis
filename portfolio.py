"""
Normaliza a análise da carteira para HTML/PDF/Excel.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from db import DatabaseManager
from market_data import buscar_cotacao, calcular_dy


def analisar_carteira(db: DatabaseManager | None = None) -> Dict:
    """Retorna dict com chaves compatíveis com PDF, Excel e dashboard."""
    db = db or DatabaseManager()
    carteira = db.obter_carteira()
    if carteira.empty:
        return {"erro": "Carteira vazia"}

    analise = {
        "total_investido": 0.0,
        "total_atual": 0.0,
        "valor_atual": 0.0,
        "total_recebido": 0.0,
        "lucro": 0.0,
        "rendimento_mensal": 0.0,
        "rendimento_anual": 0.0,
        "dy_medio": 0.0,
        "rentabilidade": 0.0,
        "rentabilidade_com_dividendos": 0.0,
        "fiis": [],
        "data_analise": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    for _, row in carteira.iterrows():
        ticker = row["ticker"]
        quantidade = int(row["quantidade"])
        preco_compra = float(row["preco_compra"])
        cotacao = buscar_cotacao(ticker)
        if not cotacao:
            continue

        preco_atual = float(cotacao["preco_atual"])
        valor_investido = quantidade * preco_compra
        valor_atual = quantidade * preco_atual
        lucro = valor_atual - valor_investido
        lucro_pct = (lucro / valor_investido * 100) if valor_investido else 0

        dy_info = calcular_dy(ticker, preco_atual)
        dy_anual = dy_info["dy_anual"] if dy_info else 0.0
        dy_mensal = dy_info["dy_mensal"] if dy_info else 0.0
        div_12m = dy_info["total_dividendos_12m"] if dy_info else 0.0
        dividendos_recebidos = quantidade * div_12m
        rendimento_mensal = valor_atual * (dy_anual / 100) / 12 if dy_anual else 0

        analise["total_investido"] += valor_investido
        analise["total_atual"] += valor_atual
        analise["total_recebido"] += dividendos_recebidos
        analise["rendimento_mensal"] += rendimento_mensal

        item = {
            "ticker": ticker,
            "quantidade": quantidade,
            "preco_compra": preco_compra,
            "preco_atual": preco_atual,
            "valor_investido": valor_investido,
            "valor_atual": valor_atual,
            "lucro": lucro,
            "lucro_pct": lucro_pct,
            "lucro_prejuizo": lucro,
            "lucro_prejuizo_pct": lucro_pct,
            "dy": dy_anual,
            "dy_anual": dy_anual,
            "dy_mensal": dy_mensal,
            "dividendos_recebidos": dividendos_recebidos,
            "rendimento_mensal": rendimento_mensal,
        }
        analise["fiis"].append(item)
        db.salvar_cotacao(ticker, preco_atual, cotacao["data"])

    analise["valor_atual"] = analise["total_atual"]
    analise["lucro"] = analise["total_atual"] - analise["total_investido"]
    analise["rendimento_anual"] = analise["rendimento_mensal"] * 12
    if analise["total_atual"] > 0:
        analise["dy_medio"] = (
            analise["rendimento_mensal"] * 12 / analise["total_atual"]
        ) * 100
    if analise["total_investido"] > 0:
        analise["rentabilidade"] = (
            analise["lucro"] / analise["total_investido"]
        ) * 100
        analise["rentabilidade_com_dividendos"] = (
            (analise["total_atual"] + analise["total_recebido"] - analise["total_investido"])
            / analise["total_investido"]
        ) * 100

    return analise


def resumo_criterios(avaliacao: dict) -> dict:
    """Resume aprovação/reprovação/N/D de uma avaliação do criterios.py."""
    criterios: List[dict] = avaliacao.get("criterios") or []
    ok = sum(1 for c in criterios if c.get("ok") is True)
    fail = sum(1 for c in criterios if c.get("ok") is False)
    nd = sum(1 for c in criterios if c.get("ok") is None)
    if fail == 0 and ok > 0:
        status = "aprovado"
    elif fail > 0:
        status = "reprovado"
    else:
        status = "nd"
    return {"status": status, "ok": ok, "fail": fail, "nd": nd, "total": len(criterios)}
