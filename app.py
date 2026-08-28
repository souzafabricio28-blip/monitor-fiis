"""
Dashboard de Monitoramento de FIIs (Streamlit).
Usa db + market_data + investidor10 + criterios.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from auth import esta_autenticado, exigir_login, logout
from criterios import avaliar_ativo, avaliar_diversificacao
from db import USE_POSTGRES, DatabaseManager
from fiis_database import FIIS_POPULARES
from investidor10 import Investidor10API
from market_data import buscar_dados_completos
from portfolio import resumo_criterios

st.set_page_config(
    page_title="Monitor de FIIs",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: bold;
        color: #667eea;
        text-align: center;
        padding: 0.5rem;
    }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #d1d5db !important; }
    .stMetric {
        background-color: #1f2937 !important;
        padding: 1rem !important;
        border-radius: 10px;
        border: 1px solid #374151 !important;
    }
    .stMarkdown p, .stMarkdown span, .stMarkdown div, .stMarkdown label,
    .stMarkdown li, .stMarkdown td, .stMarkdown th { color: #ffffff !important; }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { color: #667eea !important; }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown span,
    [data-testid="stSidebar"] .stMarkdown div,
    [data-testid="stSidebar"] .stMarkdown label { color: #ffffff !important; }
    .stButton button { color: #ffffff !important; font-weight: 600 !important; }
    .stTextInput label, .stNumberInput label, .stSelectbox label,
    .stTextArea label, .stCheckbox label, .stRadio label { color: #d1d5db !important; }
    .stTextInput input, .stNumberInput input {
        color: #ffffff !important;
        background-color: #374151 !important;
    }
    hr { border-color: #374151 !important; }
</style>
""",
    unsafe_allow_html=True,
)


def calcular_score(dados: dict) -> float:
    score = 50
    dy = dados.get("dy", 0) or 0
    if dy >= 12:
        score += 15
    elif dy >= 10:
        score += 10
    elif dy >= 8:
        score += 5
    elif dy < 6:
        score -= 10

    pvp = dados.get("p_vp", 0) or 0
    if 0.8 <= pvp <= 1.0:
        score += 12
    elif 0.7 <= pvp < 0.8:
        score += 8
    elif pvp > 1.2:
        score -= 5

    vac = dados.get("vacancia", 0) or 0
    if vac < 5:
        score += 10
    elif vac < 10:
        score += 5
    elif vac > 20:
        score -= 10

    pl = dados.get("patrimonio", 0) or 0
    if pl > 1_000_000_000:
        score += 8
    elif pl > 500_000_000:
        score += 5

    setor = dados.get("setor", "") or ""
    if setor in ["Logístico", "Tijolo", "Logística/Galpão", "Shopping"]:
        score += 5
    elif setor == "Papel":
        score += 3

    return min(max(score, 0), 100)


def buscar_dados_tempo_real(ticker: str) -> dict:
    return buscar_dados_completos(ticker, db=st.session_state.db, usar_cache=True)


def status_badge(status: str) -> str:
    if status == "aprovado":
        return "APROVADO"
    if status == "reprovado":
        return "REPROVADO"
    return "N/D"


