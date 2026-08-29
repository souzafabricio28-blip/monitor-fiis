"""Alertas no WhatsApp (número 11 97367-4455). Sem Telegram."""

from __future__ import annotations

import os
import re
from datetime import datetime
from urllib.parse import quote_plus

import requests

NUMERO_PADRAO = "5511973674455"
CALLMEBOT = "https://api.callmebot.com/whatsapp.php"


def normalizar_telefone(valor: str | None) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if not digitos:
        return NUMERO_PADRAO
    if digitos.startswith("55") and len(digitos) >= 12:
        return digitos
    if len(digitos) == 11:
        return "55" + digitos
    if len(digitos) == 10:
        return "55" + digitos
    return digitos


def telefone_destino() -> str:
    return normalizar_telefone(os.environ.get("WHATSAPP_PHONE") or NUMERO_PADRAO)


def _apikey() -> str:
    return (os.environ.get("WHATSAPP_APIKEY") or os.environ.get("CALLMEBOT_APIKEY") or "").strip()


def whatsapp_configurado(db=None) -> bool:
    if not _apikey():
        return False
    if db is None:
        return True
    cfg = db.get_config("whatsapp") or {}
    if cfg.get("ativar") is False:
        return False
    return True


def _texto_simples(titulo: str, mensagem: str) -> str:
    bruto = f"{titulo}\n\n{mensagem}\n\n{datetime.now().strftime('%d/%m/%Y %H:%M')}"
    return re.sub(r"<[^>]+>", "", bruto).strip()


def enviar_mensagem(texto: str) -> bool:
    chave = _apikey()
    if not chave:
        return False
    phone = telefone_destino()
    url = f"{CALLMEBOT}?phone={phone}&text={quote_plus(texto[:1500])}&apikey={quote_plus(chave)}"
    try:
        resp = requests.get(url, timeout=25)
        return resp.status_code == 200 and "ERROR" not in (resp.text or "").upper()[:80]
    except requests.RequestException:
        return False


def enviar_alerta(titulo: str, mensagem: str, tipo: str = "info") -> bool:
    return enviar_mensagem(_texto_simples(titulo, mensagem))


class WhatsAppNotifier:
    def enviar_mensagem(self, mensagem: str) -> bool:
        return enviar_mensagem(mensagem)

    def enviar_alerta(self, titulo: str, mensagem: str, tipo: str = "info") -> bool:
        return enviar_alerta(titulo, mensagem, tipo)

    def testar_conexao(self) -> bool:
        return enviar_alerta("Monitor de FIIs", "Teste de alerta no WhatsApp.")


CHAVE_ALERTAS_WATCHLIST = "watchlist_alertas_enviados"


def _float_positivo(valor):
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if numero != numero or numero <= 0:
        return None
    return numero


def alvo_de_preco_atingido(preco, preco_alvo) -> bool:
    atual = _float_positivo(preco)
    alvo = _float_positivo(preco_alvo)
    if atual is None or alvo is None:
        return False
    return atual <= alvo


def _preco_watchlist(ticker: str, db, precos: dict | None):
    if precos is not None and ticker in precos:
        return _float_positivo(precos.get(ticker))
    cached = db.get_cache(ticker, 60) if db is not None else None
    if cached:
        preco = _float_positivo(cached.get("preco_atual") or cached.get("preco"))
        if preco is not None:
            return preco
    from market_data import buscar_cotacao

    cotacao = buscar_cotacao(ticker)
    if not cotacao:
        return None
    return _float_positivo(cotacao.get("preco_atual") or cotacao.get("preco"))


def verificar_alertas_watchlist(db, precos: dict | None = None, enviar: bool = True) -> dict:
    resultado = {
        "disparados": [],
        "enviados": [],
        "omitidos_dedup": [],
        "sem_preco": [],
        "whatsapp_ok": whatsapp_configurado(db),
    }
    watchlist = db.obter_watchlist()
    if watchlist is None or getattr(watchlist, "empty", True):
        return resultado

    estado = db.get_config(CHAVE_ALERTAS_WATCHLIST) or {}
    if not isinstance(estado, dict):
        estado = {}
    novo_estado = dict(estado)

    for _, row in watchlist.iterrows():
        ticker = str(row.get("ticker") or "").upper().replace(".SA", "").strip()
        alvo = _float_positivo(row.get("preco_alvo"))
        if not ticker or alvo is None:
            continue
        preco = _preco_watchlist(ticker, db, precos)
        if preco is None:
            resultado["sem_preco"].append(ticker)
            continue

        if not alvo_de_preco_atingido(preco, alvo):
            novo_estado.pop(ticker, None)
            continue

        item = {
            "ticker": ticker,
            "preco": preco,
            "preco_alvo": alvo,
        }
        resultado["disparados"].append(item)
        previa = estado.get(ticker) or {}
        mesmo_alvo = _float_positivo(previa.get("preco_alvo")) == alvo
        if mesmo_alvo:
            resultado["omitidos_dedup"].append(item)
            continue

        enviado = False
        if enviar and resultado["whatsapp_ok"]:
            enviado = enviar_alerta(
                f"Watchlist no alvo — {ticker}",
                (
                    f"Ativo: {ticker}\n"
                    f"Preço atual: R$ {preco:.2f}\n"
                    f"Alvo: R$ {alvo:.2f}\n"
                    f"Status: preço atingiu ou ficou abaixo do alerta"
                ),
                "compra",
            )
        resultado["enviados"].append({**item, "enviado": enviado})
        if enviado:
            novo_estado[ticker] = {
                "preco_alvo": alvo,
                "preco": preco,
                "enviado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    db.set_config(CHAVE_ALERTAS_WATCHLIST, novo_estado)
    return resultado
