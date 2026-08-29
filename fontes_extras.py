"""Fontes públicas extras (além de Yahoo e Investidor10).

Cada fonte devolve o mesmo formato. Valor ausente permanece None (N/D), nunca 0.
Falhas de rede não derrubam as demais.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Callable, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from investidor10 import extrair_inteiro_br, extrair_percentual, extrair_valor_br, extrair_valor_compacto
from lista_gestor import TICKERS_ACAO_MESMO_COM_11

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

TIMEOUT = 8


def ticker_limpo(ticker: str) -> str:
    return (ticker or "").upper().replace(".SA", "").strip()


def eh_fii(ticker: str) -> bool:
    t = ticker_limpo(ticker)
    if t in TICKERS_ACAO_MESMO_COM_11:
        return False
    return t.endswith("11")


def _get(url: str, *, accept_json: bool = False) -> requests.Response:
    headers = dict(HEADERS)
    if accept_json:
        headers["Accept"] = "application/json"
    return requests.get(url, headers=headers, timeout=TIMEOUT)


def _vazio(fonte: str, url: str = "", erro: str | None = None) -> dict:
    return {
        "fonte": fonte,
        "url": url,
        "preco": None,
        "dy": None,
        "p_vp": None,
        "p_l": None,
        "vacancia": None,
        "patrimonio": None,
        "setor": None,
        "liquidez_diaria": None,
        "ultimo_rendimento": None,
        "vp_cota": None,
        "erro": erro,
    }


def _tabela_rotulada(html: str) -> str:
    texto = re.sub(r"<[^>]+>", "|", html or "")
    texto = texto.replace("&nbsp;", " ").replace("?", "")
    return re.sub(r"\|+", "|", texto)


def _valor_apos(texto: str, rotulo: str) -> Optional[float]:
    partes = [p.strip() for p in (texto or "").split("|")]
    alvo = rotulo.lower().rstrip(".")
    for i, parte in enumerate(partes):
        if parte.lower().rstrip(".") != alvo:
            continue
        for bruto in partes[i + 1 :]:
            if not bruto or bruto in {".", "-", "?"}:
                continue
            if "%" in bruto or "yield" in rotulo.lower():
                return extrair_percentual(bruto)
            if "," not in bruto and bruto.count(".") >= 1 and bruto.replace(".", "").isdigit():
                inteiro = extrair_inteiro_br(bruto)
                return float(inteiro) if inteiro is not None else None
            return extrair_valor_br(bruto)
    return None


def parse_fundamentus(html: str) -> dict:
    """Cotação, P/VP, DY, P/L e setor da página pública do Fundamentus."""
    out = _vazio("Fundamentus")
    if not html:
        out["erro"] = "vazio"
        return out
    texto = _tabela_rotulada(html)
    out["preco"] = _valor_apos(texto, "Cotação")
    out["p_vp"] = _valor_apos(texto, "P/VP")
    out["dy"] = _valor_apos(texto, "Div. Yield")
    out["p_l"] = _valor_apos(texto, "P/L")
    out["liquidez_diaria"] = _valor_apos(texto, "Vol $ méd (2m)")
    out["patrimonio"] = (
        _valor_apos(texto, "Patrim. Líq")
        or _valor_apos(texto, "Patrim. Liq")
        or _valor_apos(texto, "Patrim. Líq.")
    )
    if out["patrimonio"] is None:
        m_pl = re.search(r"Patrim\. L\w+\|([^|]+)", texto, re.I)
        if m_pl:
            bruto = m_pl.group(1).strip()
            if bruto.replace(".", "").isdigit():
                out["patrimonio"] = float(bruto.replace(".", ""))
            else:
                out["patrimonio"] = extrair_valor_br(bruto)
    setor = None
    partes = [p.strip() for p in texto.split("|")]
    for i, parte in enumerate(partes):
        if parte in {"Setor", "Segmento"}:
            for cand in partes[i + 1 :]:
                if cand and cand not in {".", "-", "?"}:
                    setor = cand
                    break
        if setor:
            break
    if setor:
        out["setor"] = setor
    return out


def buscar_fundamentus(ticker: str) -> dict:
    t = ticker_limpo(ticker)
    url = f"https://www.fundamentus.com.br/detalhes.php?papel={quote(t)}"
    out = _vazio("Fundamentus", url)
    try:
        resp = _get(url)
        if resp.status_code != 200:
            out["erro"] = f"HTTP {resp.status_code}"
            return out
        html = resp.content.decode("latin-1", errors="replace")
        parsed = parse_fundamentus(html)
        parsed["url"] = url
        if parsed.get("preco") is None and parsed.get("p_vp") is None:
            parsed["erro"] = "sem indicadores"
        return parsed
    except requests.RequestException as exc:
        out["erro"] = str(exc)[:160]
        return out


def parse_fundsexplorer(html: str) -> dict:
    """Cotação, DY, P/VP, VP/cota, liquidez e rendimento da página do fundo."""
    out = _vazio("Funds Explorer")
    if not html:
        out["erro"] = "vazio"
        return out
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one(".quotation__grid__box")
    if box:
        texto_box = box.get_text(" ", strip=True)
        # A caixa live é "R$ 9,30 Cotação atual 9,24 0,65%" — o 1º R$ NN,NN é o preço.
        m_rs = re.search(r"R\$\s*([\d.]*\d,\d{2})", texto_box)
        out["preco"] = extrair_valor_br(m_rs.group(1) if m_rs else texto_box)
    bloco = soup.select_one("[class*='indicators']")
    texto = bloco.get_text("|", strip=True) if bloco else soup.get_text("|", strip=True)
    texto = re.sub(r"\s*\|\s*", "|", texto)
    m_dy = re.search(r"Dividend Yield\|([\d.,]+)", texto, re.I)
    if m_dy:
        out["dy"] = extrair_percentual(m_dy.group(1))
    m_pvp = re.search(r"P/VP\|([\d.,]+)", texto, re.I)
    if m_pvp:
        out["p_vp"] = extrair_valor_br(m_pvp.group(1))
    m_vp = re.search(r"Valor Patrimonial\|R\$\|([\d.,]+)", texto, re.I)
    if m_vp:
        out["vp_cota"] = extrair_valor_br(m_vp.group(1))
    m_pl = re.search(r"Patrimônio Líquido\|R\$\|([^|]+)", texto, re.I)
    if m_pl:
        out["patrimonio"] = extrair_valor_compacto(m_pl.group(1))
    m_liq = re.search(r"Liquidez Média Diária\|([^|]+)", texto, re.I)
    if m_liq:
        out["liquidez_diaria"] = extrair_valor_compacto(m_liq.group(1))
    m_rend = re.search(r"Último Rendimento\|R\$\|([\d.,]+)", texto, re.I)
    if m_rend:
        out["ultimo_rendimento"] = extrair_valor_br(m_rend.group(1))
    m_vac = re.search(r'"vacancia"\s*:\s*"?([\d.,]+)"?', html, re.I)
    if m_vac and m_vac.group(1).strip():
        out["vacancia"] = extrair_percentual(m_vac.group(1))
    return out


def buscar_fundsexplorer(ticker: str) -> dict:
    t = ticker_limpo(ticker)
    url = f"https://www.fundsexplorer.com.br/funds/{quote(t.lower())}"
    out = _vazio("Funds Explorer", url)
    if not eh_fii(t):
        out["erro"] = "somente FII"
        return out
    try:
        resp = _get(url)
        if resp.status_code != 200:
            out["erro"] = f"HTTP {resp.status_code}"
            return out
        parsed = parse_fundsexplorer(resp.text)
        parsed["url"] = url
        return parsed
    except requests.RequestException as exc:
        out["erro"] = str(exc)[:160]
        return out


def parse_brapi(payload: dict) -> dict:
    out = _vazio("Brapi")
    if not payload or payload.get("error"):
        out["erro"] = str(payload.get("message") or "erro")
        return out
    item = (payload.get("results") or [None])[0] or {}
    preco = item.get("regularMarketPrice")
    try:
        out["preco"] = float(preco) if preco is not None else None
        if out["preco"] is not None and out["preco"] <= 0:
            out["preco"] = None
    except (TypeError, ValueError):
        out["preco"] = None
    pe = item.get("priceEarnings")
    try:
        out["p_l"] = float(pe) if pe not in (None, 0) else None
    except (TypeError, ValueError):
        out["p_l"] = None
    vol = item.get("regularMarketVolume")
    try:
        out["liquidez_diaria"] = float(vol) if vol else None
    except (TypeError, ValueError):
        out["liquidez_diaria"] = None
    out["setor"] = item.get("longName") or item.get("shortName")
    return out


def buscar_brapi(ticker: str) -> dict:
    t = ticker_limpo(ticker)
    token = (os.environ.get("BRAPI_TOKEN") or "").strip()
    url = f"https://brapi.dev/api/quote/{quote(t)}"
    if token:
        url += f"?token={quote(token)}"
    out = _vazio("Brapi", url.split("?")[0])
    try:
        resp = _get(url, accept_json=True)
        try:
            payload = resp.json()
        except ValueError:
            out["erro"] = "json inválido"
            return out
        if resp.status_code != 200:
            out["erro"] = payload.get("message") or f"HTTP {resp.status_code}"
            return out
        parsed = parse_brapi(payload)
        parsed["url"] = out["url"]
        return parsed
    except requests.RequestException as exc:
        out["erro"] = str(exc)[:160]
        return out


def parse_maisretorno_next(html: str) -> dict:
    out = _vazio("Mais Retorno")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "", re.S)
    if not m:
        out["erro"] = "sem NEXT_DATA"
        return out
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        out["erro"] = "NEXT_DATA inválido"
        return out
    props = (data.get("props") or {}).get("pageProps") or {}
    headers = props.get("headers") or {}
    out["setor"] = (
        headers.get("actuation_segment")
        or headers.get("actuation_sector")
        or None
    )
    if out["setor"] in {"-", "", None}:
        out["setor"] = None
    cap = headers.get("mkt_cap")
    try:
        out["patrimonio"] = float(cap) if cap else None
        if out["patrimonio"] is not None and out["patrimonio"] <= 0:
            out["patrimonio"] = None
    except (TypeError, ValueError):
        out["patrimonio"] = None
    return out


def buscar_maisretorno(ticker: str) -> dict:
    t = ticker_limpo(ticker)
    url = f"https://maisretorno.com/fii/{quote(t.lower())}"
    out = _vazio("Mais Retorno", url)
    if not eh_fii(t):
        out["erro"] = "somente FII"
        return out
    try:
        resp = _get(url)
        if resp.status_code != 200:
            out["erro"] = f"HTTP {resp.status_code}"
            return out
        parsed = parse_maisretorno_next(resp.text)
        parsed["url"] = url
        return parsed
    except requests.RequestException as exc:
        out["erro"] = str(exc)[:160]
        return out


def parse_google_finance(html: str) -> dict:
    out = _vazio("Google Finance")
    if not html:
        out["erro"] = "vazio"
        return out
    m = re.search(r'data-last-price="([\d.]+)"', html)
    if m:
        try:
            valor = float(m.group(1))
            out["preco"] = valor if valor > 0 else None
        except ValueError:
            pass
    if out["preco"] is None:
        soup = BeautifulSoup(html, "html.parser")
        el = soup.select_one(".YMlKec.fxKbKc, div.YMlKec")
        if el:
            out["preco"] = extrair_valor_br(el.get_text(" ", strip=True))
    if out["preco"] is None:
        out["erro"] = "preço não encontrado"
    return out


def buscar_google_finance(ticker: str) -> dict:
    t = ticker_limpo(ticker)
    url = f"https://www.google.com/finance/quote/{quote(t)}:BVMF?hl=pt-BR"
    out = _vazio("Google Finance", url)
    try:
        resp = _get(url)
        if resp.status_code != 200:
            out["erro"] = f"HTTP {resp.status_code}"
            return out
        parsed = parse_google_finance(resp.text)
        parsed["url"] = url
        return parsed
    except requests.RequestException as exc:
        out["erro"] = str(exc)[:160]
        return out


_PTAX_CACHE: dict = {"ts": 0.0, "dados": None}
_PTAX_TTL_S = 30 * 60


def buscar_ptax(*, forcar: bool = False) -> dict:
    """Dólar PTAX (Banco Central). Cache de 30 min — não precisa a cada ticker."""
    agora = time.time()
    cached = _PTAX_CACHE.get("dados")
    if (
        not forcar
        and isinstance(cached, dict)
        and cached.get("usd_brl") is not None
        and agora - float(_PTAX_CACHE["ts"]) < _PTAX_TTL_S
    ):
        return dict(cached)
    fim = datetime.now()
    ini = fim - timedelta(days=7)
    d1 = ini.strftime("%m-%d-%Y")
    d2 = fim.strftime("%m-%d-%Y")
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoDolarPeriodo(dataInicial=@d1,dataFinalCotacao=@d2)"
        f"?@d1='{d1}'&@d2='{d2}'&$top=1&$orderby=dataHoraCotacao%20desc&$format=json"
    )
    out = {"fonte": "Banco Central (PTAX)", "url": url, "usd_brl": None, "erro": None}
    try:
        resp = _get(url, accept_json=True)
        if resp.status_code != 200:
            out["erro"] = f"HTTP {resp.status_code}"
            return out
        valor = ((resp.json() or {}).get("value") or [{}])[0]
        venda = valor.get("cotacaoVenda")
        out["usd_brl"] = float(venda) if venda else None
        if out["usd_brl"] is None:
            out["erro"] = "sem cotação"
        else:
            _PTAX_CACHE["ts"] = agora
            _PTAX_CACHE["dados"] = dict(out)
        return out
    except (requests.RequestException, ValueError, TypeError) as exc:
        out["erro"] = str(exc)[:160]
        return out


def _chamar(fn: Callable[[str], dict], ticker: str) -> dict:
    try:
        return fn(ticker)
    except Exception as exc:
        logger.warning("Fonte extra falhou (%s): %s", getattr(fn, "__name__", fn), exc)
        return _vazio(getattr(fn, "__name__", "fonte"), erro=str(exc)[:160])


# Google Finance fica de fora do pool: a página é JS e quase sempre
# devolve vazio, só atrasando o Indicadores em ~8 s. O parser permanece
# para testes e uso pontual.
FONTES_PARALELAS: tuple[Callable[[str], dict], ...] = (
    buscar_fundamentus,
    buscar_fundsexplorer,
    buscar_brapi,
    buscar_maisretorno,
)


def consultar_fontes_extras(ticker: str) -> List[dict]:
    """Dispara as fontes em paralelo. PTAX entra no fim (macro, com cache)."""
    t = ticker_limpo(ticker)
    resultados: List[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futuros = {pool.submit(_chamar, fn, t): fn for fn in FONTES_PARALELAS}
        for fut in as_completed(futuros):
            resultados.append(fut.result())
    ordem = {
        "Fundamentus": 0,
        "Funds Explorer": 1,
        "Brapi": 2,
        "Mais Retorno": 3,
    }
    resultados.sort(key=lambda d: ordem.get(d.get("fonte") or "", 9))
    ptax = buscar_ptax()
    resultados.append(ptax)
    return resultados


CAMPOS_PREENCHER = (
    ("preco", "preco_atual"),
    ("dy", "dy"),
    ("p_vp", "p_vp"),
    ("p_l", "p_l"),
    ("vacancia", "vacancia"),
    ("patrimonio", "patrimonio"),
    ("setor", "setor"),
    ("liquidez_diaria", "liquidez_diaria"),
    ("ultimo_rendimento", "ultimo_rendimento"),
    ("vp_cota", "vp_cota"),
)


def _valor_da_fonte(dados: dict, campo: str, nome_fonte: str):
    meta = (dados.get("qualidade") or {}).get(campo) or {}
    fonte = str(meta.get("fonte") or "")
    if fonte == nome_fonte or fonte.startswith(nome_fonte):
        return dados.get(campo)
    extra = meta.get(f"valor_{nome_fonte}")
    if extra not in (None, ""):
        return extra
    return None


def montar_comparativo_fontes(dados: dict, extras: List[dict]) -> List[dict]:
    """Uma linha por fonte com preço, DY e P/VP originais (N/D não vira 0)."""
    linhas: List[dict] = [
        {
            "fonte": "Yahoo Finance",
            "preco": _valor_da_fonte(dados, "preco_atual", "Yahoo Finance"),
            "dy": _valor_da_fonte(dados, "dy", "Yahoo Finance"),
            "p_vp": _valor_da_fonte(dados, "p_vp", "Yahoo Finance"),
        }
    ]
    i10 = {
        "fonte": "Investidor10",
        "preco": _valor_da_fonte(dados, "preco_atual", "Investidor10"),
        "dy": dados.get("dy_investidor10")
        if dados.get("dy_investidor10") is not None
        else _valor_da_fonte(dados, "dy", "Investidor10"),
        "p_vp": _valor_da_fonte(dados, "p_vp", "Investidor10"),
    }
    if any(i10[k] is not None for k in ("preco", "dy", "p_vp")):
        linhas.append(i10)
    for extra in extras:
        if not isinstance(extra, dict) or "usd_brl" in extra:
            continue
        linhas.append(
            {
                "fonte": extra.get("fonte") or "fonte",
                "preco": extra.get("preco"),
                "dy": extra.get("dy"),
                "p_vp": extra.get("p_vp"),
            }
        )
    return linhas


def aplicar_fontes_extras(
    dados: dict,
    extras: List[dict],
    *,
    registrar,
    divergencia_pct,
    limite: float,
) -> List[str]:
    """Preenche só o que ainda é N/D. Divergência em preço, DY e P/VP fica na auditoria."""
    usadas: List[str] = []
    consultadas: List[dict] = []
    for extra in extras:
        nome = extra.get("fonte") or "fonte"
        url = extra.get("url") or ""
        if "usd_brl" in extra:
            consultadas.append(
                {"fonte": nome, "ok": extra.get("usd_brl") is not None, "url": url, "erro": extra.get("erro")}
            )
            if extra.get("usd_brl") is not None:
                dados.setdefault("macro", {})["usd_brl"] = extra["usd_brl"]
                dados["macro"]["fonte_usd"] = nome
                usadas.append(nome)
            continue
        tem_dado = any(extra.get(origem) not in (None, "") for origem, _ in CAMPOS_PREENCHER)
        consultadas.append(
            {"fonte": nome, "ok": tem_dado, "url": url, "erro": extra.get("erro")}
        )
        if not tem_dado:
            continue
        usadas.append(nome)
        for origem, destino in CAMPOS_PREENCHER:
            valor = extra.get(origem)
            if valor in (None, ""):
                continue
            atual = dados.get(destino)
            if atual is None:
                registrar(dados, destino, valor, nome, confianca="media")
                if destino == "preco_atual":
                    dados["preco"] = valor
                continue
            if destino not in {"preco_atual", "dy", "p_vp"}:
                continue
            div = divergencia_pct(atual, valor)
            qualidade = dados.setdefault("qualidade", {}).setdefault(destino, {})
            qualidade[f"valor_{nome}"] = valor
            if div is not None and div > limite:
                qualidade["status"] = "divergente"
                qualidade["confianca"] = "baixa"
                qualidade["divergencia_pct"] = round(div, 2)
                dados.setdefault("divergencias", []).append(
                    f"{destino}: {nome} diverge {div:.1f}%"
                )
    dados["fontes_consultadas"] = consultadas
    dados["comparativo_fontes"] = montar_comparativo_fontes(dados, extras)
    return usadas
