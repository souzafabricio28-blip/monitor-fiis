"""
Normaliza a análise da carteira para HTML/PDF/Excel.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from db import DatabaseManager
from market_data import buscar_dados_completos


def _quantidade_na_data(movimentos, data_pagamento: str) -> int:
    quantidade = 0
    limite = str(data_pagamento)[:10]
    for _, mov in movimentos.iterrows():
        if str(mov["data_movimentacao"])[:10] > limite:
            continue
        sinal = -1 if mov["tipo"] == "VENDA" else 1
        quantidade += sinal * int(mov["quantidade"])
    return max(quantidade, 0)


def _proventos_registrados(db: DatabaseManager, ticker: str) -> float:
    dividendos = db.obter_dividendos(ticker)
    movimentos = db.obter_movimentacoes(ticker)
    if dividendos.empty or movimentos.empty:
        return 0.0
    return sum(
        _quantidade_na_data(movimentos, row["data_pagamento"])
        * float(row["valor_por_cota"])
        for _, row in dividendos.iterrows()
    )


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
        "proventos_registrados": 0.0,
        "projecao_renda_mensal": 0.0,
        "posicoes_sem_cotacao": [],
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
        valor_investido = quantidade * preco_compra
        analise["total_investido"] += valor_investido

        dados = buscar_dados_completos(ticker, db=db)
        preco_valor = dados.get("preco_atual")
        preco_atual = float(preco_valor) if preco_valor is not None else None
        valor_atual = quantidade * preco_atual if preco_atual is not None else None
        lucro = valor_atual - valor_investido if valor_atual is not None else None
        lucro_pct = (
            lucro / valor_investido * 100
            if lucro is not None and valor_investido
            else None
        )

        dy_anual = dados.get("dy")
        dy_mensal = dados.get("dy_mensal")
        div_12m = dados.get("total_dividendos_12m")
        proventos = _proventos_registrados(db, ticker)
        projecao_mensal = (
            quantidade * float(div_12m) / 12 if div_12m is not None else None
        )

        if valor_atual is not None:
            analise["total_atual"] += valor_atual
        else:
            analise["posicoes_sem_cotacao"].append(ticker)
        analise["total_recebido"] += proventos
        analise["proventos_registrados"] += proventos
        if projecao_mensal is not None:
            analise["rendimento_mensal"] += projecao_mensal
            analise["projecao_renda_mensal"] += projecao_mensal

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
            "dividendos_recebidos": proventos,
            "proventos_registrados": proventos,
            "projecao_renda_mensal": projecao_mensal,
            "rendimento_mensal": projecao_mensal,
            "status_dados": dados.get("status_geral"),
            "confianca": dados.get("confianca"),
            "fonte": dados.get("fonte"),
            "coletado_em": dados.get("coletado_em"),
            "divergencias": dados.get("divergencias", []),
        }
        analise["fiis"].append(item)

    analise["valor_atual"] = analise["total_atual"]
    analise["lucro"] = (
        analise["total_atual"] - analise["total_investido"]
        if not analise["posicoes_sem_cotacao"]
        else None
    )
    analise["rendimento_anual"] = analise["rendimento_mensal"] * 12
    if analise["total_atual"] > 0:
        analise["dy_medio"] = (
            analise["rendimento_mensal"] * 12 / analise["total_atual"]
        ) * 100
    if analise["total_investido"] > 0 and analise["lucro"] is not None:
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
