"""
Sistema de notificações Telegram para FIIs
Envia alertas e relatórios via Telegram
"""

import requests
import json
from datetime import datetime


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
    """Função auxiliar para enviar alertas"""
    if config is None:
        config = {}
    
    token = config.get("telegram_token", "")
    chat_id = config.get("telegram_chat_id", "")
    
    if token and chat_id:
        notifier = TelegramNotifier(token, chat_id)
        return notifier.enviar_mensagem(mensagem)
    
    return False
