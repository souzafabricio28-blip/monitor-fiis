# -*- coding: utf-8 -*-
"""
Monitor de FIIs - Fundos Imobiliários Brasileiros
===================================================
Script completo para monitorar sua carteira de FIIs.

Funcionalidades:
- Buscar cotações em tempo real via Yahoo Finance
- Calcular rendimentos e dividend yield
- Gerar relatórios em HTML
- Enviar alertas por email
- Dashboard gráfico
- Armazenamento local em SQLite
- Execução automática diária

Autor: Seu Nome
Versão: 1.0.0
"""

import os
import sys
import json
import sqlite3
import smtplib
import logging
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

try:
    import yfinance as yf
    import pandas as pd
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from jinja2 import Template
    from tabulate import tabulate
except ImportError as e:
    print(f"Erro: Biblioteca não encontrada. Execute: pip install -r requirements.txt")
    print(f"Biblioteca faltando: {e}")
    sys.exit(1)

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fii_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Gerencia o banco de dados SQLite para armazenar histórico."""
    
    def __init__(self, db_path: str = "fii_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Inicializa o banco de dados com as tabelas necessárias."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de cotações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cotacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                data TEXT NOT NULL,
                preco REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, data)
            )
        ''')
        
        # Tabela de dividendos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dividendos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                data_pagamento TEXT NOT NULL,
                valor_por_cota REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, data_pagamento)
            )
        ''')
        
        # Tabela de carteira
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS carteira (
                ticker TEXT PRIMARY KEY,
                quantidade INTEGER NOT NULL,
                preco_compra REAL NOT NULL,
                data_compra TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Banco de dados inicializado com sucesso")
    
    def salvar_cotacao(self, ticker: str, data: str, preco: float):
        """Salva uma cotação no banco de dados."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT OR REPLACE INTO cotacoes (ticker, data, preco) VALUES (?, ?, ?)',
                (ticker, data, preco)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar cotação: {e}")
        finally:
            conn.close()
    
    def obter_cotacoes(self, ticker: str, dias: int = 30) -> pd.DataFrame:
        """Obtém cotações históricas de um FII."""
        conn = sqlite3.connect(self.db_path)
        query = '''
            SELECT data, preco FROM cotacoes 
            WHERE ticker = ? AND data >= date('now', ?)
            ORDER BY data
        '''
        df = pd.read_sql_query(query, conn, params=(ticker, f'-{dias} days'))
        conn.close()
        return df
    
    def salvar_dividendo(self, ticker: str, data_pagamento: str, valor: float):
        """Salva um dividend no banco de dados."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT OR REPLACE INTO dividendos (ticker, data_pagamento, valor_por_cota) VALUES (?, ?, ?)',
                (ticker, data_pagamento, valor)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar dividendo: {e}")
        finally:
            conn.close()
    
    def obter_dividendos(self, ticker: str = None, meses: int = 12) -> pd.DataFrame:
        """Obtém dividendos pagos."""
        conn = sqlite3.connect(self.db_path)
        if ticker:
            query = '''
                SELECT * FROM dividendos 
                WHERE ticker = ? AND data_pagamento >= date('now', ?)
                ORDER BY data_pagamento DESC
            '''
            df = pd.read_sql_query(query, conn, params=(ticker, f'-{meses} months'))
        else:
            query = '''
                SELECT * FROM dividendos 
                WHERE data_pagamento >= date('now', ?)
                ORDER BY data_pagamento DESC
            '''
            df = pd.read_sql_query(query, conn, params=(f'-{meses} months',))
        conn.close()
        return df
    
    def atualizar_carteira(self, ticker: str, quantidade: int, preco_compra: float):
        """Atualiza a carteira de investimentos."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        data_compra = datetime.now().strftime('%Y-%m-%d')
        try:
            cursor.execute(
                '''INSERT OR REPLACE INTO carteira 
                   (ticker, quantidade, preco_compra, data_compra, updated_at) 
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)''',
                (ticker, quantidade, preco_compra, data_compra)
            )
            conn.commit()
            logger.info(f"Carteira atualizada: {ticker} - {quantidade} cotas @ R$ {preco_compra:.2f}")
        except Exception as e:
            logger.error(f"Erro ao atualizar carteira: {e}")
        finally:
            conn.close()
    
    def obter_carteira(self) -> pd.DataFrame:
        """Obtém a carteira atual."""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query('SELECT * FROM carteira', conn)
        conn.close()
        return df
    
    def remover_da_carteira(self, ticker: str):
        """Remove um FII da carteira."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM carteira WHERE ticker = ?', (ticker,))
            conn.commit()
            logger.info(f"{ticker} removido da carteira")
        except Exception as e:
            logger.error(f"Erro ao remover da carteira: {e}")
        finally:
            conn.close()


class Investidor10API:
    """Classe para integrar dados do Investidor10 via Web Scraping"""
    
    def __init__(self):
        self.base_url = "https://investidor10.com.br/fiis/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def buscar_fii(self, ticker: str) -> Dict:
        """
        Busca dados de um FII no Investidor10
        
        Args:
            ticker: Código do FII (ex: MXRF11)
            
        Returns:
            dict com os dados do FII
        """
        import re
        
        ticker = ticker.upper().replace(".SA", "")
        url = f"{self.base_url}{ticker.lower()}/"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            texto_completo = soup.get_text()
            
            dados = {
                "ticker": ticker,
                "fonte": "Investidor10",
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "url": url
            }
            
            # Buscar nome do fundo (h1)
            h1 = soup.find("h1")
            if h1:
                dados["nome"] = h1.get_text(strip=True)
            
            # Buscar preco usando regex
            preco_match = re.search(rf"{ticker}\s*Cota..o.*?R\$\s*([\d.,]+)", texto_completo, re.IGNORECASE | re.DOTALL)
            if preco_match:
                dados["preco"] = self._extrair_valor(preco_match.group(1))
            
            # Buscar DY (Dividend Yield)
            dy_match = re.search(rf"{ticker}\s*DY\s*\(12M\)\s*:\s*([\d.,]+)%", texto_completo, re.IGNORECASE)
            if dy_match:
                dados["dy"] = self._extrair_percentual(dy_match.group(1))
            
            # Buscar P/VP
            pvp_match = re.search(rf"{ticker}\s*P/VP\s*:\s*([\d.,]+)", texto_completo, re.IGNORECASE)
            if pvp_match:
                dados["p_vp"] = self._extrair_valor(pvp_match.group(1))
            
            # Buscar Patrimonio (procurar "patrimonio de R$ X Bilhoes" ou "valor patrimonial R$ X")
            pl_match = re.search(r"patrim.nio\s+de\s+R\$\s*([\d.,]+)\s*(Bilh|Milh)", texto_completo, re.IGNORECASE)
            if pl_match:
                valor = self._extrair_valor(pl_match.group(1))
                unidade = pl_match.group(2).lower()
                if "bilh" in unidade:
                    valor *= 1000000000  # Bilhoes
                elif "milh" in unidade:
                    valor *= 1000000  # Milhoes
                dados["patrimonio"] = valor
            else:
                # Tentar otra forma: "VALOR PATRIMONIAL R$ X"
                pl_match2 = re.search(r"valor patrimonial\s+R\$\s*([\d.,]+)\s*(B|K|M|Bilh|Milh)?", texto_completo, re.IGNORECASE)
                if pl_match2:
                    dados["patrimonio"] = self._extrair_valor(pl_match2.group(1))
            
            # Buscar vacancia
            vac_match = re.search(r"vac.ncia.*?([\d.,]+)%", texto_completo, re.IGNORECASE)
            if vac_match:
                dados["vacancia"] = self._extrair_percentual(vac_match.group(1))
            
            # Buscar setor/segmento (procurar "do segmento X" que esta na descricao do fundo)
            setor_match = re.search(r"do segmento\s+(Híbrido|Papel|Tijolo|Logístico|FOF)", texto_completo, re.IGNORECASE)
            if setor_match:
                dados["setor"] = setor_match.group(1)
            
            # Buscar tipo do fundo (Fundo de Papel, Fundo de Tijolo, etc)
            tipo_match = re.search(r"tipo\s+(Fundo de\s+(Papel|Tijolo|Logístico|Híbrido))", texto_completo, re.IGNORECASE)
            if tipo_match:
                dados["tipo"] = tipo_match.group(1)
            
            return dados
            
        except Exception as e:
            return {"ticker": ticker, "erro": str(e)}
    
    def _extrair_valor(self, texto: str) -> float:
        """Extrai valor numerico de texto"""
        try:
            texto = texto.replace("R$", "").strip()
            texto = texto.replace(".", "").replace(",", ".")
            texto = "".join(c for c in texto if c.isdigit() or c in ".-")
            return float(texto) if texto else 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def _extrair_percentual(self, texto: str) -> float:
        """Extrai percentual de texto"""
        try:
            texto = texto.replace("%", "").replace(",", ".").strip()
            return float(texto) if texto else 0.0
        except (ValueError, TypeError):
            return 0.0


class FiiDataFetcher:
    """Busca dados de FIIs via Yahoo Finance."""
    
    @staticmethod
    def buscar_cotacao_atual(ticker: str) -> Optional[Dict]:
        """Busca a cotação atual de um FII."""
        try:
            # Adiciona .SA para FIIs brasileiros no Yahoo Finance
            symbol = f"{ticker}.SA"
            fii = yf.Ticker(symbol)
            
            # Obtém informações básicas
            info = fii.info
            
            # Obtém preço atual
            historico = fii.history(period="1d")
            if historico.empty:
                logger.warning(f"Não foi possível obter cotação para {ticker}")
                return None
            
            preco_atual = historico['Close'].iloc[-1]
            variacao_dia = historico['Close'].iloc[-1] - historico['Open'].iloc[0]
            variacao_pct = (variacao_dia / historico['Open'].iloc[0]) * 100
            
            return {
                'ticker': ticker,
                'preco_atual': preco_atual,
                'variacao_dia': variacao_dia,
                'variacao_pct': variacao_pct,
                'data': datetime.now().strftime('%Y-%m-%d'),
                'volume': historico['Volume'].iloc[-1] if 'Volume' in historico else 0
            }
        except Exception as e:
            logger.error(f"Erro ao buscar cotação de {ticker}: {e}")
            return None
    
    @staticmethod
    def buscar_historico(ticker: str, periodo: str = "1mo") -> Optional[pd.DataFrame]:
        """Busca histórico de cotações."""
        try:
            symbol = f"{ticker}.SA"
            fii = yf.Ticker(symbol)
            historico = fii.history(period=periodo)
            return historico
        except Exception as e:
            logger.error(f"Erro ao buscar histórico de {ticker}: {e}")
            return None
    
    @staticmethod
    def buscar_dividendos(ticker: str) -> Optional[pd.DataFrame]:
        """Busca dividendos pagos pelo FII."""
        try:
            symbol = f"{ticker}.SA"
            fii = yf.Ticker(symbol)
            dividendos = fii.dividends
            return dividendos
        except Exception as e:
            logger.error(f"Erro ao buscar dividendos de {ticker}: {e}")
            return None
    
    @staticmethod
    def calcular_dy(ticker: str) -> Optional[Dict]:
        """Calcula o Dividend Yield de um FII (timezone-safe)."""
        try:
            from market_data import calcular_dy as _calcular_dy

            return _calcular_dy(ticker)
        except Exception as e:
            logger.error(f"Erro ao calcular DY de {ticker}: {e}")
            return None


class PortfolioAnalyzer:
    """Analisa a carteira de investimentos."""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.fetcher = FiiDataFetcher()
    
    def analisar_carteira(self) -> Dict:
        """Realiza análise completa da carteira (chaves compatíveis com PDF/Excel)."""
        try:
            from db import DatabaseManager as SharedDB
            from portfolio import analisar_carteira as _analisar

            return _analisar(SharedDB())
        except Exception as e:
            logger.error(f"Erro na análise da carteira: {e}")
            return {"erro": str(e)}
    
    def gerar_relatorio_html(self, analise: Dict, pasta: str = "relatorios") -> str:
        """Gera relatório HTML da carteira."""
        # Cria pasta de relatórios se não existir
        Path(pasta).mkdir(exist_ok=True)
        
        template_html = '''
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Relatório de FIIs - {{ data }}</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
                .container { max-width: 1200px; margin: 0 auto; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
                .card { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
                .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
                .summary-item { text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px; }
                .summary-item h3 { margin: 0; color: #666; font-size: 14px; }
                .summary-item p { margin: 5px 0 0; font-size: 24px; font-weight: bold; color: #333; }
                .positive { color: #28a745 !important; }
                .negative { color: #dc3545 !important; }
                table { width: 100%; border-collapse: collapse; margin-top: 15px; }
                th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
                th { background-color: #667eea; color: white; }
                tr:hover { background-color: #f5f5f5; }
                .footer { text-align: center; margin-top: 30px; color: #666; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1> Relatório de FIIs</h1>
                    <p>Gerado em: {{ data }}</p>
                </div>
                
                <div class="card">
                    <h2>Resumo da Carteira</h2>
                    <div class="summary">
                        <div class="summary-item">
                            <h3>Total Investido</h3>
                            <p>R$ {{ "%.2f"|format(total_investido) }}</p>
                        </div>
                        <div class="summary-item">
                            <h3>Valor Atual</h3>
                            <p>R$ {{ "%.2f"|format(total_atual) }}</p>
                        </div>
                        <div class="summary-item">
                            <h3>Dividendos Recebidos</h3>
                            <p>R$ {{ "%.2f"|format(total_recebido) }}</p>
                        </div>
                        <div class="summary-item">
                            <h3>Lucro/Prejuízo</h3>
                            <p class="{{ 'positive' if rentabilidade >= 0 else 'negative' }}">
                                {{ "%.2f"|format(rentabilidade) }}%
                            </p>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Detalhes por FII</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Qtd</th>
                                <th>Preço Compra</th>
                                <th>Preço Atual</th>
                                <th>Valor Investido</th>
                                <th>Valor Atual</th>
                                <th>Lucro/Prejuízo</th>
                                <th>DY Anual</th>
                                <th>Dividendos</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for fii in fiis %}
                            <tr>
                                <td><strong>{{ fii.ticker }}</strong></td>
                                <td>{{ fii.quantidade }}</td>
                                <td>R$ {{ "%.2f"|format(fii.preco_compra) }}</td>
                                <td>R$ {{ "%.2f"|format(fii.preco_atual) }}</td>
                                <td>R$ {{ "%.2f"|format(fii.valor_investido) }}</td>
                                <td>R$ {{ "%.2f"|format(fii.valor_atual) }}</td>
                                <td class="{{ 'positive' if fii.lucro_prejuizo >= 0 else 'negative' }}">
                                    R$ {{ "%.2f"|format(fii.lucro_prejuizo) }} ({{ "%.2f"|format(fii.lucro_prejuizo_pct) }}%)
                                </td>
                                <td>{{ "%.2f"|format(fii.dy_anual) }}%</td>
                                <td>R$ {{ "%.2f"|format(fii.dividendos_recebidos) }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
                <div class="footer">
                    <p>Monitor de FIIs v1.0.0 - Relatório gerado automaticamente</p>
                </div>
            </div>
        </body>
        </html>
        '''
        
        template = Template(template_html)
        html_content = template.render(
            data=analise['data_analise'],
            total_investido=analise['total_investido'],
            total_atual=analise.get('total_atual', analise.get('valor_atual', 0)),
            total_recebido=analise.get('total_recebido', 0),
            rentabilidade=analise.get('rentabilidade', 0),
            fiis=[
                {
                    **fii,
                    "lucro_prejuizo": fii.get("lucro_prejuizo", fii.get("lucro", 0)),
                    "lucro_prejuizo_pct": fii.get("lucro_prejuizo_pct", fii.get("lucro_pct", 0)),
                    "dy_anual": fii.get("dy_anual", fii.get("dy", 0)),
                }
                for fii in analise.get("fiis", [])
            ],
        )
        
        # Salva o arquivo
        filename = f"relatorio_fii_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(pasta, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Relatório gerado: {filepath}")
        return filepath


class AlertManager:
    """Gerencia alertas e notificações."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.db = DatabaseManager()
    
    def verificar_alertas(self, analise: Dict) -> List[str]:
        """Verifica se há alertas para disparar."""
        alertas = []
        config_alertas = self.config.get('alertas', {})
        dy_minimo = config_alertas.get('dy_minimo', 8.0)
        dy_maximo = config_alertas.get('dy_maximo', 20.0)
        variacao_preco = config_alertas.get('variacao_preco', 5.0)
        
        for fii in analise.get('fiis', []):
            ticker = fii['ticker']
            dy = fii.get('dy_anual', 0)
            lucro_pct = fii.get('lucro_prejuizo_pct', 0)
            
            # Alerta de DY muito alto (possível armadilha)
            if dy > dy_maximo:
                alertas.append(f" {ticker}: DY muito alto ({dy:.2f}%) - Possível armadilha!")
            
            # Alerta de DY muito baixo
            if dy < dy_minimo and dy > 0:
                alertas.append(f" {ticker}: DY baixo ({dy:.2f}%) - Abaixo do mínimo desejado")
            
            # Alerta de queda significativa no preço
            if lucro_pct < -variacao_preco:
                alertas.append(f" {ticker}: Queda de {lucro_pct:.2f}% no preço")
            
            # Alerta de alta significativa no preço
            if lucro_pct > variacao_preco:
                alertas.append(f" {ticker}: Alta de {lucro_pct:.2f}% no preço")
        
        return alertas
    
    def enviar_email(self, assunto: str, mensagem: str):
        """Envia email de notificação."""
        config_email = self.config.get('email', {})
        
        if not config_email.get('ativar', False):
            logger.info("Notificações por email desativadas")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = config_email['email_remetente']
            msg['To'] = config_email['email_destinatario']
            msg['Subject'] = assunto
            
            msg.attach(MIMEText(mensagem, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(config_email['smtp_server'], config_email['smtp_port'])
            server.starttls()
            server.login(config_email['email_remetente'], config_email['senha_app'])
            
            text = msg.as_string()
            server.sendmail(config_email['email_remetente'], config_email['email_destinatario'], text)
            server.quit()
            
            logger.info(f"Email enviado: {assunto}")
        except Exception as e:
            logger.error(f"Erro ao enviar email: {e}")
    
    def processar_alertas(self, analise: Dict):
        """Processa e envia alertas."""
        alertas = self.verificar_alertas(analise)
        
        if alertas:
            # Exibe alertas no terminal
            print("\n" + "="*50)
            print(" ALERTAS")
            print("="*50)
            for alerta in alertas:
                print(alerta)
            print("="*50 + "\n")
            
            # Envia email se configurado
            if self.config.get('email', {}).get('ativar', False):
                assunto = f"Alertas FII - {datetime.now().strftime('%d/%m/%Y')}"
                mensagem = "Alertas da sua carteira de FIIs:\n\n"
                for alerta in alertas:
                    mensagem += f"{alerta}\n"
                self.enviar_email(assunto, mensagem)
        
        return alertas


class ChartGenerator:
    """Gera gráficos da carteira."""
    
    @staticmethod
    def gerar_grafico_evolucao(historico: pd.DataFrame, ticker: str):
        """Gera gráfico de evolução do preço."""
        if historico.empty:
            print(f"Sem dados históricos para {ticker}")
            return
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=historico.index,
            open=historico['Open'],
            high=historico['High'],
            low=historico['Low'],
            close=historico['Close'],
            name=ticker
        ))
        
        fig.update_layout(
            title=f'Evolução de {ticker}',
            yaxis_title='Preço (R$)',
            xaxis_title='Data',
            template='plotly_dark'
        )
        
        fig.show()
    
    @staticmethod
    def gerar_grafico_carteira(analise: Dict):
        """Gera gráfico de composição da carteira."""
        if not analise.get('fiis'):
            print("Sem dados para gerar gráfico")
            return
        
        labels = [fii['ticker'] for fii in analise['fiis']]
        values = [fii['valor_atual'] for fii in analise['fiis']]
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=.3,
            textinfo='label+percent',
            insidetextorientation='radial'
        )])
        
        fig.update_layout(
            title='Composição da Carteira de FIIs',
            template='plotly_dark'
        )
        
        fig.show()
    
    @staticmethod
    def gerar_grafico_rentabilidade(analise: Dict):
        """Gera gráfico de rentabilidade por FII."""
        if not analise.get('fiis'):
            print("Sem dados para gerar gráfico")
            return
        
        tickers = [fii['ticker'] for fii in analise['fiis']]
        rentabilidades = [fii['lucro_prejuizo_pct'] for fii in analise['fiis']]
        cores = ['#28a745' if r >= 0 else '#dc3545' for r in rentabilidades]
        
        fig = go.Figure(data=[go.Bar(
            x=tickers,
            y=rentabilidades,
            marker_color=cores,
            text=[f'{r:.2f}%' for r in rentabilidades],
            textposition='auto'
        )])
        
        fig.update_layout(
            title='Rentabilidade por FII (%)',
            yaxis_title='Rentabilidade (%)',
            xaxis_title='FII',
            template='plotly_dark'
        )
        
        fig.show()