def main():
    # Login antes de qualquer dado de negócio
    exigir_login()

    st_autorefresh(interval=120_000, key="datarefresh")

    st.markdown('<h1 class="main-header">Monitor de FIIs</h1>', unsafe_allow_html=True)
    st.caption(
        f"Backend: {'PostgreSQL/Neon' if USE_POSTGRES else 'SQLite local'} · "
        f"Atualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    st.sidebar.title("Menu")
    if esta_autenticado():
        st.sidebar.caption(f"Logado: {st.session_state.get('auth_user', 'admin')}")
        if st.sidebar.button("Sair", width="stretch"):
            logout()
            st.rerun()

    opcao = st.sidebar.radio(
        "Navegação",
        [
            "Dashboard",
            "Carteira",
            "Buscar FII",
            "Critérios",
            "Watchlist",
            "Comparar FIIs",
            "Configurações",
        ],
    )

    if "api" not in st.session_state:
        st.session_state.api = Investidor10API()
    if "db" not in st.session_state:
        try:
            st.session_state.db = DatabaseManager()
        except Exception as e:
            st.error("Erro ao conectar no banco. Verifique DATABASE_URL no ambiente.")
            st.caption(str(e))
            st.stop()

    rotas = {
        "Dashboard": exibir_dashboard,
        "Carteira": exibir_carteira,
        "Buscar FII": exibir_buscar_fii,
        "Critérios": exibir_criterios,
        "Watchlist": exibir_watchlist,
        "Comparar FIIs": exibir_comparacao,
        "Configurações": exibir_configuracoes,
    }
    rotas[opcao]()


def _montar_carteira_enriquecida():
    carteira = st.session_state.db.obter_carteira()
    itens = []
    total_investido = 0.0
    valor_atual = 0.0
    rendimento_mensal = 0.0

    if carteira.empty:
        return itens, total_investido, valor_atual, rendimento_mensal

    for _, row in carteira.iterrows():
        ticker = row["ticker"]
        qtd = int(row["quantidade"])
        preco_compra = float(row["preco_compra"])
        total_investido += qtd * preco_compra

        dados = buscar_dados_tempo_real(ticker)
        if "erro" in dados:
            preco_atual = preco_compra
            dy = 0.0
            setor = "N/A"
        else:
            preco_atual = float(dados.get("preco_atual") or dados.get("preco") or preco_compra)
            dy = float(dados.get("dy") or 0)
            setor = dados.get("setor") or "N/A"

        valor = qtd * preco_atual
        valor_atual += valor
        rendimento_mensal += valor * (dy / 100) / 12 if dy else 0

        av = st.session_state.db.obter_avaliacao(ticker)
        if not av:
            try:
                av = avaliar_ativo(ticker)
                st.session_state.db.salvar_avaliacao(ticker, av)
            except Exception:
                av = None
        resumo = resumo_criterios(av) if av else {"status": "nd", "ok": 0, "fail": 0, "nd": 0}

        itens.append(
            {
                "ticker": ticker,
                "qtd": qtd,
                "preco_compra": preco_compra,
                "preco_atual": preco_atual,
                "valor": valor,
                "dy": dy,
                "setor": setor,
                "criterio": status_badge(resumo["status"]),
                "criterio_status": resumo["status"],
            }
        )

    return itens, total_investido, valor_atual, rendimento_mensal


def exibir_dashboard():
    st.header("Visão Geral")
    itens, total_investido, valor_atual, rendimento_mensal = _montar_carteira_enriquecida()
    lucro = valor_atual - total_investido
    lucro_pct = (lucro / total_investido * 100) if total_investido else 0
    dy_medio = (rendimento_mensal * 12 / valor_atual * 100) if valor_atual else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Investido", f"R$ {total_investido:,.2f}")
    c2.metric("Valor Atual", f"R$ {valor_atual:,.2f}", f"{lucro_pct:+.2f}%")
    c3.metric("Rendimento Mensal", f"R$ {rendimento_mensal:,.2f}")
    c4.metric("DY Anual Médio", f"{dy_medio:.2f}%")

    if not itens:
        st.info("Carteira vazia. Adicione FIIs na aba Carteira.")
        return

    df = pd.DataFrame(itens)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Composição")
        fig = px.pie(df, names="ticker", values="valor", hole=0.4)
        st.plotly_chart(fig, width="stretch")
    with col2:
        st.subheader("Projeção 12 meses")
        meses = list(range(1, 13))
        fig = go.Figure()
        fig.add_trace(
            go.Bar(x=meses, y=[rendimento_mensal * m for m in meses], name="Rendimento")
        )
        fig.add_trace(
            go.Scatter(
                x=meses,
                y=[total_investido + rendimento_mensal * m for m in meses],
                name="Patrimônio + rendimentos",
                mode="lines+markers",
            )
        )
        fig.update_layout(xaxis_title="Mês", yaxis_title="R$")
        st.plotly_chart(fig, width="stretch")

    st.subheader("Detalhes da Carteira")
    df["lucro"] = df["valor"] - (df["qtd"] * df["preco_compra"])
    df["lucro_pct"] = (df["lucro"] / (df["qtd"] * df["preco_compra"]) * 100).fillna(0)
    st.dataframe(
        df[
            [
                "ticker",
                "qtd",
                "preco_compra",
                "preco_atual",
                "valor",
                "dy",
                "criterio",
                "lucro",
                "lucro_pct",
            ]
        ].rename(
            columns={
                "ticker": "FII",
                "qtd": "Qtd",
                "preco_compra": "Preço Compra",
                "preco_atual": "Preço Atual",
                "valor": "Valor Atual",
                "dy": "DY %",
                "criterio": "Critério",
                "lucro": "Lucro R$",
                "lucro_pct": "Lucro %",
            }
        ),
        width="stretch",
    )

    try:
        avaliacoes = []
        for item in itens:
            av = st.session_state.db.obter_avaliacao(item["ticker"])
            if av:
                avaliacoes.append(av)
        if avaliacoes:
            div = avaliar_diversificacao(avaliacoes)
            st.subheader("Diversificação (critério do gestor)")
            st.write(
                f"Setores presentes: {', '.join(div['presentes']) or 'nenhum'} · "
                f"Meta: galpão, shopping, empresarial e papel (≥3)"
            )
            if div["passou"]:
                st.success("Carteira diversificada o suficiente.")
            else:
                st.warning("Carteira concentrada — avalie mesclar setores.")
    except Exception:
        pass

    st.subheader("FIIs de referência")
    ref = []
    for ticker in FIIS_POPULARES[:6]:
        dados = buscar_dados_tempo_real(ticker)
        if "erro" in dados:
            continue
        ref.append(
            {
                "Ticker": ticker,
                "Preço": dados.get("preco_atual") or dados.get("preco", 0),
                "DY %": dados.get("dy", 0),
                "P/VP": dados.get("p_vp", 0),
                "Setor": dados.get("setor", "N/A"),
            }
        )
    if ref:
        st.dataframe(pd.DataFrame(ref), width="stretch")


def exibir_carteira():
    st.header("Sua Carteira")

    with st.form("adicionar_fii", clear_on_submit=True):
        st.subheader("Adicionar FII")
        c1, c2, c3 = st.columns(3)
        ticker = c1.text_input("Ticker", "MXRF11").upper()
        quantidade = c2.number_input("Quantidade", min_value=1, value=10)
        preco = c3.number_input("Preço (R$)", min_value=0.01, value=9.00, step=0.01)
        if st.form_submit_button("Adicionar à Carteira", type="primary", width="stretch"):
            st.session_state.db.adicionar_fii(ticker, int(quantidade), float(preco))
            st.success(f"{ticker} adicionado (preço médio recalculado se já existia).")
            st.rerun()

    carteira = st.session_state.db.obter_carteira()
    if carteira.empty:
        st.info("Carteira vazia.")
        return

    for _, row in carteira.iterrows():
        ticker = row["ticker"]
        qtd = int(row["quantidade"])
        preco_compra = float(row["preco_compra"])
        total = qtd * preco_compra
        dados = buscar_dados_tempo_real(ticker)
        preco_atual = float(
            dados.get("preco_atual") or dados.get("preco") or preco_compra
        )
        lucro = qtd * preco_atual - total
        variacao = ((preco_atual - preco_compra) / preco_compra * 100) if preco_compra else 0

        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 0.5])
        c1.markdown(f"**{ticker}**")
        c2.write(f"{qtd} cotas")
        c3.write(f"R$ {preco_compra:.2f}")
        c4.write(f"R$ {total:,.2f}")
        c4.caption(f"{lucro:+,.2f} ({variacao:+.1f}%)")
        if c5.button("X", key=f"remover_{ticker}", width="stretch"):
            st.session_state.db.remover_fii(ticker)
            st.rerun()


