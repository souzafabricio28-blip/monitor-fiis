"""Vigia do Monitor de FIIs: saúde do site + carteira. IA opcional (chave de API)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

SITE_PADRAO = "https://monitor-fiis-6dk7.onrender.com"


def _agora() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")


def checar_saude(url: str | None = None, timeout: int = 20) -> dict:
    base = (url or os.environ.get("VIGIA_URL") or SITE_PADRAO).rstrip("/")
    health = f"{base}/_stcore/health"
    try:
        resp = requests.get(health, timeout=timeout, headers={"User-Agent": "monitor-fiis-vigia"})
        ok = resp.status_code == 200
        return {
            "ok": ok,
            "url": health,
            "status_http": resp.status_code,
            "detalhe": "no ar" if ok else f"HTTP {resp.status_code}",
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "url": health,
            "status_http": None,
            "detalhe": str(exc)[:200],
        }


def analisar_carteira_vigia(db) -> dict:
    from portfolio import analisar_carteira
    from queda_report import gatilhos_de_queda
    from whatsapp_notifier import verificar_alertas_watchlist

    analise = analisar_carteira(db)
    if "erro" in analise:
        return {
            "erro": analise["erro"],
            "posicoes": 0,
            "quedas": [],
            "watchlist": [],
            "proventos": 0.0,
            "investido": None,
            "patrimonio": None,
        }

    quedas = []
    for fii in analise.get("fiis") or []:
        g = gatilhos_de_queda(fii.get("preco_atual"), fii.get("preco_compra"))
        if g.get("atingiu"):
            quedas.append(
                {
                    "ticker": fii.get("ticker"),
                    "pct": g.get("pct"),
                }
            )
    wl = verificar_alertas_watchlist(db, enviar=False)
    return {
        "erro": None,
        "posicoes": len(analise.get("fiis") or []),
        "quedas": quedas,
        "watchlist": [i["ticker"] for i in (wl.get("disparados") or [])],
        "proventos": float(analise.get("proventos_registrados") or 0),
        "investido": analise.get("total_investido"),
        "patrimonio": analise.get("total_atual"),
        "sem_cotacao": analise.get("posicoes_sem_cotacao") or [],
    }


def montar_relatorio(saude: dict, carteira: dict) -> str:
    linhas = [f"Vigia Monitor de FIIs — {_agora()}"]
    if saude.get("ok"):
        linhas.append(f"Site: no ar ({saude.get('url')})")
    else:
        linhas.append(f"Site FORA: {saude.get('detalhe')} ({saude.get('url')})")

    if carteira.get("erro"):
        linhas.append(f"Carteira: {carteira['erro']}")
        return "\n".join(linhas)

    linhas.append(f"Posições: {carteira.get('posicoes', 0)}")
    inv = carteira.get("investido")
    pat = carteira.get("patrimonio")
    if inv is not None and pat is not None:
        linhas.append(f"Investido R$ {inv:,.2f} · Patrimônio R$ {pat:,.2f}")
    linhas.append(f"Proventos registados 12m: R$ {float(carteira.get('proventos') or 0):,.2f}")
    if carteira.get("proventos") == 0:
        linhas.append(
            "Proventos em zero: rode Dividendos → Sincronizar proventos se a corretora já pagou."
        )
    quedas = carteira.get("quedas") or []
    if quedas:
        nomes = ", ".join(f"{q['ticker']}" for q in quedas)
        linhas.append(f"Queda ≥10% vs compra: {nomes}")
    else:
        linhas.append("Nenhuma queda ≥10% vs compra.")
    wl = carteira.get("watchlist") or []
    if wl:
        linhas.append("Watchlist no alvo: " + ", ".join(wl))
    sem = carteira.get("sem_cotacao") or []
    if sem:
        linhas.append("Sem cotação: " + ", ".join(sem))
    return "\n".join(linhas)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELO_OPENROUTER = "openai/gpt-4o-mini"


def _parece_openrouter(chave: str) -> bool:
    return chave.startswith("sk-or-")


def _chave_llm() -> tuple[str, str, str] | None:
    openrouter = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    openai = (os.environ.get("OPENAI_API_KEY") or "").strip()
    groq = (os.environ.get("GROQ_API_KEY") or "").strip()
    if openrouter or _parece_openrouter(openai):
        token = openrouter or openai
        modelo = (
            os.environ.get("OPENROUTER_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or MODELO_OPENROUTER
        ).strip()
        return token, OPENROUTER_URL, modelo
    if groq:
        return groq, "https://api.groq.com/openai/v1/chat/completions", "llama-3.1-8b-instant"
    if openai:
        modelo = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
        return openai, "https://api.openai.com/v1/chat/completions", modelo
    return None


def tem_chave_ia() -> bool:
    return _chave_llm() is not None


def resumir_com_ia(relatorio: str) -> str | None:
    cred = _chave_llm()
    if not cred:
        return None
    token, url, modelo = cred
    corpo = {
        "model": modelo,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é o vigia do Monitor de FIIs. Responda em português, "
                    "curto, sem inventar número. Diga o que está ok, o que falhou "
                    "e a próxima ação. Não dê recomendação de compra."
                ),
            },
            {"role": "user", "content": relatorio},
        ],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if url == OPENROUTER_URL:
        headers["HTTP-Referer"] = (os.environ.get("VIGIA_URL") or SITE_PADRAO).rstrip("/")
        headers["X-Title"] = "Monitor de FIIs"
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=corpo,
            timeout=40,
        )
        resp.raise_for_status()
        texto = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
            or ""
        ).strip()
        return texto or None
    except Exception:
        return None


def enviar_whatsapp_vigia(texto: str, db=None) -> bool:
    from whatsapp_notifier import aplicar_segredo_whatsapp, enviar_alerta, whatsapp_configurado

    aplicar_segredo_whatsapp(db)
    if not whatsapp_configurado(db):
        return False
    return enviar_alerta("Vigia do app", texto, tipo="aviso")


def rodar_vigia(db=None, enviar: bool = True, url: str | None = None) -> dict:
    from db import DatabaseManager

    saude = checar_saude(url)
    banco = None
    try:
        banco = db or DatabaseManager()
        carteira = analisar_carteira_vigia(banco)
    except Exception as exc:
        carteira = {
            "erro": str(exc)[:200],
            "posicoes": 0,
            "quedas": [],
            "watchlist": [],
            "proventos": 0.0,
        }
    relatorio = montar_relatorio(saude, carteira)
    ia = resumir_com_ia(relatorio)
    texto = f"{ia}\n\n---\n{relatorio}" if ia else relatorio
    whatsapp = False
    if enviar:
        whatsapp = enviar_whatsapp_vigia(texto, banco)
    return {
        "saude": saude,
        "carteira": carteira,
        "relatorio": relatorio,
        "ia": ia,
        "texto": texto,
        "whatsapp": whatsapp,
        "usou_ia": bool(ia),
        "coletado_em": _agora(),
    }


def main() -> int:
    resultado = rodar_vigia()
    print(resultado["texto"])
    if not resultado["saude"].get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
