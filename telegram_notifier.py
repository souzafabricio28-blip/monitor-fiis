"""
Sistema de notificações Telegram para FIIs
Envia alertas e relatórios via Telegram
"""

from __future__ import annotations

import os
from datetime import datetime

import requests


class TelegramNotifier:
    """Gerencia notificações via Telegram"""
    
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def configurar(self, token: str, chat_id: str):
        """Configura as credenciais do Telegram"""
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def enviar_mensagem(self, mensagem: str) -> bool:
        """Envia uma mensagem de texto"""
        if not self.token or not self.chat_id:
            print("⚠️ Telegram não configurado!")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": mensagem,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem: {e}")
            return False
    
    def enviar_alerta(self, titulo: str, mensagem: str, tipo: str = "info"):
        """Envia um alerta formatado"""
        emojis = {
            "info": "ℹ️",
            "sucesso": "✅",
            "aviso": "⚠️",
            "erro": "❌",
            "dividendo": "💰",
            "compra": "📈",
            "venda": "📉"
        }
        
        emoji = emojis.get(tipo, "ℹ️")
        
        texto = f"""
{emoji} <b>{titulo}</b>

{mensagem}

📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        return self.enviar_mensagem(texto)
    
    def enviar_dividendo(self, ticker: str, valor: float, data: str):
        """Envia notificação de dividendo"""
        titulo = f"Dividendo Recebido - {ticker}"
        mensagem = f"""
<b>FII:</b> {ticker}
<b>Valor por cota:</b> R$ {valor:.4f}
<b>Data:</b> {data}
<b>Status:</b> Creditado na conta
        """
        
        return self.enviar_alerta(titulo, mensagem, "dividendo")
    
    def enviar_alerta_dy(self, ticker: str, dy_atual: float, dy_anterior: float):
        """Envia alerta de mudança no DY"""
        variacao = dy_atual - dy_anterior
        tipo = "alta" if variacao > 0 else "baixa"
        
        titulo = f"Alerta DY - {ticker}"
        mensagem = f"""
<b>FII:</b> {ticker}
<b>DY Anterior:</b> {dy_anterior:.2f}%
<b>DY Atual:</b> {dy_atual:.2f}%
<b>Variação:</b> {variacao:+.2f}%
        """
        
        return self.enviar_alerta(titulo, mensagem, "aviso" if tipo == "baixa" else "sucesso")
    
    def enviar_relatorio_diario(self, dados: dict):
        """Envia relatório diário da carteira"""
        titulo = "📊 Relatório Diário - Carteira FIIs"
        
        mensagem = f"""
<b>Total Investido:</b> R$ {dados.get('total_investido', 0):.2f}
<b>Valor Atual:</b> R$ {dados.get('valor_atual', 0):.2f}
<b>Lucro/Prejuízo:</b> R$ {dados.get('lucro', 0):.2f}
<b>Rendimento Mensal:</b> R$ {dados.get('rendimento_mensal', 0):.2f}

<b>FIIs na Carteira:</b>
"""
        
        for fii in dados.get('fiis', []):
            mensagem += f"\n• {fii['ticker']}: {fii['quantidade']} cotas"
        
        return self.enviar_alerta(titulo, mensagem, "info")
    
    def enviar_oportunidade(self, ticker: str, preco: float, dy: float, motivo: str):
        """Envia alerta de oportunidade"""
        titulo = f"🎯 Oportunidade - {ticker}"
        mensagem = f"""
<b>FII:</b> {ticker}
<b>Preço Atual:</b> R$ {preco:.2f}
<b>DY:</b> {dy:.2f}%
<b>Motivo:</b> {motivo}
        """
        
        return self.enviar_alerta(titulo, mensagem, "compra")
    
    def testar_conexao(self) -> bool:
        """Testa a conexão com o Telegram"""
        if not self.token:
            return False
        
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            return response.status_code == 200
        except:
            return False


# Função para usar no fii_monitor.py
def enviar_alerta_telegram(mensagem: str, config: dict = None):
    """Envia usando somente segredos do ambiente; config legado é ignorado."""
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    
    if token and chat_id:
        notifier = TelegramNotifier(token, chat_id)
        return notifier.enviar_mensagem(mensagem)
    
    return False


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
    """True só quando preço e alvo existem e o preço caiu até o alvo."""
    atual = _float_positivo(preco)
    alvo = _float_positivo(preco_alvo)
    if atual is None or alvo is None:
        return False
    return atual <= alvo


def telegram_configurado(db=None) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    if db is None:
        return True
    cfg = db.get_config("telegram") or {}
    if cfg.get("ativar") is False:
        return False
    return True


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
    """Dispara alerta de preço da watchlist sem gravar token no banco.

    Deduplica pelo par ticker+alvo: só reenvia se o preço subir acima do alvo
    e depois voltar a atingi-lo, ou se o alvo mudar.
    """
    resultado = {
        "disparados": [],
        "enviados": [],
        "omitidos_dedup": [],
        "sem_preco": [],
        "telegram_ok": telegram_configurado(db),
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
        if enviar and resultado["telegram_ok"]:
            notifier = TelegramNotifier(
                os.environ.get("TELEGRAM_TOKEN", ""),
                os.environ.get("TELEGRAM_CHAT_ID", ""),
            )
            enviado = bool(
                notifier.enviar_alerta(
                    f"Watchlist no alvo — {ticker}",
                    (
                        f"<b>FII:</b> {ticker}\n"
                        f"<b>Preço atual:</b> R$ {preco:.2f}\n"
                        f"<b>Alvo:</b> R$ {alvo:.2f}\n"
                        f"<b>Status:</b> preço atingiu ou ficou abaixo do alerta"
                    ),
                    "compra",
                )
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