def exibir_buscar_fii():
    st.header("Buscar FII")
    c1, c2 = st.columns([3, 1])
    ticker = c1.text_input("Ticker", "MXRF11").upper()
    buscar = c2.button("Buscar", type="primary", width="stretch")

    if not buscar:
        return

    with st.spinner("Buscando..."):
        dados = buscar_dados_tempo_real(ticker)

    if "erro" in dados:
        st.error(dados["erro"])
        return

    score = calcular_score(dados)
    try:
        av = avaliar_ativo(ticker)
        st.session_state.db.salvar_avaliacao(ticker, av)
        resumo = resumo_criterios(av)
    except Exception:
        av = None
        resumo = {"status": "nd", "ok": 0, "fail": 0, "nd": 0}

    preco = dados.get("preco_atual") or dados.get("preco", 0)
    st.subheader(f"{dados.get('ticker', ticker)} — {dados.get('nome', '')}")
    st.caption(f"{dados.get('fonte', '')} · {dados.get('horario_dados', '')}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço", f"R$ {float(preco):.2f}", f"{dados.get('variacao', 0):+.2f}%")
    c2.metric("DY Anual", f"{float(dados.get('dy', 0) or 0):.2f}%")
    c3.metric("P/VP", f"{float(dados.get('p_vp', 0) or 0):.2f}")
    c4.metric("Score / Critério", f"{score:.0f}/100 · {status_badge(resumo['status'])}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Vacância", f"{float(dados.get('vacancia', 0) or 0):.1f}%")
    c2.metric("Patrimônio", f"R$ {float(dados.get('patrimonio', 0) or 0):,.0f}")
    c3.metric("Setor", str(dados.get("setor", "N/A")))

    if av:
        st.subheader("Critérios do gestor")
        for crit in av.get("criterios", []):
            ok = crit.get("ok")
            if ok is True:
                st.success(f"{crit['crit']}: {crit['valor']}")
            elif ok is False:
                st.error(f"{crit['crit']}: {crit['valor']} — {crit.get('obs', '')}")
            else:
                st.info(f"{crit['crit']}: N/D — {crit.get('obs', '')}")

    a1, a2 = st.columns(2)
    if a1.button("Adicionar à Carteira", width="stretch"):
        st.session_state.db.adicionar_fii(ticker, 1, float(preco or 0))
        st.success("Adicionado.")
    if a2.button("Adicionar à Watchlist", width="stretch"):
        st.session_state.db.adicionar_watchlist(ticker)
        st.success("Na watchlist.")


