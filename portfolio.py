"""
Normaliza a análise da carteira para HTML/PDF/Excel.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List

from db import DatabaseManager
from market_data import (
    buscar_cotacoes_lote,
    buscar_dados_completos,
    calcular_dy,
    dados_rapidos,
    sincronizar_proventos,
)


def _quantidade_na_data(movimentos, data_pagamento: str) -> int:
    quantidade = 0
    limite = str(data_pagamento)[:10]
    for _, mov in movimentos.iterrows():
        if str(mov["data_movimentacao"])[:10] > limite:
            continue
        sinal = -1 if mov["tipo"] == "VENDA" else 1
        quantidade += sinal * int(mov["quantidade"])
    return max(quantidade, 0)


def rentabilidade_total(valor_atual, proventos, investido):
    """Lucro e % com preço + proventos registados. Cotação ausente continua N/D."""
    if valor_atual is None or investido is None:
        return None, None
    try:
        atual = float(valor_atual)
        custo = float(investido)
        recebido = float(proventos or 0)
    except (TypeError, ValueError):
        return None, None
    if custo <= 0:
        return None, None
    lucro = atual + recebido - custo
    return lucro, (lucro / custo) * 100


def _proventos_de_frames(dividendos, movimentos, ticker: str) -> float:
    if dividendos is None or getattr(dividendos, "empty", True):
        return 0.0
    if movimentos is None or getattr(movimentos, "empty", True):
        return 0.0
    divs = dividendos[dividendos["ticker"].astype(str).str.upper() == ticker]
    movs = movimentos[movimentos["ticker"].astype(str).str.upper() == ticker]
    if divs.empty or movs.empty:
        return 0.0
    return sum(
        _quantidade_na_data(movs, row["data_pagamento"]) * float(row["valor_por_cota"])
        for _, row in divs.iterrows()
    )


def _dy_por_cota_12m(dividendos, ticker: str):
    if dividendos is None or getattr(dividendos, "empty", True):
        return None
    divs = dividendos[dividendos["ticker"].astype(str).str.upper() == ticker]
    if divs.empty:
        return None
    total = float(divs["valor_por_cota"].sum())
    return total if total > 0 else None


def _proventos_registrados(db: DatabaseManager, ticker: str) -> float:
    return _proventos_de_frames(db.obter_dividendos(ticker), db.obter_movimentacoes(ticker), ticker)


def _cotacoes_em_paralelo(
    tickers: List[str],
    db: DatabaseManager,
    max_idade_min: int = 20,
) -> Dict[str, dict]:
    """Cotações em lote: Investidor10 prevalece; Yahoo fica de reserva."""
    resultado: Dict[str, dict] = {}
    pendentes: List[str] = []
    vistos: List[str] = []
    for ticker in tickers:
        if ticker in vistos:
            continue
        vistos.append(ticker)
        cached = db.get_cache(ticker, max_idade_min) if max_idade_min else None
        fonte_cache = str((cached or {}).get("fonte") or "").casefold()
        if (
            cached
            and "erro" not in cached
            and cached.get("preco_atual") is not None
            and (
                "investidor10" in fonte_cache
                or "consenso" in fonte_cache
                or "google" in fonte_cache
            )
        ):
            resultado[ticker] = cached
        else:
            pendentes.append(ticker)

    if pendentes:
        lote = buscar_cotacoes_lote(pendentes)
        for ticker in pendentes:
            cotacao = lote.get(ticker) or {}
            preco = cotacao.get("preco_atual")
            fonte = cotacao.get("fonte") or ("Investidor10" if preco is not None else "Yahoo Finance")
            dados = dados_rapidos(
                ticker,
                preco=preco,
                dy=cotacao.get("dy"),
                fonte=fonte,
            )
            if cotacao.get("url_investidor10"):
                dados["url_investidor10"] = cotacao["url_investidor10"]
            if cotacao.get("p_l") is not None:
                dados["p_l"] = cotacao["p_l"]
            if cotacao.get("p_vp") is not None:
                dados["p_vp"] = cotacao["p_vp"]
            if cotacao.get("variacao_12m") is not None:
                dados["variacao_12m"] = cotacao["variacao_12m"]
            resultado[ticker] = dados
            try:
                db.set_cache(ticker, dados)
                if preco is not None:
                    db.salvar_cotacao(ticker, float(preco))
            except Exception:
                pass
    return resultado


def analisar_carteira(db: DatabaseManager | None = None, max_idade_min: int = 20) -> Dict:
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
        "rentabilidade_com_dividendos": None,
        "lucro_com_dividendos": None,
        "fiis": [],
        "data_analise": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    tickers = [str(row["ticker"]).upper() for _, row in carteira.iterrows()]
    dados_por_ticker = _cotacoes_em_paralelo(tickers, db, max_idade_min=max_idade_min)
    dividendos = db.obter_dividendos(meses=12)
    movimentos = db.obter_movimentacoes()

    falta_dy = []
    for ticker, dados in dados_por_ticker.items():
        if dados.get("total_dividendos_12m") is not None and dados.get("dy") is not None:
            continue
        por_cota = _dy_por_cota_12m(dividendos, ticker)
        preco = dados.get("preco_atual")
        if por_cota is not None and preco:
            dados["total_dividendos_12m"] = por_cota
            dados["dy"] = por_cota / float(preco) * 100
            dados["dy_mensal"] = dados["dy"] / 12
        elif dados.get("dy") is None:
            falta_dy.append(ticker)

    if falta_dy:
        workers = min(8, len(falta_dy))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pares = list(
                pool.map(
                    lambda t: (t, calcular_dy(t, dados_por_ticker[t].get("preco_atual"))),
                    falta_dy,
                )
            )
        sincronizou = False
        for ticker, dy_calc in pares:
            if not dy_calc:
                continue
            dados_por_ticker[ticker]["dy"] = dy_calc["dy_anual"]
            dados_por_ticker[ticker]["dy_mensal"] = dy_calc["dy_mensal"]
            dados_por_ticker[ticker]["total_dividendos_12m"] = dy_calc["total_dividendos_12m"]
            dados_por_ticker[ticker]["pagamentos"] = dy_calc.get("pagamentos") or []
            try:
                sincronizar_proventos(db, ticker, dados_por_ticker[ticker]["pagamentos"])
                sincronizou = True
            except Exception:
                pass
        if sincronizou:
            dividendos = db.obter_dividendos(meses=12)

    for _, row in carteira.iterrows():
        ticker = str(row["ticker"]).upper()
        quantidade = int(row["quantidade"])
        preco_compra = float(row["preco_compra"])
        valor_investido = quantidade * preco_compra
        analise["total_investido"] += valor_investido

        dados = dados_por_ticker.get(ticker) or buscar_dados_completos(
            ticker, db=db, incluir_fundamentos=False
        )
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
        proventos = _proventos_de_frames(dividendos, movimentos, ticker)
        lucro_total, lucro_total_pct = rentabilidade_total(
            valor_atual, proventos, valor_investido
        )
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
            "lucro_com_dividendos": lucro_total,
            "lucro_com_dividendos_pct": lucro_total_pct,
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
            "p_vp": dados.get("p_vp"),
            "p_l": dados.get("p_l"),
            "variacao_12m": dados.get("variacao_12m"),
            "url_investidor10": dados.get("url_investidor10"),
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
        lucro_total_carteira, pct_total = rentabilidade_total(
            analise["total_atual"],
            analise["total_recebido"],
            analise["total_investido"],
        )
        analise["lucro_com_dividendos"] = lucro_total_carteira
        analise["rentabilidade_com_dividendos"] = pct_total
    else:
        analise["lucro_com_dividendos"] = None
        analise["rentabilidade_com_dividendos"] = None

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