class FIIMonitor:
    """Classe principal do monitor de FIIs."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self.carregar_config(config_path)
        self.db = DatabaseManager()
        self.fetcher = FiiDataFetcher()
        self.analyzer = PortfolioAnalyzer(self.db)
        self.alert_manager = AlertManager(self.config)
        self.chart_generator = ChartGenerator()
    
    def carregar_config(self, config_path: str) -> Dict:
        """Carrega configuração do arquivo JSON."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Arquivo de configuração não encontrado: {config_path}")
            return self.config_padrao()
        except json.JSONDecodeError:
            logger.error(f"Erro ao ler configuração: {config_path}")
            return self.config_padrao()
    
    def config_padrao(self) -> Dict:
        """Retorna configuração padrão."""
        return {
            "fiis": [],
            "alertas": {
                "dy_minimo": 8.0,
                "dy_maximo": 20.0,
                "variacao_preco": 5.0
            },
            "email": {
                "ativar": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "email_remetente": "",
                "email_destinatario": "",
                "senha_app": ""
            },
            "relatorio": {
                "formato": "html",
                "pasta": "relatorios"
            }
        }
    
    def salvar_config(self):
        """Salva configuração no arquivo JSON."""
        with open("config.json", 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        logger.info("Configuração salva")
    
    def exibir_menu(self):
        """Exibe o menu principal."""
        print("\n" + "="*50)
        print(" MONITOR DE FIIS - Fundos Imobiliários")
        print("="*50)
        print("1.  Ver cotação de um FII")
        print("2.  Adicionar FII à carteira")
        print("3.  Remover FII da carteira")
        print("4.  Ver carteira completa")
        print("5.  Ver histórico de cotações")
        print("6.  Ver dividendos")
        print("7.  Gerar relatório HTML")
        print("8.  Verificar alertas")
        print("9.  Gerar gráficos")
        print("10.  Configurações")
        print("11.  Atualizar todos os FIIs")
        print("12.  Investidor10 - Dados detalhados")
        print("0.  Sair")
        print("="*50)
    
    def ver_cotacao(self):
        """Busca e exibe cotação de um FII."""
        ticker = input("\nDigite o ticker do FII (ex: MXRF11): ").upper().strip()
        
        if not ticker:
            print("Ticker inválido!")
            return
        
        print(f"\nBuscando cotação de {ticker}...")
        cotacao = self.fetcher.buscar_cotacao_atual(ticker)
        
        if cotacao:
            print("\n" + "="*40)
            print(f" COTAÇÃO - {cotacao['ticker']}")
            print("="*40)
            print(f"Preço Atual: R$ {cotacao['preco_atual']:.2f}")
            print(f"Variação Dia: R$ {cotacao['variacao_dia']:.2f} ({cotacao['variacao_pct']:.2f}%)")
            print(f"Data: {cotacao['data']}")
            print("="*40)
            
            # Salva no banco
            self.db.salvar_cotacao(ticker, cotacao['data'], cotacao['preco_atual'])
        else:
            print(f"Não foi possível obter cotação para {ticker}")
    
    def adicionar_fii(self):
        """Adiciona um FII à carteira."""
        print("\n--- Adicionar FII à Carteira ---")
        ticker = input("Ticker do FII (ex: MXRF11): ").upper().strip()
        
        if not ticker:
            print("Ticker inválido!")
            return
        
        try:
            quantidade = int(input("Quantidade de cotas: "))
            preco_compra = float(input("Preço de compra (R$): "))
            
            if quantidade <= 0 or preco_compra <= 0:
                print("Valores devem ser positivos!")
                return
            
            # Verifica se o FII existe
            cotacao = self.fetcher.buscar_cotacao_atual(ticker)
            if not cotacao:
                print(f"FII {ticker} não encontrado!")
                return
            
            # Adiciona à carteira
            self.db.atualizar_carteira(ticker, quantidade, preco_compra)
            
            # Atualiza configuração
            fiis_config = self.config.get('fiis', [])
            fiis_existente = [f for f in fiis_config if f['ticker'] == ticker]
            
            if fiis_existente:
                fiis_existente[0]['quantidade'] = quantidade
                fiis_existente[0]['preco_compra'] = preco_compra
            else:
                fiis_config.append({
                    'ticker': ticker,
                    'quantidade': quantidade,
                    'preco_compra': preco_compra
                })
            
            self.config['fiis'] = fiis_config
            self.salvar_config()
            
            print(f"\n {ticker} adicionado à carteira com sucesso!")
            print(f"   {quantidade} cotas @ R$ {preco_compra:.2f}")
            print(f"   Total investido: R$ {quantidade * preco_compra:.2f}")
            
        except ValueError:
            print("Valores inválidos!")
    
    def remover_fii(self):
        """Remove um FII da carteira."""
        print("\n--- Remover FII da Carteira ---")
        
        carteira = self.db.obter_carteira()
        if carteira.empty:
            print("Carteira vazia!")
            return
        
        print("\nFIIs na carteira:")
        for _, fii in carteira.iterrows():
            print(f"  - {fii['ticker']}: {fii['quantidade']} cotas")
        
        ticker = input("\nDigite o ticker para remover: ").upper().strip()
        
        if not ticker:
            print("Ticker inválido!")
            return
        
        # Remove do banco
        self.db.remover_da_carteira(ticker)
        
        # Remove da configuração
        self.config['fiis'] = [f for f in self.config.get('fiis', []) if f['ticker'] != ticker]
        self.salvar_config()
        
        print(f"\n {ticker} removido da carteira!")
    
    def ver_carteira(self):
        """Exibe a carteira completa."""
        print("\nAnalisando carteira...")
        analise = self.analyzer.analisar_carteira()
        
        if 'erro' in analise:
            print(analise['erro'])
            return
        
        print("\n" + "="*70)
        print(" CARTEIRA DE FIIs")
        print("="*70)
        print(f"Data da análise: {analise['data_analise']}")
        print("-"*70)
        
        # Resumo
        print(f"\n RESUMO:")
        print(f"   Total Investido:    R$ {analise['total_investido']:.2f}")
        print(f"   Valor Atual:        R$ {analise['total_atual']:.2f}")
        print(f"   Dividendos (12m):   R$ {analise['total_recebido']:.2f}")
        
        cor_lucro = "" if analise['rentabilidade'] >= 0 else ""
        print(f"   {cor_lucro} Lucro/Prejuízo:   {analise['rentabilidade']:.2f}%")
        
        # Detalhes por FII
        print(f"\n📋 DETALHES POR FII:")
        print("-"*70)
        
        headers = ['Ticker', 'Qtd', 'Preço Compra', 'Preço Atual', 'Lucro/Prejuízo', 'DY']
        rows = []
        
        for fii in analise['fiis']:
            lucro_str = f"R$ {fii['lucro_prejuizo']:.2f} ({fii['lucro_prejuizo_pct']:.2f}%)"
            dy_str = f"{fii['dy_anual']:.2f}%" if fii['dy_anual'] > 0 else "N/A"
            
            rows.append([
                fii['ticker'],
                fii['quantidade'],
                f"R$ {fii['preco_compra']:.2f}",
                f"R$ {fii['preco_atual']:.2f}",
                lucro_str,
                dy_str
            ])
        
        print(tabulate(rows, headers=headers, tablefmt='grid'))
        print("="*70)
        
        return analise
    
    def ver_historico(self):
        """Exibe histórico de cotações."""
        ticker = input("\nDigite o ticker do FII: ").upper().strip()
        
        if not ticker:
            print("Ticker inválido!")
            return
        
        historico = self.fetcher.buscar_historico(ticker, "3mo")
        
        if historico is not None and not historico.empty:
            print(f"\n Histórico de {ticker} (últimos 3 meses):")
            print("-"*50)
            
            # Mostra últimos 10 registros
            for data, row in historico.tail(10).iterrows():
                print(f"{data.strftime('%d/%m/%Y')} - R$ {row['Close']:.2f}")
            
            print("-"*50)
            print(f"Total de registros: {len(historico)}")
        else:
            print(f"Não foi possível obter histórico para {ticker}")
    
    def ver_dividendos(self):
        """Exibe dividendos pagos."""
        ticker = input("\nDigite o ticker do FII: ").upper().strip()
        if not ticker:
            print("Informe um ticker (ex: MXRF11).")
            return

        from market_data import buscar_dividendos_serie

        dividendos = buscar_dividendos_serie(ticker)
        if dividendos is not None and not dividendos.empty:
            print(f"\n Dividendos - {ticker}")
            print("-" * 50)
            data_limite = pd.Timestamp((datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
            dividendos_12m = dividendos[dividendos.index >= data_limite]
            if not dividendos_12m.empty:
                for data, valor in dividendos_12m.items():
                    print(f"{data.strftime('%d/%m/%Y')} - R$ {float(valor):.4f}")
                print("-" * 50)
                print(f"Total últimos 12 meses: R$ {float(dividendos_12m.sum()):.4f}")
            else:
                print("Nenhum dividendo nos últimos 12 meses")
        else:
            print("Nenhum dividendo encontrado")
    
    def gerar_relatorio(self):
        """Gera relatório HTML."""
        print("\nGerando relatório...")
        analise = self.analyzer.analisar_carteira()
        
        if 'erro' in analise:
            print(analise['erro'])
            return
        
        pasta = self.config.get('relatorio', {}).get('pasta', 'relatorios')
        filepath = self.analyzer.gerar_relatorio_html(analise, pasta)
        
        print(f"\n Relatório gerado: {filepath}")
        print("   Abrindo no navegador...")
        
        # Abre no navegador padrão
        os.startfile(filepath)
    
    def verificar_alertas(self):
        """Verifica e exibe alertas."""
        print("\nVerificando alertas...")
        analise = self.analyzer.analisar_carteira()
        
        if 'erro' in analise:
            print(analise['erro'])
            return
        
        alertas = self.alert_manager.processar_alertas(analise)
        
        if not alertas:
            print("\n Nenhum alerta no momento!")
    
    def gerar_graficos(self):
        """Gera gráficos da carteira."""
        print("\nGerando gráficos...")
        analise = self.analyzer.analisar_carteira()
        
        if 'erro' in analise:
            print(analise['erro'])
            return
        
        print("\nTipo de gráfico:")
        print("1. Composição da carteira")
        print("2. Rentabilidade por FII")
        print("3. Evolução de um FII")
        
        opcao = input("\nEscolha: ").strip()
        
        if opcao == "1":
            self.chart_generator.gerar_grafico_carteira(analise)
        elif opcao == "2":
            self.chart_generator.gerar_grafico_rentabilidade(analise)
        elif opcao == "3":
            ticker = input("Ticker do FII: ").upper().strip()
            historico = self.fetcher.buscar_historico(ticker, "6mo")
            if historico is not None:
                self.chart_generator.gerar_grafico_evolucao(historico, ticker)
        else:
            print("Opção inválida!")
    
    def configuracoes(self):
        """Gerencia configurações."""
        print("\n--- Configurações ---")
        print("1. Ver configuração atual")
        print("2. Alterar alertas")
        print("3. Configurar email")
        print("4. Voltar")
        
        opcao = input("\nEscolha: ").strip()
        
        if opcao == "1":
            cfg_safe = json.loads(json.dumps(self.config))
            if "email" in cfg_safe and "senha_app" in cfg_safe["email"]:
                cfg_safe["email"]["senha_app"] = "***" if cfg_safe["email"]["senha_app"] else ""
            print("\nConfiguração atual (segredos ocultos):")
            print(json.dumps(cfg_safe, indent=2, ensure_ascii=False))
        
        elif opcao == "2":
            print("\nConfigurar alertas:")
            try:
                dy_min = float(input(f"DY mínimo ({self.config['alertas']['dy_minimo']}%): ") or self.config['alertas']['dy_minimo'])
                dy_max = float(input(f"DY máximo ({self.config['alertas']['dy_maximo']}%): ") or self.config['alertas']['dy_maximo'])
                var_preco = float(input(f"Variação preço ({self.config['alertas']['variacao_preco']}%): ") or self.config['alertas']['variacao_preco'])
                
                self.config['alertas'] = {
                    'dy_minimo': dy_min,
                    'dy_maximo': dy_max,
                    'variacao_preco': var_preco
                }
                self.salvar_config()
                print(" Alertas atualizados!")
            except ValueError:
                print("Valores inválidos!")
        
        elif opcao == "3":
            print("\nConfigurar email:")
            ativar = input(f"Ativar email (s/n) [{('s' if self.config['email']['ativar'] else 'n')}]: ").lower()
            
            self.config['email']['ativar'] = ativar == 's'
            
            if self.config['email']['ativar']:
                self.config['email']['email_remetente'] = input(f"Email remetente: ") or self.config['email']['email_remetente']
                self.config['email']['email_destinatario'] = input(f"Email destinatário: ") or self.config['email']['email_destinatario']
                self.config['email']['senha_app'] = input(f"Senha de app: ") or self.config['email']['senha_app']
            
            self.salvar_config()
            print(" Configuração de email atualizada!")
    
    def atualizar_todos(self):
        """Atualiza cotações de todos os FIIs da carteira."""
        print("\nAtualizando cotações...")
        
        carteira = self.db.obter_carteira()
        if carteira.empty:
            print("Carteira vazia!")
            return
        
        for _, fii in carteira.iterrows():
            ticker = fii['ticker']
            print(f"  Atualizando {ticker}...", end=" ")
            
            cotacao = self.fetcher.buscar_cotacao_atual(ticker)
            if cotacao:
                self.db.salvar_cotacao(ticker, cotacao['data'], cotacao['preco_atual'])
                print(f"R$ {cotacao['preco_atual']:.2f}")
            else:
                print("Erro")
        
        print("\n Atualização concluída!")
        
        # Verifica alertas
        analise = self.analyzer.analisar_carteira()
        if 'erro' not in analise:
            self.alert_manager.processar_alertas(analise)
    
    def buscar_investidor10(self):
        """Busca dados detalhados no Investidor10 via Web Scraping"""
        print("\n--- Investidor10 - Dados Detalhados ---")
        print("Busca dados fundamentalistas de FIIs")
        print("-" * 50)
        
        # Opções de FIIs
        fiis_padrao = ["mxrf11", "kncr11", "cpts11", "mcci11", "rbrr11"]
        
        print("\nFIIs disponíveis:")
        print("1. MXRF11 (Master Cash)")
        print("2. KNCR11 (Kinea Renda Imob.)")
        print("3. CPTS11 (Capital Securitizadora)")
        print("4. MCCI11 (Mauá Capital)")
        print("5. RBRR11 (RBR Properties)")
        print("6. Personalizado")
        
        opcao = input("\nEscolha uma opção (1-6): ").strip()
        
        if opcao == "6":
            tickers_input = input("Digite os tickers separados por vírgula: ").strip()
            fiis = [t.strip() for t in tickers_input.split(",")]
        elif opcao in ["1", "2", "3", "4", "5"]:
            fiis = [fiis_padrao[int(opcao) - 1]]
        else:
            fiis = fiis_padrao
        
        print(f"\n Buscando dados de: {', '.join(fiis).upper()}")
        print("Aguarde...")
        
        api = Investidor10API()
        dados_lista = []
        
        for ticker in fiis:
            dados = api.buscar_fii(ticker)
            dados_lista.append(dados)
        
        # Exibir resultados
        print("\n" + "=" * 60)
        print(" DADOS DO INVESTIDOR10")
        print("=" * 60)
        
        for dados in dados_lista:
            if "erro" in dados:
                print(f"\n✗ {dados['ticker']}: {dados['erro']}")
                continue
            
            print(f"\n{'─' * 50}")
            print(f"Ticker: {dados.get('ticker', 'N/A')}")
            print(f"Nome: {dados.get('nome', 'N/A')}")
            print(f"Preço: R$ {dados.get('preco', 0):.2f}")
            print(f"Dividend Yield: {dados.get('dy', 0):.2f}%")
            print(f"P/VP: {dados.get('p_vp', 0):.2f}")
            print(f"Patrimônio: R$ {dados.get('patrimonio', 0):,.2f}")
            print(f"Vacância: {dados.get('vacancia', 0):.2f}%")
            print(f"Liquidez Diária: R$ {dados.get('liquidez', 0):,.2f}")
            print(f"Setor: {dados.get('setor', 'N/A')}")
        
        print(f"\n{'=' * 60}")
        print(f"Consulta: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print("=" * 60)
        
        # Salvar dados
        salvar = input("\nDeseja salvar os dados? (s/n): ").strip().lower()
        if salvar == "s":
            import csv
            nome_arquivo = f"investidor10_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            with open(nome_arquivo, "w", newline="", encoding="utf-8-sig") as arquivo:
                if dados_lista:
                    writer = csv.DictWriter(arquivo, fieldnames=dados_lista[0].keys())
                    writer.writeheader()
                    writer.writerows(dados_lista)
            
            print(f"✓ Dados salvos em: {nome_arquivo}")
    
    def executar(self):
        """Loop principal do programa."""
        print("\n Iniciando Monitor de FIIs...")
        print(f"   Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        
        while True:
            try:
                self.exibir_menu()
                opcao = input("\nEscolha uma opção: ").strip()
                
                if opcao == "1":
                    self.ver_cotacao()
                elif opcao == "2":
                    self.adicionar_fii()
                elif opcao == "3":
                    self.remover_fii()
                elif opcao == "4":
                    self.ver_carteira()
                elif opcao == "5":
                    self.ver_historico()
                elif opcao == "6":
                    self.ver_dividendos()
                elif opcao == "7":
                    self.gerar_relatorio()
                elif opcao == "8":
                    self.verificar_alertas()
                elif opcao == "9":
                    self.gerar_graficos()
                elif opcao == "10":
                    self.configuracoes()
                elif opcao == "11":
                    self.atualizar_todos()
                elif opcao == "12":
                    self.buscar_investidor10()
                elif opcao == "0":
                    print("\n Obrigado por usar o Monitor de FIIs!")
                    break
                else:
                    print("\n Opção inválida!")
                
                input("\nPressione Enter para continuar...")
                
            except KeyboardInterrupt:
                print("\n\n Programa encerrado pelo usuário.")
                break
            except Exception as e:
                logger.error(f"Erro: {e}")
                print(f"\n Ocorreu um erro: {e}")
                input("Pressione Enter para continuar...")


def executar_diariamente():
    """Função para execução automática diária."""
    monitor = FIIMonitor()
    monitor.atualizar_todos()
    logger.info("Atualização diária concluída")


if __name__ == "__main__":
    # Verifica se há argumento para execução automática
    if len(sys.argv) > 1 and sys.argv[1] == "--daily":
        executar_diariamente()
    else:
        # Executa interface interativa
        monitor = FIIMonitor()
        monitor.executar()