def exibir_criterios():
    st.header("Critérios do gestor")
    st.markdown(
        """
**FIIs:** DY mensal 0,60–1,50% · Vacância ≤ 10% · P/VP 0,70–1,10 ·
liquidez acima da média · +10 anos de bolsa · diversificar galpão/shopping/empresarial/papel.

**Ações:** sem prejuízo 5 anos · liquidez · P/VP ≥ 0,60 · +10 anos · dívida < patrimônio · crescimento 10 anos.
"""
    )

    ticker = st.text_input("Avaliar ticker", "MXRF11").upper()
    if st.button("Avaliar", type="primary"):
        with st.spinner("Avaliando..."):
            av = avaliar_ativo(ticker)
            st.session_state.db.salvar_avaliacao(ticker, av)
        resumo = resumo_criterios(av)
        st.subheader(f"{ticker} — {status_badge(resumo['status'])}")
        st.write(
            f"Aprovados: {resumo['ok']} · Reprovados: {resumo['fail']} · N/D: {resumo['nd']}"
        )
        for crit in av.get("criterios", []):
            ok = crit.get("ok")
            linha = f"**{crit['crit']}** — {crit['valor']}"
            if crit.get("obs"):
                linha += f" ({crit['obs']})"
            if ok is True:
                st.success(linha)
            elif ok is False:
                st.error(linha)
            else:
                st.info(linha)

    st.divider()
    st.subheader("Carteira sob os critérios")
    carteira = st.session_state.db.obter_carteira()
    if carteira.empty:
        st.info("Carteira vazia.")
        return

    avaliacoes = []
    rows = []
    for _, row in carteira.iterrows():
        ticker = row["ticker"]
        av = st.session_state.db.obter_avaliacao(ticker)
        if not av:
            with st.spinner(f"Avaliando {ticker}..."):
                av = avaliar_ativo(ticker)
                st.session_state.db.salvar_avaliacao(ticker, av)
        avaliacoes.append(av)
        resumo = resumo_criterios(av)
        rows.append(
            {
                "Ticker": ticker,
                "Status": status_badge(resumo["status"]),
                "OK": resumo["ok"],
                "Fail": resumo["fail"],
                "N/D": resumo["nd"],
                "Setor": av.get("dados", {}).get("setor_final", ""),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch")
    div = avaliar_diversificacao(avaliacoes)
    st.write(f"Diversificação: {', '.join(div['presentes']) or 'nenhum setor principal'}")
    if div["passou"]:
        st.success("Diversificação OK (≥3 setores-alvo).")
    else:
        st.warning("Diversificação insuficiente.")


def exibir_watchlist():
    st.header("Watchlist")
    with st.form("add_wl", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ticker = c1.text_input("Ticker", placeholder="MXRF11").upper()
        alerta = c2.number_input("Alerta de preço baixo (R$)", min_value=0.0, value=0.0, step=0.01)
        if st.form_submit_button("Adicionar", type="primary", width="stretch") and ticker:
            st.session_state.db.adicionar_watchlist(
                ticker, alerta if alerta > 0 else None, ""
            )
            st.rerun()

    watchlist = st.session_state.db.obter_watchlist()
    if watchlist.empty:
        st.info("Watchlist vazia.")
        return

    for _, row in watchlist.iterrows():
        ticker = row["ticker"]
        alerta_preco = row["preco_alvo"]
        dados = buscar_dados_tempo_real(ticker)
        if "erro" in dados:
            st.warning(f"{ticker}: {dados['erro']}")
            continue
        preco = float(dados.get("preco_atual") or dados.get("preco") or 0)
        dy = float(dados.get("dy") or 0)
        score = calcular_score(dados)

        status = ""
        if alerta_preco and preco > 0:
            if preco <= float(alerta_preco):
                status = "PREÇO NO ALVO"
            elif preco <= float(alerta_preco) * 1.05:
                status = "Perto do alvo"
            else:
                status = "Acima do alerta"

        st.markdown(f"### {ticker}")
        st.write(
            f"R$ {preco:.2f} · DY {dy:.2f}% · Score {score:.0f}/100"
            + (f" · Alerta R$ {float(alerta_preco):.2f} ({status})" if alerta_preco else "")
        )
        if st.button("Remover", key=f"rm_wl_{ticker}"):
            st.session_state.db.remover_watchlist(ticker)
            st.rerun()


def exibir_comparacao():
    st.header("Comparar FIIs")
    selecionados = st.multiselect(
        "Selecione os FIIs",
        FIIS_POPULARES,
        default=FIIS_POPULARES[:3],
    )
    if not selecionados:
        return

    dados_lista = []
    for ticker in selecionados:
        with st.spinner(f"Buscando {ticker}..."):
            dados = buscar_dados_tempo_real(ticker)
            if "erro" in dados:
                continue
            dados["score"] = calcular_score(dados)
            if not dados.get("preco"):
                dados["preco"] = dados.get("preco_atual", 0)
            dados_lista.append(dados)

    if not dados_lista:
        st.warning("Sem dados.")
        return

    df = pd.DataFrame(dados_lista)
    cols = [c for c in ["ticker", "preco", "dy", "p_vp", "vacancia", "setor", "score"] if c in df.columns]
    st.dataframe(df[cols], width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        if "dy" in df.columns:
            st.plotly_chart(px.bar(df, x="ticker", y="dy", title="DY (%)"), width="stretch")
    with c2:
        if "p_vp" in df.columns:
            st.plotly_chart(px.bar(df, x="ticker", y="p_vp", title="P/VP"), width="stretch")


def exibir_configuracoes():
    st.header("Configurações")
    st.info(
        "Segredos (senha do app, DATABASE_URL, tokens) ficam só no Render/Neon — "
        "nunca no Git. Preferir TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no ambiente."
    )
    db = st.session_state.db
    cfg_email = db.get_config("email", {"ativar": False, "destino": ""})
    cfg_tg = db.get_config(
        "telegram",
        {"ativar": False, "token": "", "chat_id": ""},
    )
    cfg_agenda = db.get_config("agendamento", {"horario": "18:00"})

    token_env = bool(os.environ.get("TELEGRAM_TOKEN"))
    chat_env = bool(os.environ.get("TELEGRAM_CHAT_ID"))

    st.subheader("Alertas por Email")
    with st.form("config_email"):
        ativar_email = st.checkbox("Ativar email", value=bool(cfg_email.get("ativar")))
        email_destino = st.text_input("Email de destino", value=cfg_email.get("destino", ""))
        if st.form_submit_button("Salvar email"):
            db.set_config(
                "email",
                {"ativar": ativar_email, "destino": email_destino.strip()},
            )
            st.success("Email salvo no banco.")

    st.subheader("Telegram")
    if token_env or chat_env:
        st.success("Credenciais Telegram detectadas nas variáveis de ambiente (recomendado).")
    with st.form("config_telegram"):
        ativar_tg = st.checkbox("Ativar Telegram", value=bool(cfg_tg.get("ativar")))
        st.caption("Deixe em branco para manter o valor atual. Não exibimos o token salvo.")
        token = st.text_input("Token do Bot (novo)", value="", type="password")
        chat_id = st.text_input("Chat ID (novo)", value="")
        if st.form_submit_button("Salvar Telegram"):
            novo_token = token.strip() or cfg_tg.get("token", "")
            novo_chat = chat_id.strip() or cfg_tg.get("chat_id", "")
            db.set_config(
                "telegram",
                {
                    "ativar": ativar_tg,
                    "token": novo_token,
                    "chat_id": novo_chat,
                },
            )
            st.success("Preferências Telegram salvas (token não é exibido na tela).")

    st.subheader("Agendamento (referência)")
    with st.form("config_agendamento"):
        horario = st.text_input("Horário (HH:MM)", value=cfg_agenda.get("horario", "18:00"))
        if st.form_submit_button("Salvar horário"):
            db.set_config("agendamento", {"horario": horario.strip()})
            st.success("Horário salvo. Use o scheduler/cron no deploy para executar.")

    st.subheader("Ambiente (sem segredos)")
    st.code(
        json.dumps(
            {
                "postgres": USE_POSTGRES,
                "login_ativo": esta_autenticado(),
                "email_destino": (db.get_config("email") or {}).get("destino", ""),
                "telegram_ativado": bool((db.get_config("telegram") or {}).get("ativar"))
                or token_env,
                "telegram_via_env": token_env and chat_env,
                "agendamento": db.get_config("agendamento"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
