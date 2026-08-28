"""
Dashboard de Monitoramento de FIIs (Streamlit).
Usa db + market_data + investidor10 + criterios.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from auth import esta_autenticado, exigir_login, logout
from criterios import avaliar_ativo, avaliar_diversificacao
from db import USE_POSTGRES, DatabaseManager
from fiis_database import FIIS_POPULARES
from investidor10 import Investidor10API
from market_data import buscar_dados_completos
from portfolio import analisar_carteira, resumo_criterios
from rebalanceamento import gerar_plano, registrar_plano_no_banco
from scoring import calcular_score

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

    st.markdown('<h1 class="main-header">Monitor de FIIs</h1>', unsafe_allow_html=True)
    st.caption(
        f"Backend: {'PostgreSQL/Neon' if USE_POSTGRES else 'SQLite local'} · "
        f"Atualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    st.sidebar.title("Menu")
    if st.sidebar.button("Atualizar dados agora", width="stretch"):
        st.rerun()
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
            "Rebalanceamento",
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
        "Rebalanceamento": exibir_rebalanceamento,
        "Buscar FII": exibir_buscar_fii,
        "Critérios": exibir_criterios,
        "Watchlist": exibir_watchlist,
        "Comparar FIIs": exibir_comparacao,
        "Configurações": exibir_configuracoes,
    }
    rotas[opcao]()


def _montar_carteira_enriquecida():
    analise = analisar_carteira(st.session_state.db)
    itens = []
    if "erro" in analise:
        return itens, analise
    for fii in analise["fiis"]:
        ticker = fii["ticker"]
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
                "qtd": fii["quantidade"],
                "preco_compra": fii["preco_compra"],
                "preco_atual": fii["preco_atual"],
                "valor": fii["valor_atual"],
                "dy": fii["dy"],
                "setor": (av or {}).get("dados", {}).get("setor_final") or "N/D",
                "criterio": status_badge(resumo["status"]),
                "criterio_status": resumo["status"],
                "status_dados": fii["status_dados"],
                "confianca": fii["confianca"],
                "fonte": fii["fonte"],
                "coletado_em": fii["coletado_em"],
                "divergencias": "; ".join(fii["divergencias"]) or "",
                "proventos": fii["proventos_registrados"],
                "projecao_mensal": fii["projecao_renda_mensal"],
            }
        )
    return itens, analise


_VALOR_OCULTO = "R$ ••••••"


def _alternar_visibilidade_valores():
    if "mostrar_valores_financeiros" not in st.session_state:
        st.session_state.mostrar_valores_financeiros = False
    rotulo = (
        "Ocultar valores"
        if st.session_state.mostrar_valores_financeiros
        else "Mostrar valores"
    )
    if st.button(rotulo, key="toggle_valores_financeiros", type="secondary"):
        st.session_state.mostrar_valores_financeiros = (
            not st.session_state.mostrar_valores_financeiros
        )
        st.rerun()


def exibir_dashboard():
    st.header("Visão Geral")
    with st.spinner("Atualizando análise única da carteira..."):
        itens, analise = _montar_carteira_enriquecida()
    if "erro" in analise:
        st.info(analise["erro"])
        return
    total_investido = analise["total_investido"]
    valor_atual = analise["total_atual"]
    rendimento_mensal = analise["projecao_renda_mensal"]
    lucro = analise["lucro"]
    lucro_pct = analise["rentabilidade"] if lucro is not None else None
    dy_medio = analise["dy_medio"]

    _alternar_visibilidade_valores()
    mostrar_valores = st.session_state.get("mostrar_valores_financeiros", False)

    c1, c2, c3, c4 = st.columns(4)
    if mostrar_valores:
        c1.metric("Total Investido", f"R$ {total_investido:,.2f}")
        c2.metric(
            "Valor Atual",
            f"R$ {valor_atual:,.2f}",
            f"{lucro_pct:+.2f}%" if lucro_pct is not None else "parcial",
        )
        c3.metric("Projeção Mensal", f"R$ {rendimento_mensal:,.2f}")
        c4.metric(
            "Proventos Registrados (12m)",
            f"R$ {analise['proventos_registrados']:,.2f}",
        )
    else:
        c1.metric("Total Investido", _VALOR_OCULTO)
        c2.metric("Valor Atual", _VALOR_OCULTO)
        c3.metric("Projeção Mensal", _VALOR_OCULTO)
        c4.metric("Proventos Registrados (12m)", _VALOR_OCULTO)

    if not itens:
        st.info("Carteira vazia. Adicione FIIs na aba Carteira.")
        return
    if analise["posicoes_sem_cotacao"]:
        st.warning(
            "Total atual parcial. Sem cotação: "
            + ", ".join(analise["posicoes_sem_cotacao"])
        )

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
    df["lucro_pct"] = df["lucro"] / (df["qtd"] * df["preco_compra"]) * 100
    f1, f2 = st.columns(2)
    setores = ["Todos"] + sorted(df["setor"].dropna().unique().tolist())
    setor_filtro = f1.selectbox("Filtrar por setor", setores)
    criterio_filtro = f2.selectbox(
        "Filtrar por critério", ["Todos", "APROVADO", "REPROVADO", "N/D"]
    )
    exibicao = df
    if setor_filtro != "Todos":
        exibicao = exibicao[exibicao["setor"] == setor_filtro]
    if criterio_filtro != "Todos":
        exibicao = exibicao[exibicao["criterio"] == criterio_filtro]
    st.dataframe(
        exibicao[
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
                "status_dados",
                "confianca",
                "fonte",
                "divergencias",
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
                "status_dados": "Status Dados",
                "confianca": "Confiança",
                "fonte": "Fonte",
                "divergencias": "Divergências",
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

    with st.form("registrar_movimentacao", clear_on_submit=True):
        st.subheader("Registrar movimentação")
        c0, c1, c2, c3 = st.columns(4)
        tipo = c0.selectbox("Tipo", ["COMPRA", "VENDA"])
        ticker = c1.text_input("Ticker", "MXRF11").upper()
        quantidade = c2.number_input("Quantidade", min_value=1, value=10)
        preco = c3.number_input("Preço (R$)", min_value=0.01, value=9.00, step=0.01)
        c4, c5 = st.columns(2)
        taxas = c4.number_input("Taxas (R$)", min_value=0.0, value=0.0, step=0.01)
        data_mov = c5.date_input("Data")
        if st.form_submit_button("Registrar", type="primary", width="stretch"):
            try:
                st.session_state.db.registrar_movimentacao(
                    ticker,
                    tipo,
                    int(quantidade),
                    float(preco),
                    float(taxas),
                    data_mov.isoformat(),
                )
                st.success(f"{tipo} de {ticker} registrada e preço médio recalculado.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

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
        preco_valor = dados.get("preco_atual")
        preco_atual = float(preco_valor) if preco_valor is not None else None
        lucro = qtd * preco_atual - total if preco_atual is not None else None
        variacao = (
            (preco_atual - preco_compra) / preco_compra * 100
            if preco_atual is not None and preco_compra
            else None
        )

        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
        c1.markdown(f"**{ticker}**")
        c2.write(f"{qtd} cotas")
        c3.write(f"R$ {preco_compra:.2f}")
        c4.write(f"R$ {total:,.2f}")
        c4.caption(
            f"{lucro:+,.2f} ({variacao:+.1f}%)"
            if lucro is not None
            else "Cotação indisponível — ganho N/D"
        )
        if c5.button(
            "Encerrar ao PM",
            key=f"remover_{ticker}",
            help="Registra a venda total pelo preço médio atual; prefira a venda com preço real no formulário.",
            width="stretch",
        ):
            st.session_state.db.remover_fii(ticker)
            st.rerun()

    with st.expander("Histórico auditável de movimentações"):
        movimentos = st.session_state.db.obter_movimentacoes()
        st.dataframe(movimentos, width="stretch", hide_index=True)


def exibir_rebalanceamento():
    st.header("Plano de Rebalanceamento")
    st.caption(
        "Roteiro sugerido pelos critérios do gestor. Execute na corretora e confirme "
        "aqui para atualizar carteira e histórico."
    )
    db = st.session_state.db
    meta = db.get_config("plano_rebalanceamento_meta") or {}
    plano = db.obter_plano_rebalanceamento()

    c1, c2 = st.columns(2)
    if c1.button("Gerar / atualizar plano", type="primary", width="stretch"):
        with st.spinner("Calculando preços e quantidades..."):
            resultado = registrar_plano_no_banco(db)
        st.success(
            f"Plano registrado com {resultado['inseridos']} movimentações pendentes."
        )
        st.rerun()
    if c2.button("Recarregar tela", width="stretch"):
        st.rerun()

    if plano.empty:
        st.info(
            "Nenhum plano pendente. Clique em **Gerar / atualizar plano** para registrar "
            "as vendas e compras sugeridas com base na sua carteira atual."
        )
        return

    if meta:
        st.write(f"**{meta.get('titulo', 'Plano')}** · criado em {meta.get('criado_em', 'N/D')}")
        resumo = meta.get("resumo") or {}
        m1, m2, m3 = st.columns(3)
        m1.metric("Vendas planejadas", resumo.get("vendas", 0))
        m2.metric("Compras planejadas", resumo.get("compras", 0))
        m3.metric("Fases", resumo.get("fases", 3))

    manter = meta.get("manter") or []
    if manter:
        st.subheader("Manter")
        for item in manter:
            st.success(f"**{item['ticker']}** — {item['motivo']}")

    decisoes = meta.get("decisoes") or []
    if decisoes:
        st.subheader("Decisão separada")
        for item in decisoes:
            st.warning(f"**{item['ticker']}** — {item['motivo']}")

    pendentes = plano[plano["status"] == "pendente"] if "status" in plano.columns else plano
    executados = (
        plano[plano["status"] == "executado"] if "status" in plano.columns else pd.DataFrame()
    )
    st.subheader(f"Pendente ({len(pendentes)})")
    if pendentes.empty:
        st.success("Todas as movimentações do plano foram executadas.")
    else:
        for fase in sorted(pendentes["fase"].unique()):
            st.markdown(f"### Fase {int(fase)}")
            fatia = pendentes[pendentes["fase"] == fase]
            for _, item in fatia.iterrows():
                tipo = item["tipo"]
                ticker = item["ticker"]
                qtd = int(item["quantidade"])
                preco_ref = item.get("preco_referencia")
                valor = item.get("valor_estimado")
                par = item.get("par_ticker") or ""
                icone = "VENDA" if tipo == "VENDA" else "COMPRA"
                st.markdown(
                    f"**{icone} {ticker}** — {qtd} cotas"
                    + (f" · ref. R$ {float(preco_ref):.2f}" if pd.notna(preco_ref) else "")
                    + (f" · ~R$ {float(valor):,.2f}" if pd.notna(valor) else "")
                    + (f" → par: **{par}**" if par else "")
                )
                st.caption(str(item.get("motivo") or ""))
                with st.expander(f"Confirmar {tipo} de {ticker} na corretora"):
                    preco_default = float(preco_ref) if pd.notna(preco_ref) else 10.0
                    with st.form(f"exec_plano_{item['id']}"):
                        preco_exec = st.number_input(
                            "Preço executado (R$)",
                            min_value=0.01,
                            value=preco_default,
                            step=0.01,
                            key=f"preco_{item['id']}",
                        )
                        taxas = st.number_input(
                            "Taxas (R$)",
                            min_value=0.0,
                            value=0.0,
                            step=0.01,
                            key=f"taxas_{item['id']}",
                        )
                        if st.form_submit_button(
                            f"Registrar {tipo} executada",
                            type="primary",
                            width="stretch",
                        ):
                            try:
                                db.executar_item_plano(
                                    int(item["id"]),
                                    float(preco_exec),
                                    float(taxas),
                                )
                                st.success(f"{tipo} de {ticker} registrada na carteira.")
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))

    if not executados.empty:
        st.subheader(f"Executado ({len(executados)})")
        st.dataframe(
            executados[
                [
                    c
                    for c in [
                        "fase",
                        "tipo",
                        "ticker",
                        "quantidade",
                        "preco_referencia",
                        "valor_estimado",
                        "par_ticker",
                        "executado_em",
                    ]
                    if c in executados.columns
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Checklist para a corretora")
    checklist = []
    for _, item in pendentes.iterrows():
        checklist.append(
            {
                "Fase": int(item["fase"]),
                "Ordem": int(item["ordem"]),
                "Ação": item["tipo"],
                "Ticker": item["ticker"],
                "Qtd": int(item["quantidade"]),
                "Preço ref.": f"R$ {float(item['preco_referencia']):.2f}"
                if pd.notna(item.get("preco_referencia"))
                else "N/D",
                "Par": item.get("par_ticker") or "",
                "Status": item.get("status"),
            }
        )
    if checklist:
        st.dataframe(pd.DataFrame(checklist), width="stretch", hide_index=True)


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

    preco = dados.get("preco_atual")
    st.subheader(f"{dados.get('ticker', ticker)} — {dados.get('nome', '')}")
    st.caption(
        f"{dados.get('fonte', '')} · {dados.get('horario_dados', '')} · "
        f"status {dados.get('status_geral', 'N/D')} · confiança {dados.get('confianca', 'N/D')}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Preço",
        f"R$ {float(preco):.2f}" if preco is not None else "N/D",
        f"{dados.get('variacao', 0):+.2f}%" if preco is not None else None,
    )
    c2.metric(
        "DY Anual",
        f"{float(dados['dy']):.2f}%" if dados.get("dy") is not None else "N/D",
    )
    c3.metric(
        "P/VP",
        f"{float(dados['p_vp']):.2f}" if dados.get("p_vp") is not None else "N/D",
    )
    c4.metric("Score / Critério", f"{score:.0f}/100 · {status_badge(resumo['status'])}")

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Vacância",
        f"{float(dados['vacancia']):.1f}%"
        if dados.get("vacancia") is not None
        else "N/D",
    )
    c2.metric(
        "Patrimônio",
        f"R$ {float(dados['patrimonio']):,.0f}"
        if dados.get("patrimonio") is not None
        else "N/D",
    )
    c3.metric("Setor", str(dados.get("setor") or "N/D"))

    if dados.get("divergencias"):
        st.warning(" · ".join(dados["divergencias"]))
    with st.expander("Auditoria das fontes"):
        qualidade = pd.DataFrame.from_dict(dados.get("qualidade", {}), orient="index")
        st.dataframe(qualidade, width="stretch")

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
        if preco is None:
            st.error("Não é possível comprar sem uma cotação válida.")
        else:
            st.session_state.db.adicionar_fii(ticker, 1, float(preco))
            st.success("Compra registrada.")
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
    cfg_tg = db.get_config("telegram", {"ativar": False}) or {"ativar": False}
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
    if token_env and chat_env:
        st.success("Credenciais Telegram detectadas nas variáveis de ambiente (recomendado).")
    else:
        st.warning(
            "Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no ambiente para ativar alertas."
        )
    with st.form("config_telegram"):
        ativar_tg = st.checkbox("Ativar Telegram", value=bool(cfg_tg.get("ativar")))
        if st.form_submit_button("Salvar Telegram"):
            if ativar_tg and not (token_env and chat_env):
                st.error("Credenciais ausentes no ambiente; Telegram não foi ativado.")
            else:
                db.set_config("telegram", {"ativar": ativar_tg})
                st.success("Preferência Telegram salva; nenhum segredo foi gravado no banco.")

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
