"""
Dashboard de Monitoramento de FIIs
Interface web com Streamlit
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import json
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
import sys
import os

# Detectar se está no Render (PostgreSQL) ou local (SQLite)
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith("postgresql")

# Configuração da página
st.set_page_config(
    page_title="Monitor de FIIs",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado global
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #667eea;
        text-align: center;
        padding: 1rem;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #d1d5db !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricDelta"] {
        color: #34d399 !important;
    }
    .stMetric {
        background-color: #1f2937 !important;
        padding: 1rem !important;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
        border: 1px solid #374151 !important;
    }
    /* Forçar texto BRANCO em todos os elementos do Streamlit */
    .stMarkdown p, .stMarkdown span, .stMarkdown div, .stMarkdown label,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
    .stMarkdown h5, .stMarkdown h6, .stMarkdown li, .stMarkdown td, .stMarkdown th {
        color: #ffffff !important;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        color: #667eea !important;
    }
    /* Tabelas */
    .stDataFrame [data-testid="stDataFrameCell"] {
        color: #ffffff !important;
        font-size: 1rem !important;
    }
    [data-testid="stDataFrame"] {
        color: #ffffff !important;
    }
    /* Sidebar */
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown span,
    [data-testid="stSidebar"] .stMarkdown div,
    [data-testid="stSidebar"] .stMarkdown label {
        color: #ffffff !important;
    }
    /* Botões */
    .stButton button {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    /* Forms */
    .stTextInput label, .stNumberInput label, .stSelectbox label,
    .stTextArea label, .stCheckbox label, .stRadio label {
        color: #d1d5db !important;
    }
    .stTextInput input, .stNumberInput input {
        color: #ffffff !important;
        background-color: #374151 !important;
    }
    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        color: #d1d5db !important;
    }
    .stTabs [aria-selected="true"] {
        color: #667eea !important;
    }
    /* Form labels */
    .stForm label {
        color: #d1d5db !important;
    }
    /* Success/Error/Info boxes */
    .stSuccess, .stError, .stInfo, .stWarning {
        color: #ffffff !important;
    }
    /* Headers hr */
    hr {
        border-color: #374151 !important;
    }
    /* Titles */
    .stSubheader {
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)


class Investidor10API:
    """API para buscar dados do Investidor10"""
    
    def __init__(self):
        self.base_url = "https://investidor10.com.br/fiis/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def buscar_fii(self, ticker: str) -> dict:
        """Busca dados de um FII"""
        ticker = ticker.upper().replace(".SA", "")
        url = f"{self.base_url}{ticker.lower()}/"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            texto = soup.get_text()
            
            dados = {"ticker": ticker, "url": url}
            
            # Buscar nome
            h1 = soup.find("h1")
            if h1:
                dados["nome"] = h1.get_text(strip=True)
            
            # Buscar preco
            preco_match = re.search(rf"{ticker}\s*Cota..o.*?R\$\s*([\d.,]+)", texto, re.IGNORECASE | re.DOTALL)
            if preco_match:
                dados["preco"] = self._extrair_valor(preco_match.group(1))
            
            # Buscar DY
            dy_match = re.search(rf"{ticker}\s*DY\s*\(12M\)\s*:\s*([\d.,]+)%", texto, re.IGNORECASE)
            if dy_match:
                dados["dy"] = self._extrair_percentual(dy_match.group(1))
            
            # Buscar P/VP
            pvp_match = re.search(rf"{ticker}\s*P/VP\s*:\s*([\d.,]+)", texto, re.IGNORECASE)
            if pvp_match:
                dados["p_vp"] = self._extrair_valor(pvp_match.group(1))
            
            # Buscar patrimonio
            pl_match = re.search(r"patrim.nio\s+de\s+R\$\s*([\d.,]+)\s*(Bilh|Milh)", texto, re.IGNORECASE)
            if pl_match:
                valor = self._extrair_valor(pl_match.group(1))
                unidade = pl_match.group(2).lower()
                if "bilh" in unidade:
                    valor *= 1000000000
                elif "milh" in unidade:
                    valor *= 1000000
                dados["patrimonio"] = valor
            
            # Buscar vacancia
            vac_match = re.search(r"vac.ncia.*?([\d.,]+)%", texto, re.IGNORECASE)
            if vac_match:
                dados["vacancia"] = self._extrair_percentual(vac_match.group(1))
            
            # Buscar setor
            setor_match = re.search(r"do segmento\s+(Híbrido|Papel|Tijolo|Logístico|FOF)", texto, re.IGNORECASE)
            if setor_match:
                dados["setor"] = setor_match.group(1)
            
            return dados
            
        except Exception as e:
            return {"ticker": ticker, "erro": str(e)}
    
    def _extrair_valor(self, texto: str) -> float:
        try:
            texto = texto.replace("R$", "").strip()
            texto = texto.replace(".", "").replace(",", ".")
            texto = "".join(c for c in texto if c.isdigit() or c in ".-")
            return float(texto) if texto else 0.0
        except:
            return 0.0
    
    def _extrair_percentual(self, texto: str) -> float:
        try:
            texto = texto.replace("%", "").replace(",", ".").strip()
            return float(texto) if texto else 0.0
        except:
            return 0.0


class DatabaseManager:
    """Gerencia banco de dados - SQLite (local) ou PostgreSQL (Render/Neon)"""
    
    def __init__(self, db_path="fii_data.db"):
        self.db_path = db_path
        self.use_pg = USE_POSTGRES
        self.init_database()
    
    def _get_conn(self):
        if self.use_pg:
            import psycopg2
            return psycopg2.connect(DATABASE_URL)
        else:
            return sqlite3.connect(self.db_path)
    
    def init_database(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if self.use_pg:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS carteira (
                    ticker TEXT PRIMARY KEY,
                    quantidade INTEGER NOT NULL,
                    preco_compra REAL NOT NULL,
                    data_compra TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cotacoes (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    data TEXT NOT NULL,
                    preco REAL NOT NULL,
                    UNIQUE(ticker, data)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    preco_alvo REAL,
                    data_adicionado TEXT NOT NULL,
                    notas TEXT,
                    UNIQUE(ticker)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS carteira (
                    ticker TEXT PRIMARY KEY,
                    quantidade INTEGER NOT NULL,
                    preco_compra REAL NOT NULL,
                    data_compra TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cotacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    data TEXT NOT NULL,
                    preco REAL NOT NULL,
                    UNIQUE(ticker, data)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    preco_alvo REAL,
                    data_adicionado TEXT NOT NULL,
                    notas TEXT,
                    UNIQUE(ticker)
                )
            ''')
        
        conn.commit()
        conn.close()
        
        if self.use_pg:
            self._migrate_sqlite_if_needed()
    
    def _migrate_sqlite_if_needed(self):
        """Migra dados do SQLite local para PostgreSQL se o PG estiver vazio"""
        import os
        pg_conn = self._get_conn()
        pg_cur = pg_conn.cursor()
        pg_cur.execute("SELECT COUNT(*) FROM carteira")
        if pg_cur.fetchone()[0] > 0:
            pg_conn.close()
            return
        
        sqlite_path = "fii_data.db"
        if not os.path.exists(sqlite_path):
            pg_conn.close()
            return
        
        try:
            sl_conn = sqlite3.connect(sqlite_path)
            sl_cur = sl_conn.cursor()
            
            sl_cur.execute("SELECT * FROM carteira")
            rows = sl_cur.fetchall()
            for row in rows:
                pg_cur.execute(
                    "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
                    row
                )
            
            sl_cur.execute("SELECT ticker, data, preco FROM cotacoes")
            rows = sl_cur.fetchall()
            for row in rows:
                pg_cur.execute(
                    "INSERT INTO cotacoes (ticker, data, preco) VALUES (%s, %s, %s) ON CONFLICT (ticker, data) DO NOTHING",
                    row
                )
            
            sl_cur.execute("SELECT ticker, preco_alvo, data_adicionado, notas FROM watchlist")
            rows = sl_cur.fetchall()
            for row in rows:
                pg_cur.execute(
                    "INSERT INTO watchlist (ticker, preco_alvo, data_adicionado, notas) VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
                    row
                )
            
            pg_conn.commit()
            sl_conn.close()
            pg_conn.close()
        except Exception as e:
            pg_conn.close()
    
    def obter_carteira(self) -> pd.DataFrame:
        conn = self._get_conn()
        df = pd.read_sql_query("SELECT * FROM carteira", conn)
        conn.close()
        return df
    
    def adicionar_fii(self, ticker: str, quantidade: int, preco: float):
        conn = self._get_conn()
        cursor = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d")
        
        if self.use_pg:
            cursor.execute("SELECT quantidade, preco_compra FROM carteira WHERE ticker = %s", (ticker,))
        else:
            cursor.execute("SELECT quantidade, preco_compra FROM carteira WHERE ticker = ?", (ticker,))
        existente = cursor.fetchone()
        
        if existente:
            qtd_antiga = existente[0]
            preco_antigo = existente[1]
            nova_qtd = qtd_antiga + quantidade
            preco_medio = ((qtd_antiga * preco_antigo) + (quantidade * preco)) / nova_qtd
            
            if self.use_pg:
                cursor.execute(
                    "UPDATE carteira SET quantidade = %s, preco_compra = %s, data_compra = %s WHERE ticker = %s",
                    (nova_qtd, round(preco_medio, 4), data, ticker)
                )
            else:
                cursor.execute(
                    "UPDATE carteira SET quantidade = ?, preco_compra = ?, data_compra = ? WHERE ticker = ?",
                    (nova_qtd, round(preco_medio, 4), data, ticker)
                )
        else:
            if self.use_pg:
                cursor.execute(
                    "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) VALUES (%s, %s, %s, %s)",
                    (ticker, quantidade, preco, data)
                )
            else:
                cursor.execute(
                    "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) VALUES (?, ?, ?, ?)",
                    (ticker, quantidade, preco, data)
                )
        
        conn.commit()
        conn.close()
    
    def remover_fii(self, ticker: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        if self.use_pg:
            cursor.execute("DELETE FROM carteira WHERE ticker = %s", (ticker,))
        else:
            cursor.execute("DELETE FROM carteira WHERE ticker = ?", (ticker,))
        conn.commit()
        conn.close()
    
    def salvar_cotacao(self, ticker: str, preco: float):
        conn = self._get_conn()
        cursor = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d")
        if self.use_pg:
            cursor.execute(
                "INSERT INTO cotacoes (ticker, data, preco) VALUES (%s, %s, %s) ON CONFLICT (ticker, data) DO UPDATE SET preco = EXCLUDED.preco",
                (ticker, data, preco)
            )
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO cotacoes (ticker, data, preco) VALUES (?, ?, ?)",
                (ticker, data, preco)
            )
        conn.commit()
        conn.close()
    
    def adicionar_watchlist(self, ticker: str, preco_alvo: float = None, notas: str = ""):
        conn = self._get_conn()
        cursor = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d %H:%M")
        if self.use_pg:
            cursor.execute(
                "INSERT INTO watchlist (ticker, preco_alvo, data_adicionado, notas) VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO UPDATE SET preco_alvo = EXCLUDED.preco_alvo, notas = EXCLUDED.notas",
                (ticker, preco_alvo, data, notas)
            )
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO watchlist (ticker, preco_alvo, data_adicionado, notas) VALUES (?, ?, ?, ?)",
                (ticker, preco_alvo, data, notas)
            )
        conn.commit()
        conn.close()
    
    def remover_watchlist(self, ticker: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        if self.use_pg:
            cursor.execute("DELETE FROM watchlist WHERE ticker = %s", (ticker,))
        else:
            cursor.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
        conn.commit()
        conn.close()
    
    def obter_watchlist(self) -> pd.DataFrame:
        conn = self._get_conn()
        df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY data_adicionado DESC", conn)
        conn.close()
        return df


# Lista de FIIs populares
FIIS_POPULARES = [
    "MXRF11", "KNCR11", "CPTS11", "MCCI11", "RBRR11",
    "HGLG11", "XPML11", "KNRI11", "BTLG11", "IRDM11",
    "HSML11", "VISC11", "MXRF11", "KNHY11", "TRXF11",
    "BRTF11", "CCRO11", "IVCB11", "LFTT11", "RURA11",
    "BPML11", "BRML11", "EGIE11", "ENEV11", "TAEE11",
    "TAPR11", "VIVR11", "WEGE3", "PETR4", "VALE3"
]


def calcular_score(dados: dict) -> float:
    """Calcula score de qualidade do FII (0-100)"""
    score = 50  # Base
    
    # DY (peso 30%)
    dy = dados.get("dy", 0)
    if dy >= 12:
        score += 15
    elif dy >= 10:
        score += 10
    elif dy >= 8:
        score += 5
    elif dy < 6:
        score -= 10
    
    # P/VP (peso 25%)
    pvp = dados.get("p_vp", 0)
    if 0.8 <= pvp <= 1.0:
        score += 12
    elif 0.7 <= pvp < 0.8:
        score += 8
    elif pvp > 1.2:
        score -= 5
    
    # Vacancia (peso 20%)
    vac = dados.get("vacancia", 0)
    if vac < 5:
        score += 10
    elif vac < 10:
        score += 5
    elif vac > 20:
        score -= 10
    
    # Patrimonio (peso 15%)
    pl = dados.get("patrimonio", 0)
    if pl > 1000000000:  # > 1 bilhao
        score += 8
    elif pl > 500000000:  # > 500 milhoes
        score += 5
    
    # Setor (peso 10%)
    setor = dados.get("setor", "")
    if setor in ["Logístico", "Tijolo"]:
        score += 5
    elif setor == "Papel":
        score += 3
    
    return min(max(score, 0), 100)


def main():
    """Função principal do dashboard"""
    
    # Header
    st.markdown('<h1 class="main-header">🏠 Monitor de FIIs</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar
    st.sidebar.title("📋 Menu")
    opcao = st.sidebar.radio(
        "Navegação",
        ["📊 Dashboard", "📈 Carteira", "🔍 Buscar FII", "🎯 Watchlist", "⚖️ Comparar FIIs", "⚙️ Configurações"]
    )
    
    # Inicializar sessão
    if "api" not in st.session_state:
        st.session_state.api = Investidor10API()
    if "db" not in st.session_state:
        st.session_state.db = DatabaseManager()
    
    # Dashboard
    if opcao == "📊 Dashboard":
        exibir_dashboard()
    
    # Carteira
    elif opcao == "📈 Carteira":
        exibir_carteira()
    
    # Buscar FII
    elif opcao == "🔍 Buscar FII":
        exibir_buscar_fii()
    
    # Comparar FIIs
    elif opcao == "⚖️ Comparar FIIs":
        exibir_comparacao()
    
    # Watchlist
    elif opcao == "🎯 Watchlist":
        exibir_watchlist()
    
    # Configurações
    elif opcao == "⚙️ Configurações":
        exibir_configuracoes()


def exibir_dashboard():
    """Exibe dashboard principal"""
    
    st.header("📊 Visão Geral")
    
    # Buscar carteira real do banco
    carteira = st.session_state.db.obter_carteira()
    
    total_investido = 0.0
    valor_atual = 0.0
    rendimento_mensal = 0.0
    dy_anual_medio = 0.0
    fiis_carteira = []
    
    if not carteira.empty:
        for _, row in carteira.iterrows():
            ticker = row['ticker']
            qtd = row['quantidade']
            preco_compra = row['preco_compra']
            total_investido += qtd * preco_compra
            
            # Buscar cotação atual
            dados = buscar_dados_tempo_real(ticker)
            if "erro" not in dados:
                preco_atual = dados.get("preco_atual") or dados.get("preco", preco_compra)
                dy = dados.get("dy", 0)
            else:
                preco_atual = preco_compra
                dy = 0
            
            valor_atual += qtd * preco_atual
            rendimento_mensal += qtd * preco_atual * (dy / 100) / 12 if dy else 0
            fiis_carteira.append({
                "ticker": ticker,
                "qtd": qtd,
                "preco_compra": preco_compra,
                "preco_atual": preco_atual,
                "valor": qtd * preco_atual,
                "dy": dy
            })
        
        if valor_atual > 0:
            dy_anual_medio = (rendimento_mensal * 12 / valor_atual) * 100
    
    lucro = valor_atual - total_investido
    lucro_pct = (lucro / total_investido * 100) if total_investido > 0 else 0
    
    # Métricas principais com cores para fundo escuro
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("**Total Investido**")
        st.markdown(f'<p style="color: #ffffff; font-size: 1.8rem; font-weight: 700; margin: 0;">R$ {total_investido:,.2f}</p>', unsafe_allow_html=True)
    
    with col2:
        delta_valor = f"+R$ {lucro:.2f}" if lucro >= 0 else f"-R$ {abs(lucro):.2f}"
        st.markdown("**Valor Atual**")
        st.markdown(f'<p style="color: #ffffff; font-size: 1.8rem; font-weight: 700; margin: 0;">R$ {valor_atual:,.2f}</p>', unsafe_allow_html=True)
        cor_lucro = "#34d399" if lucro >= 0 else "#f87171"
        st.markdown(f'<p style="color: {cor_lucro}; font-size: 0.9rem; font-weight: 600; margin: 0;">{delta_valor} ({lucro_pct:+.2f}%)</p>', unsafe_allow_html=True)
    
    with col3:
        st.markdown("**Rendimento Mensal**")
        st.markdown(f'<p style="color: #ffffff; font-size: 1.8rem; font-weight: 700; margin: 0;">R$ {rendimento_mensal:,.2f}</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="color: #34d399; font-size: 0.9rem; font-weight: 600; margin: 0;">Estimado</p>', unsafe_allow_html=True)
    
    with col4:
        st.markdown("**DY Anual Médio**")
        st.markdown(f'<p style="color: #ffffff; font-size: 1.8rem; font-weight: 700; margin: 0;">{dy_anual_medio:.2f}%</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="color: #667eea; font-size: 0.9rem; font-weight: 600; margin: 0;">da carteira</p>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Gráfico de composição
    if fiis_carteira:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Composição da Carteira")
            fig = px.pie(
                df_pie := pd.DataFrame(fiis_carteira),
                names="ticker",
                values="valor",
                title="Distribuição por FII",
                color_discrete_sequence=px.colors.qualitative.Set3,
                hole=0.4
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, width="stretch")
        
        with col2:
            st.subheader("💰 Projeção de Rendimentos (12 meses)")
            meses = list(range(1, 13))
            rendimentos = [rendimento_mensal * m for m in meses]
            acumulado = [rendimento_mensal * m + total_investido for m in meses]
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=meses, y=rendimentos,
                name="Rendimento Mensal",
                marker_color="#667eea"
            ))
            fig.add_trace(go.Scatter(
                x=meses, y=acumulado,
                name="Patrimônio + Rendimentos",
                line=dict(color="#10b981", width=3),
                mode="lines+markers"
            ))
            fig.update_layout(
                xaxis_title="Mês",
                yaxis_title="R$",
                hovermode="x unified"
            )
            st.plotly_chart(fig, width="stretch")
        
        # Tabela da carteira
        st.subheader("💼 Detalhes da Carteira")
        df_carteira = pd.DataFrame(fiis_carteira)
        df_carteira["lucro"] = df_carteira["valor"] - (df_carteira["qtd"] * df_carteira["preco_compra"])
        df_carteira["lucro_pct"] = (df_carteira["lucro"] / (df_carteira["qtd"] * df_carteira["preco_compra"]) * 100).fillna(0)
        
        st.dataframe(
            df_carteira[["ticker", "qtd", "preco_compra", "preco_atual", "valor", "dy", "lucro", "lucro_pct"]].rename(columns={
                "ticker": "FII",
                "qtd": "Qtd",
                "preco_compra": "Preço Compra",
                "preco_atual": "Preço Atual",
                "valor": "Valor Atual",
                "dy": "DY %",
                "lucro": "Lucro R$",
                "lucro_pct": "Lucro %"
            }).style.format({
                "Preço Compra": "R$ {:.2f}",
                "Preço Atual": "R$ {:.2f}",
                "Valor Atual": "R$ {:.2f}",
                "DY %": "{:.2f}%",
                "Lucro R$": "R$ {:.2f}",
                "Lucro %": "{:+.2f}%"
            }),
            width="stretch"
        )
    else:
        st.info("📝 Sua carteira está vazia. Adicione FIIs na aba **Carteira** no menu lateral.")
    
    st.markdown("---")
    
    # FIIs mais buscados
    st.subheader("🔥 FIIs Populares")
    
    with st.spinner("Carregando FIIs populares..."):
        fiis_data = []
        for ticker in FIIS_POPULARES[:10]:
            dados = buscar_dados_tempo_real(ticker)
            if "erro" not in dados:
                fiis_data.append({
                    "ticker": ticker,
                    "preco": dados.get("preco_atual") or dados.get("preco", 0),
                    "dy": dados.get("dy", 0),
                    "p_vp": dados.get("p_vp", 0),
                    "setor": dados.get("setor", "N/A"),
                    "variacao": dados.get("variacao", 0)
                })
    
    if fiis_data:
        df = pd.DataFrame(fiis_data)
        st.dataframe(
            df[["ticker", "preco", "variacao", "dy", "p_vp", "setor"]].rename(columns={
                "ticker": "Ticker",
                "preco": "Preço (R$)",
                "variacao": "Var %",
                "dy": "DY (%)",
                "p_vp": "P/VP",
                "setor": "Setor"
            }).style.format({
                "Preço (R$)": "R$ {:.2f}",
                "Var %": "{:+.2f}%",
                "DY (%)": "{:.2f}%",
                "P/VP": "{:.2f}"
            }),
            width="stretch"
        )


def exibir_carteira():
    """Exibe gerenciamento da carteira"""
    
    st.markdown("""
    <style>
    .cart-card {
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 0.8rem;
        background: #1f2937;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .cart-ticker {
        font-size: 1.8rem !important;
        font-weight: 800 !important;
        color: #ffffff !important;
    }
    .cart-valor {
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        color: #ffffff !important;
    }
    .cart-info {
        font-size: 1.3rem !important;
        color: #d1d5db !important;
        font-weight: 600 !important;
    }
    .cart-label {
        font-size: 0.9rem !important;
        color: #9ca3af !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .cart-header {
        font-size: 1rem !important;
        color: #9ca3af !important;
        font-weight: 700 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.header("📈 Sua Carteira")
    
    # Formulário para adicionar FII
    with st.form("adicionar_fii", clear_on_submit=True):
        st.subheader("➕ Adicionar FII")
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker = st.text_input("Ticker", "MXRF11").upper()
        with col2:
            quantidade = st.number_input("Quantidade", min_value=1, value=10)
        with col3:
            preco = st.number_input("Preço (R$)", min_value=0.01, value=9.00, step=0.01)
        
        if st.form_submit_button("➕ Adicionar à Carteira", type="primary", width="stretch"):
            # Verificar se já existe para mostrar mensagem
            carteira_atual = st.session_state.db.obter_carteira()
            ja_existe = ticker in carteira_atual['ticker'].values if not carteira_atual.empty else False
            
            st.session_state.db.adicionar_fii(ticker, quantidade, preco)
            
            if ja_existe:
                st.success(f"✅ {ticker} unificado! Quantidade e preço médio atualizados.")
            else:
                st.success(f"✅ {ticker} adicionado à carteira!")
            st.rerun()
    
    st.markdown("---")
    
    # Carteira atual
    carteira = st.session_state.db.obter_carteira()
    
    if carteira.empty:
        st.info("📝 Carteira vazia. Adicione um FII acima.")
        return
    
    # Calcular totais
    total_investido = sum(row['quantidade'] * row['preco_compra'] for _, row in carteira.iterrows())
    
    st.subheader(f"📋 {len(carteira)} FII(s) na Carteira — Total: R$ {total_investido:,.2f}")
    
    # Cabeçalho
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2, 1, 1, 1, 0.5])
    with col_h1:
        st.markdown('<span class="cart-header">FII</span>', unsafe_allow_html=True)
    with col_h2:
        st.markdown('<span class="cart-header">Quantidade</span>', unsafe_allow_html=True)
    with col_h3:
        st.markdown('<span class="cart-header">Preço Compra</span>', unsafe_allow_html=True)
    with col_h4:
        st.markdown('<span class="cart-header">Total Investido</span>', unsafe_allow_html=True)
    with col_h5:
        st.markdown('<span class="cart-header">Ação</span>', unsafe_allow_html=True)
    
    st.markdown('<hr style="border: none; border-top: 2px solid #e5e7eb; margin: 0.5rem 0;">', unsafe_allow_html=True)
    
    # Listar cada FII
    for _, row in carteira.iterrows():
        ticker = row['ticker']
        qtd = row['quantidade']
        preco_compra = row['preco_compra']
        total = qtd * preco_compra
        
        # Buscar preço atual
        dados = buscar_dados_tempo_real(ticker)
        if "erro" not in dados:
            preco_atual = dados.get("preco_atual") or dados.get("preco", preco_compra)
            variacao = ((preco_atual - preco_compra) / preco_compra) * 100
        else:
            preco_atual = preco_compra
            variacao = 0
        
        valor_atual = qtd * preco_atual
        lucro = valor_atual - total
        
        # Cor do lucro
        cor_lucro = "#10b981" if lucro >= 0 else "#ef4444"
        seta = "▲" if lucro >= 0 else "▼"
        
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 0.5])
        
        with col1:
            st.markdown(f'<span class="cart-ticker">{ticker}</span>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<span class="cart-info">{qtd} cotas</span>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<span class="cart-info">R$ {preco_compra:.2f}</span>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<span class="cart-valor">R$ {total:,.2f}</span>', unsafe_allow_html=True)
            st.markdown(f'<span style="color: {cor_lucro} !important; font-weight: 700; font-size: 1rem;">{seta} R$ {lucro:+,.2f} ({variacao:+.1f}%)</span>', unsafe_allow_html=True)
        with col5:
            if st.button("🗑️", key=f"remover_{ticker}", width="stretch"):
                st.session_state.db.remover_fii(ticker)
                st.rerun()
        
        st.markdown('<hr style="border: none; border-top: 1px solid #f3f4f6; margin: 0.3rem 0;">', unsafe_allow_html=True)


