"""
Dados de mercado via Yahoo Finance, Investidor10 e fontes extras
(Fundamentus, Funds Explorer, Brapi, Mais Retorno, PTAX).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import pandas as pd
import yfinance as yf

from investidor10 import CAMPOS_I10, Investidor10API
from fontes_extras import aplicar_fontes_extras, consultar_fontes_extras

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
        pagamentos = [
            {
                "data": idx.strftime("%Y-%m-%d"),
                "valor": float(val),
            }
            for idx, val in recentes.items()
            if float(val) > 0
        ]
        return {
            "ticker": ticker.upper().replace(".SA", ""),
            "dy_anual": dy_anual,
            "dy_mensal": dy_anual / 12,
            "total_dividendos_12m": total,
            "preco_atual": preco,
            "data_calculo": _agora_iso(),
            "fonte": "Yahoo Finance (proventos 12m)",
            "pagamentos": pagamentos,
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


def limpar_cache_memoria() -> None:
    _mem_cache.clear()


def _tickers_unicos(tickers: Iterable[str]) -> List[str]:
    vistos: List[str] = []
    for ticker in tickers:
        limpo = (ticker or "").upper().replace(".SA", "").strip()
        if limpo and limpo not in vistos:
            vistos.append(limpo)
    return vistos


def _close_de_historico(hist: pd.DataFrame, simbolo: str, unico: bool = False) -> Optional[float]:
    if hist is None or getattr(hist, "empty", True):
        return None
    try:
        if unico or not isinstance(hist.columns, pd.MultiIndex):
            if "Close" in hist.columns:
                serie = hist["Close"].dropna()
                if not serie.empty:
                    return float(serie.iloc[-1])
        candidatos = (simbolo, simbolo.replace(".SA", ""), f"{simbolo.replace('.SA', '')}.SA")
        for cand in candidatos:
            chave = (cand, "Close")
            if isinstance(hist.columns, pd.MultiIndex) and chave in hist.columns:
                serie = hist[chave].dropna()
                if not serie.empty:
                    return float(serie.iloc[-1])
            chave_inv = ("Close", cand)
            if isinstance(hist.columns, pd.MultiIndex) and chave_inv in hist.columns:
                serie = hist[chave_inv].dropna()
                if not serie.empty:
                    return float(serie.iloc[-1])
            if isinstance(hist.columns, pd.MultiIndex):
                nivel0 = list(hist.columns.get_level_values(0))
                if cand in nivel0 and "Close" in hist[cand].columns:
                    serie = hist[cand]["Close"].dropna()
                    if not serie.empty:
                        return float(serie.iloc[-1])
    except Exception:
        return None
    return None


def buscar_cotacoes_lote(tickers: Iterable[str]) -> Dict[str, dict]:
    """Uma chamada Yahoo para vários tickers; fallback individual só no que faltar."""
    limpos = _tickers_unicos(tickers)
    if not limpos:
        return {}
    simbolos = [f"{t}.SA" for t in limpos]
    saida: Dict[str, dict] = {}
    try:
        hist = yf.download(
            tickers=simbolos if len(simbolos) > 1 else simbolos[0],
            period="5d",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
        for ticker, simbolo in zip(limpos, simbolos):
            preco = _close_de_historico(hist, simbolo, unico=len(limpos) == 1)
            if preco is None:
                continue
            saida[ticker] = {
                "ticker": ticker,
                "preco_atual": preco,
                "preco": preco,
                "fonte": "Yahoo Finance",
                "coletado_em": _agora_iso(),
            }
    except Exception as exc:
        logger.warning("Falha no download em lote do Yahoo: %s", exc)

    faltando = [t for t in limpos if t not in saida]
    if faltando:
        workers = min(8, len(faltando))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pares = list(zip(faltando, pool.map(buscar_cotacao, faltando)))
        for ticker, cotacao in pares:
            if cotacao:
                saida[ticker] = cotacao
    return saida


def dados_rapidos(
    ticker: str,
    preco: Optional[float] = None,
    dy: Optional[float] = None,
    dy_mensal: Optional[float] = None,
    total_dividendos_12m: Optional[float] = None,
) -> Dict:
    """Monta o payload do dashboard sem scrape e sem yf.Ticker.info."""
    ticker = ticker.upper().replace(".SA", "").strip()
    agora = datetime.now()
    dados: Dict = {
        "ticker": ticker,
        "nome": ticker,
        "preco_atual": preco,
        "preco": preco,
        "dy": dy,
        "dy_mensal": dy_mensal,
        "total_dividendos_12m": total_dividendos_12m,
        "p_vp": None,
        "patrimonio": None,
        "vacancia": None,
        "setor": None,
        "qualidade": {},
        "divergencias": [],
        "coletado_em": _agora_iso(),
        "horario_dados": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "fonte": "Yahoo Finance",
        "status_geral": "parcial" if preco is not None or dy is not None else "indisponivel",
        "confianca": "media" if preco is not None else "baixa",
    }
    if preco is not None:
        _registrar_meta(dados, "preco_atual", preco, "Yahoo Finance", confianca="alta")
    if dy is not None:
        _registrar_meta(dados, "dy", dy, "Yahoo Finance (proventos 12m)", confianca="alta")
    return dados


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


def sincronizar_proventos(db, ticker: str, pagamentos: Optional[list] = None) -> int:
    """Grava pagamentos de proventos no banco (idempotente por data)."""
    if db is None:
        return 0
    ticker = ticker.upper().replace(".SA", "").strip()
    if pagamentos is None:
        serie = buscar_dividendos_serie(ticker)
        if serie is None or serie.empty:
            return 0
        limite = pd.Timestamp((datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
        recentes = serie[serie.index >= limite]
        pagamentos = [
            {"data": idx.strftime("%Y-%m-%d"), "valor": float(val)}
            for idx, val in recentes.items()
            if float(val) > 0
        ]
    gravados = 0
    for item in pagamentos:
        try:
            db.salvar_dividendo(ticker, item["data"], float(item["valor"]))
            gravados += 1
        except Exception as exc:
            logger.warning("Falha ao gravar provento de %s: %s", ticker, exc)
    return gravados


def buscar_dados_completos(
    ticker: str,
    db=None,
    usar_cache: bool = True,
    incluir_fundamentos: bool = True,
) -> Dict:
    """Fonte de mercado. Dashboard usa incluir_fundamentos=False (sem scrape)."""
    ticker = ticker.upper().replace(".SA", "").strip()

    if usar_cache and db is not None:
        cached = db.get_cache(ticker, CACHE_MINUTES)
        if cached and "erro" not in cached:
            if incluir_fundamentos or cached.get("preco_atual") is not None:
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

    dy_calc = calcular_dy(ticker, dados.get("preco_atual"))
    if dy_calc:
        _registrar_meta(
            dados, "dy", dy_calc["dy_anual"], "Yahoo Finance (proventos 12m)", confianca="alta"
        )
        dados["dy_mensal"] = dy_calc["dy_mensal"]
        dados["total_dividendos_12m"] = dy_calc["total_dividendos_12m"]
        dados["pagamentos"] = dy_calc.get("pagamentos") or []
        if db is not None:
            sincronizar_proventos(db, ticker, dados["pagamentos"])
    else:
        _registrar_meta(
            dados,
            "dy",
            None,
            "Yahoo Finance (proventos 12m)",
            confianca="baixa",
            status="indisponivel",
        )

    if incluir_fundamentos:
        try:
            info = yf.Ticker(f"{ticker}.SA").info or {}
            dados["nome"] = info.get("longName") or info.get("shortName") or ticker
            dados["moeda"] = info.get("currency") or "BRL"
            if info.get("sector"):
                _registrar_meta(dados, "setor", info["sector"], "Yahoo Finance", confianca="baixa")
        except Exception as exc:
            logger.warning("Falha nos metadados Yahoo de %s: %s", ticker, exc)

        inv = _api.buscar_ativo(ticker)
        if "erro" not in inv:
            fontes.append("Investidor10")
            dados["nome"] = inv.get("nome") or dados["nome"]
            dados["url_investidor10"] = inv.get("url")
            for campo in CAMPOS_I10:
                valor = inv.get(campo)
                if valor is not None and valor != "":
                    _registrar_meta(dados, campo, valor, "Investidor10", confianca="media")
                elif dados.get(campo) is None and campo in (
                    "p_vp",
                    "patrimonio",
                    "vacancia",
                    "liquidez_diaria",
                    "cotistas",
                    "ultimo_rendimento",
                ):
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
                if divergencia is not None and indicador in dados.get("qualidade", {}):
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

        extras = consultar_fontes_extras(ticker)
        usadas = aplicar_fontes_extras(
            dados,
            extras,
            registrar=_registrar_meta,
            divergencia_pct=_divergencia_percentual,
            limite=LIMITE_DIVERGENCIA,
        )
        fontes.extend(usadas)

    dados["fonte"] = " + ".join(dict.fromkeys(fontes)) or "fontes indisponíveis"
    campos_ok = ("preco_atual", "dy", "p_vp", "patrimonio", "vacancia") if incluir_fundamentos else ("preco_atual", "dy")
    disponiveis = sum(dados.get(campo) is not None for campo in campos_ok)
    dados["status_geral"] = (
        "ok" if disponiveis == len(campos_ok) and not dados["divergencias"]
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
