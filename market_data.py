"""
Dados de mercado via Yahoo Finance + Investidor10, com DY timezone-safe e cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from investidor10 import Investidor10API

_api = Investidor10API()
_mem_cache: Dict[str, tuple] = {}
CACHE_MINUTES = 20


def _naive_index(series: pd.Series) -> pd.Series:
    if series is None or series.empty:
        return series
    idx = series.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    return pd.Series(series.to_numpy(), index=idx)


def calcular_dy(ticker: str, preco: Optional[float] = None) -> Optional[Dict]:
    """Calcula DY dos últimos 12 meses sem erro de timezone."""
    try:
        symbol = f"{ticker.upper().replace('.SA', '')}.SA"
        fii = yf.Ticker(symbol)
        dividendos = fii.dividends
        if dividendos is None or dividendos.empty:
            return None

        dividendos = _naive_index(dividendos)
        limite = pd.Timestamp((datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
        recentes = dividendos[dividendos.index >= limite]
        if recentes.empty:
            return None

        total = float(recentes.sum())
        if preco is None or preco <= 0:
            hist = fii.history(period="5d")
            if hist.empty:
                return None
            preco = float(hist["Close"].iloc[-1])

        if preco <= 0:
            return None

        dy_anual = (total / preco) * 100
        return {
            "ticker": ticker.upper().replace(".SA", ""),
            "dy_anual": dy_anual,
            "dy_mensal": dy_anual / 12,
            "total_dividendos_12m": total,
            "preco_atual": preco,
            "data_calculo": datetime.now().strftime("%Y-%m-%d"),
        }
    except Exception:
        return None


def buscar_cotacao(ticker: str) -> Optional[Dict]:
    try:
        symbol = f"{ticker.upper().replace('.SA', '')}.SA"
        fii = yf.Ticker(symbol)
        hist = fii.history(period="5d")
        if hist.empty:
            return None
        preco = float(hist["Close"].iloc[-1])
        abertura = float(hist["Open"].iloc[-1])
        anterior = float(hist["Close"].iloc[-2]) if len(hist) > 1 else preco
        return {
            "ticker": ticker.upper().replace(".SA", ""),
            "preco_atual": preco,
            "variacao_dia": preco - abertura,
            "variacao_pct": ((preco - anterior) / anterior) * 100 if anterior else 0,
            "data": datetime.now().strftime("%Y-%m-%d"),
            "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
            "abertura": abertura,
            "maxima_dia": float(hist["High"].iloc[-1]),
            "minima_dia": float(hist["Low"].iloc[-1]),
            "preco_anterior": anterior,
        }
    except Exception:
        return None


def buscar_historico(ticker: str, periodo: str = "3mo") -> Optional[pd.DataFrame]:
    try:
        return yf.Ticker(f"{ticker.upper().replace('.SA', '')}.SA").history(period=periodo)
    except Exception:
        return None


def buscar_dividendos_serie(ticker: str) -> Optional[pd.Series]:
    try:
        divs = yf.Ticker(f"{ticker.upper().replace('.SA', '')}.SA").dividends
        return _naive_index(divs) if divs is not None else None
    except Exception:
        return None


def buscar_dados_completos(ticker: str, db=None, usar_cache: bool = True) -> Dict:
    """Yahoo + Investidor10, com cache em memória e opcionalmente no banco."""
    ticker = ticker.upper().replace(".SA", "").strip()

    if usar_cache and db is not None:
        cached = db.get_cache(ticker, CACHE_MINUTES)
        if cached and "erro" not in cached:
            cached["fonte_cache"] = "banco"
            return cached

    agora = datetime.now()
    if usar_cache and ticker in _mem_cache:
        dados, ts = _mem_cache[ticker]
        if (agora - ts).total_seconds() < CACHE_MINUTES * 60 and "erro" not in dados:
            out = dict(dados)
            out["fonte_cache"] = "memoria"
            return out

    dados: Dict = {"ticker": ticker}

    try:
        cotacao = buscar_cotacao(ticker)
        if cotacao:
            dados.update(cotacao)

        acao = yf.Ticker(f"{ticker}.SA")
        info = acao.info or {}
        dados["nome"] = info.get("longName") or info.get("shortName") or ticker
        dy_raw = info.get("dividendYield") or 0
        dados["dy"] = dy_raw * 100 if 0 < dy_raw < 1 else dy_raw
        dados["p_vp"] = info.get("priceToBook") or 0
        dados["patrimonio"] = info.get("totalAssets") or 0
        dados["setor"] = info.get("sector") or "FII"
        dados["moeda"] = info.get("currency", "BRL")
        dados["horario_dados"] = agora.strftime("%d/%m/%Y %H:%M:%S")
        dados["fonte"] = "Yahoo Finance"

        dy_calc = calcular_dy(ticker, dados.get("preco_atual"))
        if dy_calc:
            dados["dy"] = dy_calc["dy_anual"]
            dados["dy_mensal"] = dy_calc["dy_mensal"]
            dados["total_dividendos_12m"] = dy_calc["total_dividendos_12m"]

        inv = _api.buscar_fii(ticker)
        if "erro" not in inv:
            if inv.get("dy"):
                dados["dy_investidor10"] = inv["dy"]
                if not dados.get("dy"):
                    dados["dy"] = inv["dy"]
            if inv.get("p_vp"):
                dados["p_vp"] = inv["p_vp"]
            if inv.get("vacancia") is not None:
                dados["vacancia"] = inv["vacancia"]
            if inv.get("patrimonio"):
                dados["patrimonio"] = inv["patrimonio"]
            if inv.get("setor"):
                dados["setor"] = inv["setor"]
            if inv.get("preco") and not dados.get("preco_atual"):
                dados["preco_atual"] = inv["preco"]
                dados["preco"] = inv["preco"]
            dados["fonte"] = "Yahoo Finance + Investidor10"

        if not dados.get("preco_atual") and dados.get("preco"):
            dados["preco_atual"] = dados["preco"]

        _mem_cache[ticker] = (dict(dados), agora)
        if db is not None and "erro" not in dados:
            try:
                db.set_cache(ticker, dados)
                if dados.get("preco_atual"):
                    db.salvar_cotacao(ticker, float(dados["preco_atual"]))
            except Exception:
                pass

        return dados
    except Exception as e:
        inv = _api.buscar_fii(ticker)
        if "erro" in inv:
            return {"ticker": ticker, "erro": str(e)}
        inv["preco_atual"] = inv.get("preco", 0)
        inv["horario_dados"] = agora.strftime("%d/%m/%Y %H:%M:%S")
        inv["fonte"] = "Investidor10 (Fallback)"
        return inv