def buscar_dados_tempo_real(ticker: str) -> dict:
    """Busca dados em tempo real via Yahoo Finance + Investidor10"""
    import yfinance as yf
    
    ticker_yf = f"{ticker}.SA"
    dados = {"ticker": ticker}
    
    try:
        # Dados em tempo real do Yahoo Finance
        acao = yf.Ticker(ticker_yf)
        info = acao.info
        hist = acao.history(period="5d")
        
        if not hist.empty:
            dados["preco_atual"] = float(hist["Close"].iloc[-1])
            dados["preco_anterior"] = float(hist["Close"].iloc[-2]) if len(hist) > 1 else dados["preco_atual"]
            dados["variacao"] = ((dados["preco_atual"] - dados["preco_anterior"]) / dados["preco_anterior"]) * 100
            dados["maxima_dia"] = float(hist["High"].iloc[-1])
            dados["minima_dia"] = float(hist["Low"].iloc[-1])
            dados["volume"] = int(hist["Volume"].iloc[-1])
            dados["abertura"] = float(hist["Open"].iloc[-1])
        
        # Dados fundamentalistas do Yahoo
        dados["nome"] = info.get("longName") or info.get("shortName") or ticker
        dy_raw = info.get("dividendYield") or 0
        # Yahoo retorna como decimal (0.13 = 13%) para ações BR, mas pode vir como 13.0
        dados["dy"] = dy_raw * 100 if dy_raw < 1 else dy_raw
        dados["p_vp"] = info.get("priceToBook") or 0
        dados["patrimonio"] = info.get("totalAssets") or 0
        dados["setor"] = info.get("sector") or "FII"
        dados["moeda"] = info.get("currency", "BRL")
        dados["horario_dados"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        dados["fonte"] = "Yahoo Finance (Tempo Real)"
        
        # Complementar com dados do Investidor10
        dados_inv = st.session_state.api.buscar_fii(ticker)
        if "erro" not in dados_inv:
            # Usar DY do Investidor10 se for mais preciso
            if dados_inv.get("dy", 0) > 0:
                dados["dy_investidor10"] = dados_inv.get("dy")
            dados["vacancia"] = dados_inv.get("vacancia", 0)
            dados["fonte_dados"] = "Yahoo Finance + Investidor10"
        
        return dados
        
    except Exception as e:
        # Fallback: Investidor10 apenas
        dados_inv = st.session_state.api.buscar_fii(ticker)
        if "erro" in dados_inv:
            return {"erro": dados_inv.get("erro", "Erro desconhecido")}
        dados.update(dados_inv)
        dados["fonte"] = "Investidor10 (Fallback)"
        dados["horario_dados"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return dados


def exibir_buscar_fii():
    """Exibe busca de FII com dados em tempo real"""
    
    # CSS customizado para a página
    st.markdown("""
    <style>
    .fii-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    .fii-ticker {
        font-size: 2.5rem;
        font-weight: bold;
        margin: 0;
        color: #ffffff !important;
    }
    .fii-nome {
        font-size: 1.1rem;
        opacity: 0.9;
        margin: 0;
        color: #ffffff !important;
    }
    .preco-destaque {
        font-size: 3rem;
        font-weight: bold;
        color: #667eea;
    }
    .variacao-positiva {
        color: #34d399;
        font-weight: bold;
        font-size: 1.3rem;
    }
    .variacao-negativa {
        color: #f87171;
        font-weight: bold;
        font-size: 1.3rem;
    }
    .info-box {
        background: #1f2937;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
    }
    .info-box h4 {
        color: #ffffff !important;
    }
    .info-box p {
        color: #d1d5db !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.header("🔍 Buscar FII - Tempo Real")
    
    # Campo de busca
    col_busca, col_btn, col_auto = st.columns([3, 1, 1])
    with col_busca:
        ticker = st.text_input("", "MXRF11", placeholder="Digite o ticker (ex: MXRF11)", label_visibility="collapsed").upper()
    with col_btn:
        buscar = st.button("🔍 Buscar", type="primary", width="stretch")
    with col_auto:
        auto_refresh = st.checkbox("🔄 Auto", value=False)
    
    # Auto-refresh a cada 2 minutos (120 segundos)
    if auto_refresh:
        import time
        time.sleep(120)
        st.rerun()
    
    if buscar or auto_refresh:
        with st.spinner("Buscando dados em tempo real..."):
            dados = buscar_dados_tempo_real(ticker)
        
        if "erro" in dados:
            st.error(f"❌ Erro ao buscar {ticker}: {dados['erro']}")
            return
        
        # Calcular score
        score = calcular_score(dados)
        
        # Header personalizado
        variacao = dados.get("variacao", 0)
        cor_variacao = "🟢" if variacao >= 0 else "🔴"
        seta = "▲" if variacao >= 0 else "▼"
        
        st.markdown(f"""
        <div class="fii-header">
            <p class="fii-ticker">🏢 {dados.get('ticker', ticker)}</p>
            <p class="fii-nome">{dados.get('nome', 'Fundo Imobiliário')}</p>
            <p style="font-size: 0.85rem; opacity: 0.8; margin-top: 0.5rem; color: #ffffff !important;">
                ⏱️ Atualizado: {dados.get('horario_dados', 'N/A')} | 📡 {dados.get('fonte', 'N/A')}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Preço em destaque
        col_preco, col_variacao, col_score = st.columns([2, 1, 1])
        
        with col_preco:
            preco = dados.get("preco_atual") or dados.get("preco", 0)
            st.markdown(f'<p style="color: #9ca3af; margin: 0;">Preço Atual</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="preco-destaque">R$ {preco:.2f}</p>', unsafe_allow_html=True)
        
        with col_variacao:
            st.markdown(f'<p style="color: #9ca3af; margin: 0;">Variação Dia</p>', unsafe_allow_html=True)
            classe_var = "variacao-positiva" if variacao >= 0 else "variacao-negativa"
            st.markdown(f'<p class="{classe_var}">{cor_variacao} {seta} {variacao:+.2f}%</p>', unsafe_allow_html=True)
        
        with col_score:
            st.markdown(f'<p style="color: #9ca3af; margin: 0;">Score</p>', unsafe_allow_html=True)
            cor_score = "#34d399" if score >= 70 else "#fbbf24" if score >= 40 else "#f87171"
            st.markdown(f'<p style="font-size: 2.5rem; font-weight: bold; color: {cor_score}; margin: 0;">{score:.0f}<span style="font-size: 1rem; color: #9ca3af;">/100</span></p>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Métricas em cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📊 DY Anual", f"{dados.get('dy', 0):.2f}%", 
                     help="Dividend Yield dos últimos 12 meses")
        with col2:
            st.metric("💹 P/VP", f"{dados.get('p_vp', 0):.2f}",
                     help="Preço / Valor Patrimonial")
        with col3:
            st.metric("🏢 Vacância", f"{dados.get('vacancia', 0):.1f}%",
                     help="Taxa de vacância dos imóveis")
        with col4:
            patrimonio_mi = dados.get("patrimonio", 0) / 1000000
            st.metric("💰 Patrimônio", f"R$ {patrimonio_mi:.0f} Mi",
                     help="Patrimônio líquido do fundo")
        
        st.markdown("---")
        
        # Gráficos
        tab1, tab2, tab3 = st.tabs(["📈 Cotação", "📊 Indicadores", "ℹ️ Detalhes"])
        
        with tab1:
            st.subheader("Variação do Dia")
            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            with col_g1:
                st.metric("Abertura", f"R$ {dados.get('abertura', 0):.2f}")
            with col_g2:
                st.metric("Máxima", f"R$ {dados.get('maxima_dia', 0):.2f}")
            with col_g3:
                st.metric("Mínima", f"R$ {dados.get('minima_dia', 0):.2f}")
            with col_g4:
                volume = dados.get("volume", 0)
                st.metric("Volume", f"{volume:,}".replace(",", "."))
            
            # Gráfico de variação
            fig = go.Figure()
            fig.add_trace(go.Indicator(
                mode="number+delta",
                value=preco,
                delta={"reference": dados.get("preco_anterior", preco), "relative": True},
                title={"text": "Preço vs Fechamento Anterior"},
                number={"prefix": "R$ ", "valueformat": ".2f"},
                domain={"x": [0, 1], "y": [0, 1]}
            ))
            fig.update_layout(height=400, margin=dict(l=40, r=40, t=60, b=20))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        
        with tab2:
            st.subheader("Indicadores Fundamentalistas")
            
            col_ig1, col_ig2 = st.columns(2)
            
            with col_ig1:
                # Gauge do Score
                fig_score = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=score,
                    title={"text": "🎯 Score de Qualidade", "font": {"size": 18}},
                    delta={"reference": 50, "increasing": {"color": "#10b981"}},
                    gauge={
                        "axis": {"range": [0, 100], "tickwidth": 1},
                        "bar": {"color": "#667eea", "thickness": 0.3},
                        "bgcolor": "white",
                        "steps": [
                            {"range": [0, 40], "color": "#fee2e2"},
                            {"range": [40, 70], "color": "#fef3c7"},
                            {"range": [70, 100], "color": "#d1fae5"}
                        ],
                        "threshold": {
                            "line": {"color": "#667eea", "width": 4},
                            "thickness": 0.75,
                            "value": score
                        }
                    }
                ))
                fig_score.update_layout(height=300)
                st.plotly_chart(fig_score, width="stretch")
            
            with col_ig2:
                # Radar de indicadores
                categorias = ['DY', 'P/VP', 'Vacância', 'Patrimônio', 'Liquidez']
                dy_norm = min(dados.get('dy', 0) / 15 * 100, 100)
                pvp_norm = 100 - abs(dados.get('p_vp', 1) - 1) * 100
                pvp_norm = max(0, min(pvp_norm, 100))
                vac_norm = max(0, 100 - dados.get('vacancia', 0) * 5)
                pat_norm = min(dados.get('patrimonio', 0) / 2000000000 * 100, 100)
                liq_norm = min(dados.get('volume', 0) / 100000 * 100, 100)
                
                valores = [dy_norm, pvp_norm, vac_norm, pat_norm, liq_norm]
                
                fig_radar = go.Figure(data=go.Scatterpolar(
                    r=valores + [valores[0]],
                    theta=categorias + [categorias[0]],
                    fill='toself',
                    fillcolor='rgba(102, 126, 234, 0.3)',
                    line=dict(color='#667eea', width=2)
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=False,
                    height=300,
                    title="Perfil do FII"
                )
                st.plotly_chart(fig_radar, width="stretch")
        
        with tab3:
            st.subheader("📋 Informações Completas")
            
            # Cards informativos
            info_col1, info_col2 = st.columns(2)
            
            with info_col1:
                st.markdown("""
                <div class="info-box">
                    <h4>📊 Dados de Mercado</h4>
                </div>
                """, unsafe_allow_html=True)
                st.write(f"**Ticker:** {dados.get('ticker', 'N/A')}")
                st.write(f"**Nome:** {dados.get('nome', 'N/A')}")
                st.write(f"**Setor:** {dados.get('setor', 'N/A')}")
                st.write(f"**Moeda:** {dados.get('moeda', 'BRL')}")
                st.write(f"**Patrimônio:** R$ {dados.get('patrimonio', 0):,.2f}")
            
            with info_col2:
                st.markdown("""
                <div class="info-box">
                    <h4>💹 Indicadores</h4>
                </div>
                """, unsafe_allow_html=True)
                st.write(f"**DY (12M):** {dados.get('dy', 0):.2f}%")
                st.write(f"**P/VP:** {dados.get('p_vp', 0):.2f}")
                st.write(f"**Vacância:** {dados.get('vacancia', 0):.2f}%")
                st.write(f"**Volume:** {dados.get('volume', 0):,}")
                st.write(f"**Variação:** {dados.get('variacao', 0):+.2f}%")
            
            with st.expander("🔍 Ver dados brutos (JSON)"):
                st.json(dados)
        
        # Botões de ação
        st.markdown("---")
        col_a1, col_a2, col_a3 = st.columns(3)
        with col_a1:
            if st.button("📥 Adicionar à Carteira", width="stretch"):
                # Verificar se já existe
                carteira_atual = st.session_state.db.obter_carteira()
                ticker_add = dados.get('ticker', ticker)
                ja_existe = ticker_add in carteira_atual['ticker'].values if not carteira_atual.empty else False
                
                st.session_state.db.adicionar_fii(
                    ticker_add,
                    1,
                    dados.get('preco_atual') or dados.get('preco', 0)
                )
                
                if ja_existe:
                    st.success(f"✅ {ticker_add} unificado! +1 cota adicionada ao total.")
                else:
                    st.success(f"✅ {ticker_add} adicionado à carteira!")
        with col_a2:
            if st.button("📊 Comparar", width="stretch"):
                st.info("Vá para a aba 'Comparar FIIs' no menu lateral")
        with col_a3:
            if st.button("🔄 Atualizar", width="stretch"):
                st.rerun()
    
    # SEÇÃO: Top 10 Maior Volume
    st.markdown("---")
    st.markdown("""
    <div style="background: linear-gradient(135deg, #059669 0%, #10b981 100%); padding: 1.5rem; border-radius: 15px; margin-bottom: 1.5rem;">
        <h2 style="color: white; margin: 0; font-size: 1.8rem;">🔥 Top 10 FIIs - Maior Volume Hoje</h2>
        <p style="color: #d1fae5; margin: 0.5rem 0 0 0; font-size: 1rem;">Clique para buscar os artigos mais negociados do mercado em tempo real</p>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("🔍 Buscar Top 10 Maior Volume", type="primary", width="stretch", key="btn_top10"):
        with st.spinner("Buscando os 10 FIIs com maior volume negociado..."):
            # Lista ampla de FIIs populares para buscar
            fiis_para_buscar = [
                "MXRF11", "KNCR11", "CPTS11", "MCCI11", "RBRR11",
                "HGLG11", "XPML11", "KNRI11", "BTLG11", "IRDM11",
                "HSML11", "VISC11", "KNHY11", "TRXF11", "BRTF11",
                "CCRO11", "IVCB11", "LFTT11", "RURA11", "BPML11",
                "BRML11", "EGIE11", "ENEV11", "TAEE11", "TAPR11",
                "VIVR11", "VGIR11", "KNSC11", "BTCI11", "VRTM11",
                "MANA11", "GARE11", "SNEL11", "VGHF11", "KNCR11",
                "HGRU11", "HGRU11", "XPML11", "MXRF11", "CPTS11",
                "RECR11", "RENT11", "VILG11", "TRXL11", "MGFF11"
            ]
            
            # Remover duplicatas
            fiis_unicos = list(dict.fromkeys(fiis_para_buscar))
            
            import yfinance as yf
            resultados = []
            
            for ticker in fiis_unicos:
                try:
                    acao = yf.Ticker(f"{ticker}.SA")
                    hist = acao.history(period="1d")
                    
                    if not hist.empty:
                        preco = float(hist["Close"].iloc[-1])
                        volume = int(hist["Volume"].iloc[-1])
                        abertura = float(hist["Open"].iloc[-1])
                        maxima = float(hist["High"].iloc[-1])
                        minima = float(hist["Low"].iloc[-1])
                        variacao = ((preco - abertura) / abertura) * 100 if abertura > 0 else 0
                        
                        resultados.append({
                            "ticker": ticker,
                            "preco": preco,
                            "volume": volume,
                            "variacao": variacao,
                            "maxima": maxima,
                            "minima": minima
                        })
                except:
                    pass
            
            # Ordenar por volume (maior primeiro)
            resultados.sort(key=lambda x: x["volume"], reverse=True)
            top10 = resultados[:10]
        
        if top10:
            st.success(f"✅ Top 10 FIIs com maior volume negociado hoje!")
            
            # Exibir top 10
            for i, item in enumerate(top10):
                rank = i + 1
                cor_rank = "#fbbf24" if rank <= 3 else "#9ca3af"
                medalha = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
                
                cor_var = "#34d399" if item["variacao"] >= 0 else "#f87171"
                seta = "▲" if item["variacao"] >= 0 else "▼"
                
                # Card do FII
                st.markdown(f"""
                <div style="background: #1f2937; border: 1px solid #374151; border-left: 4px solid {cor_rank}; 
                            border-radius: 12px; padding: 1rem 1.5rem; margin-bottom: 0.8rem;
                            display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        <span style="font-size: 2rem; font-weight: 900; color: {cor_rank}; min-width: 50px;">{medalha}</span>
                        <div>
                            <span style="font-size: 1.6rem; font-weight: 800; color: #ffffff;">{item['ticker']}</span>
                            <div style="color: #9ca3af; font-size: 0.85rem; margin-top: 2px;">
                                Max: R$ {item['maxima']:.2f} | Min: R$ {item['minima']:.2f}
                            </div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.8rem; font-weight: 800; color: #667eea;">R$ {item['preco']:.2f}</div>
                        <div style="font-size: 1.1rem; font-weight: 700; color: {cor_var};">
                            {seta} {item['variacao']:+.2f}%
                        </div>
                    </div>
                    <div style="text-align: right; min-width: 150px;">
                        <div style="color: #9ca3af; font-size: 0.8rem; text-transform: uppercase;">Volume</div>
                        <div style="font-size: 1.3rem; font-weight: 700; color: #ffffff;">
                            {item['volume']:,}".replace(",", ".")
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Gráfico de volume
            st.markdown("---")
            st.subheader("📊 Comparativo de Volume")
            
            df_top10 = pd.DataFrame(top10)
            
            fig_vol = px.bar(
                df_top10, 
                x="ticker", 
                y="volume",
                title="Volume Negociado (Top 10)",
                color="volume",
                color_continuous_scale="Viridis",
                text_auto=".2s"
            )
            fig_vol.update_layout(
                height=400, 
                xaxis_title="", 
                yaxis_title="Volume",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white")
            )
            st.plotly_chart(fig_vol, width="stretch")
            
            # Gráfico de preço
            fig_preco = px.bar(
                df_top10, 
                x="ticker", 
                y="preco",
                title="Preço de Compra (R$)",
                color="preco",
                color_continuous_scale="RdYlGn",
                text_auto=".2f"
            )
            fig_preco.update_layout(
                height=400, 
                xaxis_title="", 
                yaxis_title="Preço (R$)",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white")
            )
            st.plotly_chart(fig_preco, width="stretch")
        else:
            st.error("❌ Não foi possível buscar os dados. Tente novamente.")


def exibir_watchlist():
    """Exibe watchlist de FIIs que o usuário quer comprar"""
    
    st.header("🎯 Watchlist - FIIs para Comprar")
    st.markdown("*Adicione os FIIs que você está de olho. O preço atual é buscado em tempo real.*")
    
    # CSS para a watchlist
    st.markdown("""
    <style>
    .wl-card {
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        background: #1f2937;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .wl-ticker {
        font-size: 1.5rem;
        font-weight: 800;
        color: #ffffff !important;
    }
    .wl-preco {
        font-size: 2rem;
        font-weight: 800;
        color: #667eea !important;
    }
    .wl-variacao-up { color: #34d399; font-weight: 700; font-size: 1.1rem; }
    .wl-variacao-down { color: #f87171; font-weight: 700; font-size: 1.1rem; }
    .wl-alerta-verde {
        background: #065f46; color: #34d399; padding: 6px 14px;
        border-radius: 20px; font-weight: 700; font-size: 0.9rem;
        display: inline-block; margin-top: 8px;
    }
    .wl-alerta-amarelo {
        background: #78350f; color: #fbbf24; padding: 6px 14px;
        border-radius: 20px; font-weight: 700; font-size: 0.9rem;
        display: inline-block; margin-top: 8px;
    }
    .wl-alerta-vermelho {
        background: #7f1d1d; color: #f87171; padding: 6px 14px;
        border-radius: 20px; font-weight: 700; font-size: 0.9rem;
        display: inline-block; margin-top: 8px;
    }
    .wl-info {
        color: #d1d5db !important; font-size: 0.9rem; margin-top: 6px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Formulário para adicionar
    with st.form("adicionar_watchlist", clear_on_submit=True):
        st.subheader("➕ Adicionar FII à Watchlist")
        col1, col2 = st.columns([1, 1])
        with col1:
            ticker = st.text_input("Ticker do FII", placeholder="Ex: MXRF11").upper()
        with col2:
            alerta_preco = st.number_input(
                "🔔 Alerta de Preço Baixo (R$)", 
                min_value=0.0, value=0.0, step=0.01,
                help="Se o preço cair até esse valor, será alertado. 0 = sem alerta."
            )
        
        if st.form_submit_button("➕ Adicionar à Watchlist", type="primary", width="stretch"):
            if ticker:
                st.session_state.db.adicionar_watchlist(ticker, alerta_preco if alerta_preco > 0 else None, "")
                st.success(f"✅ {ticker} adicionado à watchlist!")
                st.rerun()
            else:
                st.error("Digite um ticker válido!")
    
    st.markdown("---")
    
    # Carregar watchlist
    watchlist = st.session_state.db.obter_watchlist()
    
    if watchlist.empty:
        st.info("📝 Sua watchlist está vazia. Adicione FIIs acima que você está interessado em comprar.")
        return
    
    st.subheader(f"📋 {len(watchlist)} FII(s) na sua lista")
    
    # Auto-refresh
    col_rf, col_info = st.columns([1, 3])
    with col_rf:
        auto_refresh = st.checkbox("🔄 Auto-refresh (2 min)", value=False)
    with col_info:
        st.caption("Preços atualizados em tempo real via Yahoo Finance")
    
    if auto_refresh:
        import time
        time.sleep(120)
        st.rerun()
    
    # Buscar dados de cada FII
    dados_watchlist = []
    
    for _, row in watchlist.iterrows():
        ticker_wl = row["ticker"]
        alerta_preco_wl = row["preco_alvo"]
        
        dados = buscar_dados_tempo_real(ticker_wl)
        
        if "erro" not in dados:
            preco_atual = dados.get("preco_atual") or dados.get("preco", 0)
            dy = dados.get("dy", 0)
            variacao = dados.get("variacao", 0)
            score = calcular_score(dados)
            
            # Status do alerta
            status_alerta = ""
            if alerta_preco_wl and preco_atual > 0:
                if preco_atual <= alerta_preco_wl:
                    status_alerta = "comprar"
                elif preco_atual <= alerta_preco_wl * 1.05:
                    status_alerta = "perto"
                else:
                    status_alerta = "distante"
            
            dados_watchlist.append({
                "ticker": ticker_wl,
                "nome": dados.get("nome", ""),
                "preco_atual": preco_atual,
                "alerta_preco": alerta_preco_wl or 0,
                "variacao": variacao,
                "dy": dy,
                "p_vp": dados.get("p_vp", 0),
                "score": score,
                "status_alerta": status_alerta,
                "data_add": row["data_adicionado"]
            })
    
    # Exibir cada FII como card
    for item in dados_watchlist:
        # Cor da borda baseada no alerta
        if item["status_alerta"] == "comprar":
            cor_borda = "#10b981"
            bg_card = "#064e3b"
        elif item["status_alerta"] == "perto":
            cor_borda = "#f59e0b"
            bg_card = "#78350f"
        else:
            cor_borda = "#374151"
            bg_card = "#1f2937"
        
        cor_variacao = "#34d399" if item["variacao"] >= 0 else "#f87171"
        seta = "▲" if item["variacao"] >= 0 else "▼"
        
        # HTML do card
        alerta_html = ""
        if item["status_alerta"] == "comprar":
            alerta_html = f'<span class="wl-alerta-verde">🟢 PREÇO BAIXOU! ABAIXO DO ALERTA (R$ {item["alerta_preco"]:.2f})</span>'
        elif item["status_alerta"] == "perto":
            alerta_html = f'<span class="wl-alerta-amarelo">🟡 PERTO DO ALVO! Falta R$ {item["preco_atual"] - item["alerta_preco"]:.2f}</span>'
        elif item["alerta_preco"] > 0:
            alerta_html = f'<span class="wl-alerta-vermelho">🔴 Preço ainda acima do alerta (R$ {item["alerta_preco"]:.2f})</span>'
        
        st.markdown(f"""
        <div class="wl-card" style="border-left: 5px solid {cor_borda}; background: {bg_card};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <span class="wl-ticker">{item['ticker']}</span>
                    <span style="color: #9ca3af; margin-left: 12px; font-size: 0.95rem;">{item['nome']}</span>
                </div>
                <div style="text-align: right;">
                    <div class="wl-preco">R$ {item['preco_atual']:.2f}</div>
                    <span class="wl-variacao-{'up' if item['variacao'] >= 0 else 'down'}">{seta} {item['variacao']:+.2f}% hoje</span>
                </div>
            </div>
            <div class="wl-info">
                DY: <b>{item['dy']:.2f}%</b> &nbsp;|&nbsp; P/VP: <b>{item['p_vp']:.2f}</b> &nbsp;|&nbsp; Score: <b>{item['score']:.0f}/100</b>
                {f'&nbsp;|&nbsp; Alerta: <b style="color: #667eea;">R$ {item["alerta_preco"]:.2f}</b>' if item['alerta_preco'] > 0 else ''}
            </div>
            {alerta_html}
        </div>
        """, unsafe_allow_html=True)
        
        # Botões de ação
        col_b1, col_b2, col_b3, col_b4 = st.columns([3, 1, 1, 1])
        with col_b2:
            if st.button("🔍 Buscar", key=f"buscar_wl_{item['ticker']}", width="stretch"):
                st.session_state["busca_rapida"] = item['ticker']
                st.switch_page("app.py") if hasattr(st, 'switch_page') else st.rerun()
        with col_b3:
            if st.button("✏️ Alerta", key=f"editar_wl_{item['ticker']}", width="stretch"):
                st.session_state[f"editando_{item['ticker']}"] = True
                st.rerun()
        with col_b4:
            if st.button("🗑️ Remover", key=f"remover_wl_{item['ticker']}", width="stretch"):
                st.session_state.db.remover_watchlist(item['ticker'])
                st.rerun()
        
        # Formulário de edição inline
        if st.session_state.get(f"editando_{item['ticker']}", False):
            with st.form(f"editar_alerta_{item['ticker']}"):
                novo_alerta = st.number_input(
                    f"Novo alerta de preço para {item['ticker']}",
                    min_value=0.0, value=float(item['alerta_preco']),
                    step=0.01, key=f"input_alerta_{item['ticker']}"
                )
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    if st.form_submit_button("💾 Salvar", width="stretch"):
                        st.session_state.db.adicionar_watchlist(
                            item['ticker'], novo_alerta if novo_alerta > 0 else None, ""
                        )
                        st.session_state[f"editando_{item['ticker']}"] = False
                        st.rerun()
                with col_s2:
                    if st.form_submit_button("❌ Cancelar", width="stretch"):
                        st.session_state[f"editando_{item['ticker']}"] = False
                        st.rerun()
    
    # Gráfico comparativo
    if len(dados_watchlist) > 1:
        st.markdown("---")
        st.subheader("📊 Comparação")
        
        df_wl = pd.DataFrame(dados_watchlist)
        
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            fig_dy = px.bar(
                df_wl[df_wl["dy"] > 0], x="ticker", y="dy",
                title="DY (%)",
                color="dy", color_continuous_scale="Viridis",
                text_auto=".2f"
            )
            fig_dy.update_layout(height=350, xaxis_title="", yaxis_title="DY %")
            st.plotly_chart(fig_dy, width="stretch")
        
        with col_c2:
            fig_score = px.bar(
                df_wl, x="ticker", y="score",
                title="Score de Qualidade",
                color="score", color_continuous_scale="RdYlGn",
                text_auto=".0f"
            )
            fig_score.update_layout(height=350, xaxis_title="", yaxis_title="Score")
            st.plotly_chart(fig_score, width="stretch")


def exibir_comparacao():
    """Exibe comparação de FIIs"""
    st.header("⚖️ Comparar FIIs")
    
    # Selecionar FIIs
    fiis_selecionados = st.multiselect(
        "Selecione os FIIs para comparar",
        FIIS_POPULARES,
        default=["MXRF11", "KNCR11", "CPTS11"]
    )
    
    if fiis_selecionados:
        dados_lista = []
        
        for ticker in fiis_selecionados:
            with st.spinner(f"Buscando {ticker}..."):
                dados = st.session_state.api.buscar_fii(ticker)
                if "erro" not in dados:
                    dados["score"] = calcular_score(dados)
                    dados_lista.append(dados)
        
        if dados_lista:
            df = pd.DataFrame(dados_lista)
            
            # Tabela comparativa
            st.subheader("📊 Tabela Comparativa")
            st.dataframe(
                df[["ticker", "preco", "dy", "p_vp", "vacancia", "setor", "score"]].rename(columns={
                    "ticker": "Ticker",
                    "preco": "Preço (R$)",
                    "dy": "DY (%)",
                    "p_vp": "P/VP",
                    "vacancia": "Vacância (%)",
                    "setor": "Setor",
                    "score": "Score"
                }),
                width="stretch"
            )
            
            # Gráfico comparativo
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📈 Comparação de DY")
                fig = px.bar(
                    df,
                    x="ticker",
                    y="dy",
                    title="Dividend Yield (%)",
                    color="dy",
                    color_continuous_scale="Viridis"
                )
                st.plotly_chart(fig, width="stretch")
            
            with col2:
                st.subheader("📊 Comparação de P/VP")
                fig = px.bar(
                    df,
                    x="ticker",
                    y="p_vp",
                    title="P/VP",
                    color="p_vp",
                    color_continuous_scale="RdYlGn"
                )
                st.plotly_chart(fig, width="stretch")
            
            # Gráfico de score
            st.subheader("🏆 Ranking de Score")
            fig = px.bar(
                df.sort_values("score", ascending=True),
                x="score",
                y="ticker",
                orientation="h",
                title="Score de Qualidade",
                color="score",
                color_continuous_scale="Viridis"
            )
            st.plotly_chart(fig, width="stretch")


def exibir_configuracoes():
    """Exibe configurações"""
    st.header("⚙️ Configurações")
    
    st.subheader("📧 Alertas por Email")
    
    with st.form("config_email"):
        ativar_email = st.checkbox("Ativar alertas por email")
        email_destino = st.text_input("Email de destino")
        
        if st.form_submit_button("Salvar"):
            st.success("✅ Configurações salvas!")
    
    st.subheader("🔔 Notificações Telegram")
    
    with st.form("config_telegram"):
        ativar_telegram = st.checkbox("Ativar notificações Telegram")
        token_bot = st.text_input("Token do Bot")
        chat_id = st.text_input("Chat ID")
        
        if st.form_submit_button("Salvar"):
            st.success("✅ Configurações salvas!")
    
    st.subheader("⏰ Agendamento")
    
    with st.form("config_agendamento"):
        horario = st.time_input("Horário de atualização", value=datetime.strptime("18:00", "%H:%M").time())
        
        if st.form_submit_button("Salvar"):
            st.success("✅ Agendamento configurado!")


if __name__ == "__main__":
    main()
