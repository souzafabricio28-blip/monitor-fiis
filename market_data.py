"""
Dados de mercado via Yahoo Finance + Investidor10, com DY timezone-safe e cache.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from investidor10 import Investidor10API

_api = Investidor10API()
_mem_cache: Dict[str, tuple] = {}
CACHE_MINUTES = 20
LIMITE_DIVERGENCIA = 10.0
logger = logging.getLogger(__name__)


def _agora_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _registrar_meta(
    dados: Dict,
    indicador: str,
    valor,
    fonte: str,
    *,
    confianca: str = "media",
    status: str = "ok",
) -> None:
    dados[indicador] = valor
    dados.setdefault("qualidade", {})[indicador] = {
        "fonte": fonte,
        "coletado_em": _agora_iso(),
        "status": status,
        "confianca": confianca,
    }


def _divergencia_percentual(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or a == 0:
        return None
    return abs(float(a) - float(b)) / abs(float(a)) * 100


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
            "data_calculo": _agora_iso(),
            "fonte": "Yahoo Finance (proventos 12m)",
        }
    except Exception as exc:
        logger.warning("Falha ao calcular DY de %s: %s", ticker, exc)
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
            "variacao_dia": preco - anterior,
            "variacao_pct": ((preco - anterior) / anterior) * 100 if anterior else 0,
            "variacao": ((preco - anterior) / anterior) * 100 if anterior else 0,
            "data": _agora_iso(),
            "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
            "abertura": abertura,
            "maxima_dia": float(hist["High"].iloc[-1]),
            "minima_dia": float(hist["Low"].iloc[-1]),
            "preco_anterior": anterior,
        }
    except Exception as exc:
        logger.warning("Falha ao buscar cotação de %s: %s", ticker, exc)
        return None


def buscar_historico(ticker: str, periodo: str = "3mo") -> Optional[pd.DataFrame]:
    try:
        return yf.Ticker(f"{ticker.upper().replace('.SA', '')}.SA").history(period=periodo)
    except Exception as exc:
        logger.warning("Falha ao buscar histórico de %s: %s", ticker, exc)
        return None


def buscar_dividendos_serie(ticker: str) -> Optional[pd.Series]:
    try:
        divs = yf.Ticker(f"{ticker.upper().replace('.SA', '')}.SA").dividends
        return _naive_index(divs) if divs is not None else None
    except Exception as exc:
        logger.warning("Falha ao buscar dividendos de %s: %s", ticker, exc)
        return None


def buscar_dados_completos(ticker: str, db=None, usar_cache: bool = True) -> Dict:
    """Fonte única de mercado, com proveniência, N/D e validação cruzada."""
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

    dados: Dict = {
        "ticker": ticker,
        "nome": ticker,
        "preco_atual": None,
        "preco": None,
        "dy": None,
        "dy_mensal": None,
        "p_vp": None,
        "patrimonio": None,
        "vacancia": None,
        "setor": None,
        "qualidade": {},
        "divergencias": [],
        "coletado_em": _agora_iso(),
        "horario_dados": agora.strftime("%d/%m/%Y %H:%M:%S"),
    }
    fontes = []

    cotacao = buscar_cotacao(ticker)
    if cotacao:
        dados.update(cotacao)
        dados["preco"] = cotacao["preco_atual"]
        _registrar_meta(
            dados, "preco_atual", cotacao["preco_atual"], "Yahoo Finance", confianca="alta"
        )
        dados["preco"] = cotacao["preco_atual"]
        fontes.append("Yahoo Finance")
    else:
        _registrar_meta(
            dados, "preco_atual", None, "Yahoo Finance", confianca="baixa", status="indisponivel"
        )

    try:
        info = yf.Ticker(f"{ticker}.SA").info or {}
        dados["nome"] = info.get("longName") or info.get("shortName") or ticker
        dados["moeda"] = info.get("currency") or "BRL"
        if info.get("sector"):
            _registrar_meta(dados, "setor", info["sector"], "Yahoo Finance", confianca="baixa")
    except Exception as exc:
        logger.warning("Falha nos metadados Yahoo de %s: %s", ticker, exc)

    dy_calc = calcular_dy(ticker, dados.get("preco_atual"))
    if dy_calc:
        _registrar_meta(
            dados, "dy", dy_calc["dy_anual"], "Yahoo Finance (proventos 12m)", confianca="alta"
        )
        dados["dy_mensal"] = dy_calc["dy_mensal"]
        dados["total_dividendos_12m"] = dy_calc["total_dividendos_12m"]
    else:
        _registrar_meta(
            dados,
            "dy",
            None,
            "Yahoo Finance (proventos 12m)",
            confianca="baixa",
            status="indisponivel",
        )

    inv = _api.buscar_fii(ticker)
    if "erro" not in inv:
        fontes.append("Investidor10")
        dados["nome"] = inv.get("nome") or dados["nome"]
        for campo in ("p_vp", "patrimonio", "vacancia", "setor"):
            valor = inv.get(campo)
            if valor is not None:
                _registrar_meta(dados, campo, valor, "Investidor10", confianca="media")
            elif dados.get(campo) is None:
                _registrar_meta(
                    dados, campo, None, "Investidor10", confianca="baixa", status="indisponivel"
                )

        preco_inv = inv.get("preco")
        if dados.get("preco_atual") is None and preco_inv is not None:
            _registrar_meta(
                dados, "preco_atual", preco_inv, "Investidor10", confianca="baixa"
            )
            dados["preco"] = preco_inv
        div_preco = _divergencia_percentual(dados.get("preco_atual"), preco_inv)
        div_dy = _divergencia_percentual(dados.get("dy"), inv.get("dy"))
        for indicador, divergencia in (("preco_atual", div_preco), ("dy", div_dy)):
            if divergencia is not None:
                dados["qualidade"][indicador]["divergencia_pct"] = round(divergencia, 2)
                if divergencia > LIMITE_DIVERGENCIA:
                    dados["qualidade"][indicador]["status"] = "divergente"
                    dados["qualidade"][indicador]["confianca"] = "baixa"
                    dados["divergencias"].append(
                        f"{indicador}: fontes divergem {divergencia:.1f}%"
                    )
        dados["dy_investidor10"] = inv.get("dy")
    else:
        dados["erro_investidor10"] = inv.get("erro")
        for campo in ("p_vp", "patrimonio", "vacancia"):
            if campo not in dados["qualidade"]:
                _registrar_meta(
                    dados, campo, None, "Investidor10", confianca="baixa", status="indisponivel"
                )

    dados["fonte"] = " + ".join(dict.fromkeys(fontes)) or "fontes indisponíveis"
    disponiveis = sum(
        dados.get(campo) is not None
        for campo in ("preco_atual", "dy", "p_vp", "patrimonio", "vacancia")
    )
    dados["status_geral"] = (
        "ok" if disponiveis == 5 and not dados["divergencias"]
        else "parcial" if disponiveis
        else "indisponivel"
    )
    dados["confianca"] = (
        "alta" if dados["status_geral"] == "ok"
        else "media" if dados["status_geral"] == "parcial" and not dados["divergencias"]
        else "baixa"
    )

    _mem_cache[ticker] = (dict(dados), agora)
    if db is not None:
        try:
            db.set_cache(ticker, dados)
            if dados.get("preco_atual") is not None:
                db.salvar_cotacao(ticker, float(dados["preco_atual"]))
        except Exception as exc:
            logger.warning("Falha ao persistir cache/cotação de %s: %s", ticker, exc)
    return dados
