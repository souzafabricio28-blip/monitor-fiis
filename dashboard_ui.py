"""Painel da carteira: KPIs, mix fundos/ações, treemap, ranking e tabelas."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from criterios import SETORES_ALVO, avaliar_diversificacao_setores, classe_ativo
from excel_export import exportar_carteira_bytes
from fiis_database import FIIS_POPULARES, buscar_fii_por_ticker
from market_data import buscar_cotacoes_lote
from portfolio import rentabilidade_total
from ui_theme import (
    ACOES_COR,
    FUNDOS_COR,
    GRADE,
    MUTED,
    NEGATIVO,
    POSITIVO,
    card_grafico,
    grafico,
    metricas_em_cards,
)

_VALOR_OCULTO = "R$ ••••••"


def _grafico(fig):
    return grafico(fig)


def partir_por_classe(itens):
    fundos, acoes = [], []
    for item in itens:
        if classe_ativo(item.get("ticker")) == "fundo":
            fundos.append(item)
        else:
            acoes.append(item)
    return fundos, acoes


def totais_de_itens(itens: list) -> dict:
    investido = 0.0
    atual = 0.0
    proventos = 0.0
    projecao = 0.0
    sem_cotacao = []
    for item in itens:
        qtd = int(item.get("qtd") or 0)
        compra = float(item.get("preco_compra") or 0)
        investido += qtd * compra
        if item.get("valor") is None:
            sem_cotacao.append(item.get("ticker"))
        else:
            atual += float(item["valor"])
        proventos += float(item.get("proventos") or 0)
        if item.get("projecao_mensal") is not None:
            projecao += float(item["projecao_mensal"])
    lucro = atual - investido if not sem_cotacao else None
    lucro_pct = (lucro / investido * 100) if lucro is not None and investido else None
    lucro_total, lucro_total_pct = rentabilidade_total(
        atual if not sem_cotacao else None, proventos, investido
    )
    dy_medio = (projecao * 12 / atual * 100) if atual > 0 else None
    return {
        "investido": investido,
        "atual": atual,
        "proventos": proventos,
        "projecao": projecao,
        "sem_cotacao": sem_cotacao,
        "lucro": lucro,
        "lucro_pct": lucro_pct,
        "lucro_total": lucro_total,
        "lucro_total_pct": lucro_total_pct,
        "dy_medio": dy_medio,
        "n": len(itens),
    }


def _txt_reais(valor, mostrar: bool) -> str:
    if not mostrar:
        return _VALOR_OCULTO
    if valor is None:
        return "N/D"
    return f"R$ {float(valor):,.2f}"


def _df_grupo(itens: list) -> pd.DataFrame:
    df = pd.DataFrame(itens)
    if df.empty:
        return df
    valores = pd.to_numeric(df.get("valor"), errors="coerce")
    soma = float(valores.sum()) if valores.notna().any() else 0.0
    df["peso"] = (valores / soma * 100) if soma else None
    df["lucro"] = df["lucro_preco"] if "lucro_preco" in df.columns else None
    df["lucro_pct"] = df["lucro_preco_pct"] if "lucro_preco_pct" in df.columns else None
    return df


def _maior_peso(df: pd.DataFrame):
    if df is None or df.empty or "peso" not in df.columns:
        return None, None
    validos = df.dropna(subset=["peso"])
    if validos.empty:
        return None, None
    linha = validos.loc[validos["peso"].idxmax()]
    return str(linha.get("ticker")), float(linha["peso"])


def kpis_da_carteira(totais: dict, mostrar_valores: bool) -> list[dict]:
    return [
        {
            "label": "Investido",
            "valor": _txt_reais(totais["investido"], mostrar_valores),
        },
        {
            "label": "Patrimônio",
            "valor": _txt_reais(totais["atual"], mostrar_valores),
            "delta": (
                f"{totais['lucro_pct']:+.2f}%"
                if totais["lucro_pct"] is not None
                else "parcial"
            ),
        },
        {
            "label": "Ganho de capital",
            "valor": _txt_reais(totais["lucro"], mostrar_valores),
        },
        {
            "label": "Rentab. total",
            "valor": _txt_reais(totais["lucro_total"], mostrar_valores),
            "delta": (
                f"{totais['lucro_total_pct']:+.2f}% preço+proventos"
                if totais["lucro_total_pct"] is not None
                else "parcial"
            ),
            "ajuda": "Preço + proventos registados. Cotação ausente permanece N/D.",
        },
        {
            "label": "Proventos 12m",
            "valor": _txt_reais(totais["proventos"], mostrar_valores),
        },
        {
            "label": "Projeção / mês",
            "valor": _txt_reais(totais["projecao"], mostrar_valores),
            "delta": f"DY {totais['dy_medio']:.2f}%" if totais.get("dy_medio") else "DY N/D",
        },
    ]


def _kpis(totais: dict, mostrar_valores: bool):
    metricas_em_cards(kpis_da_carteira(totais, mostrar_valores), por_linha=3)


def _fig_mix(totais_f: dict, totais_a: dict):
    vf = totais_f["atual"] or 0
    va = totais_a["atual"] or 0
    if vf <= 0 and va <= 0:
        return None
    fig = go.Figure(
        go.Pie(
            labels=["Fundos", "Ações"],
            values=[vf, va],
            hole=0.64,
            marker=dict(colors=[FUNDOS_COR, ACOES_COR]),
            textinfo="percent+label",
            hovertemplate="%{label}: R$ %{value:,.2f} (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        title="Mix da carteira",
        showlegend=False,
        annotations=[
            dict(
                text="alocação",
                x=0.5,
                y=0.5,
                font=dict(size=12, color=MUTED),
                showarrow=False,
            )
        ],
    )
    return _grafico(fig)


def _fig_treemap(df: pd.DataFrame, titulo: str):
    dados = df.dropna(subset=["valor"]).copy()
    if dados.empty:
        return None
    dados["setor"] = dados["setor"].fillna("N/D") if "setor" in dados.columns else "N/D"
    color_col = "lucro_pct" if "lucro_pct" in dados.columns and dados["lucro_pct"].notna().any() else "setor"
    kwargs = dict(path=["setor", "ticker"], values="valor", title=titulo)
    if color_col == "lucro_pct":
        kwargs.update(
            color="lucro_pct",
            color_continuous_scale=[NEGATIVO, "#EDF1F3", POSITIVO],
            color_continuous_midpoint=0,
        )
    else:
        kwargs.update(color="setor")
    fig = px.treemap(dados, **kwargs)
    fig.update_traces(hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>")
    fig.update_layout(coloraxis_colorbar=dict(title="Ganho %"))
    return _grafico(fig)


def _fig_setor(df: pd.DataFrame, titulo: str):
    dados = df.dropna(subset=["valor"]).copy()
    dados["setor"] = dados["setor"].fillna("N/D")
    agrupado = dados.groupby("setor", as_index=False)["valor"].sum().sort_values("valor")
    fig = px.bar(agrupado, x="valor", y="setor", orientation="h", title=titulo)
    fig.update_traces(marker_color=FUNDOS_COR, hovertemplate="%{y}: R$ %{x:,.2f}<extra></extra>")
    fig.update_layout(xaxis_title="Patrimônio (R$)", yaxis_title="")
    return _grafico(fig)


def _fig_ranking(df: pd.DataFrame, titulo: str):
    dados = df.dropna(subset=["lucro_pct"]).sort_values("lucro_pct")
    cores = [POSITIVO if v >= 0 else NEGATIVO for v in dados["lucro_pct"]]
    fig = go.Figure(
        go.Bar(
            x=dados["lucro_pct"],
            y=dados["ticker"],
            orientation="h",
            marker_color=cores,
            hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(title=titulo, xaxis_title="Ganho de capital %", yaxis_title="")
    return _grafico(fig)


def _fig_projecao(totais: dict):
    meses = list(range(1, 13))
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=meses,
            y=[totais["projecao"] * m for m in meses],
            name="Renda acumulada",
            marker_color=FUNDOS_COR,
            opacity=0.88,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=meses,
            y=[totais["investido"] + totais["projecao"] * m for m in meses],
            name="Patrimônio + renda",
            mode="lines+markers",
            line=dict(color=ACOES_COR, width=2.4),
        )
    )
    fig.update_layout(title="Projeção 12 meses", xaxis_title="Mês", yaxis_title="R$")
    return _grafico(fig)


def _fig_waterfall(totais: dict):
    fig = go.Figure(
        go.Waterfall(
            measure=["absolute", "relative", "relative", "total"],
            x=["Investido", "Ganho de capital", "Proventos 12m", "Resultado"],
            y=[
                totais["investido"] or 0,
                totais["lucro"] or 0,
                totais["proventos"] or 0,
                0,
            ],
            connector=dict(line=dict(color=GRADE)),
            increasing=dict(marker=dict(color=POSITIVO)),
            decreasing=dict(marker=dict(color=NEGATIVO)),
            totals=dict(marker=dict(color=FUNDOS_COR)),
            hovertemplate="%{x}: R$ %{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(title="Decompõe o resultado", showlegend=False)
    return _grafico(fig)


def _tabela_grupo(itens: list, rotulo_ticker: str, sufixo: str, mostrar_valores: bool):
    df = _df_grupo(itens)
    if df.empty:
        return
    f1, f2, f3 = st.columns(3)
    setores = ["Todos"] + sorted(s for s in df["setor"].dropna().unique().tolist() if s)
    setor_filtro = f1.selectbox("Setor", setores, key=f"setor_{sufixo}")
    opcoes_criterio = ["Todos"] + sorted(df["criterio"].dropna().unique().tolist())
    criterio_filtro = f2.selectbox("Critério", opcoes_criterio, key=f"criterio_{sufixo}")
    ordem = f3.selectbox(
        "Ordenar por",
        ["Peso %", "Ganho capital %", "Rentab. total %", rotulo_ticker],
        key=f"ordem_{sufixo}",
    )
    exibicao = df.copy()
    if setor_filtro != "Todos":
        exibicao = exibicao[exibicao["setor"] == setor_filtro]
    if criterio_filtro != "Todos":
        exibicao = exibicao[exibicao["criterio"] == criterio_filtro]
    mapa_ordem = {
        "Peso %": "peso",
        "Ganho capital %": "lucro_pct",
        "Rentab. total %": "lucro_total_pct",
        rotulo_ticker: "ticker",
    }
    col_ordem = mapa_ordem.get(ordem, "peso")
    if col_ordem in exibicao.columns:
        exibicao = exibicao.sort_values(
            col_ordem, ascending=(col_ordem == "ticker"), na_position="last"
        )

    visiveis = ["ticker", "setor", "qtd", "peso", "criterio", "dy", "lucro_pct", "lucro_total_pct"]
    if mostrar_valores:
        visiveis[3:3] = ["preco_compra", "preco_atual", "valor"]
        visiveis.extend(["lucro", "proventos", "lucro_total"])
    extras_i10 = [
        "p_vp",
        "vacancia",
        "liquidez_diaria",
        "cotistas",
        "vp_cota",
        "taxa_administracao",
        "ultimo_rendimento",
        "variacao_12m",
        "p_l",
    ]
    visiveis.extend(c for c in extras_i10 if c in exibicao.columns and exibicao[c].notna().any())
    visiveis = [c for c in visiveis if c in exibicao.columns]
    tabela = exibicao[visiveis].rename(
        columns={
            "ticker": rotulo_ticker,
            "setor": "Setor",
            "qtd": "Qtd",
            "peso": "Peso %",
            "preco_compra": "Preço compra",
            "preco_atual": "Preço atual",
            "valor": "Valor atual",
            "dy": "DY %",
            "criterio": "Critério",
            "lucro": "Ganho R$",
            "lucro_pct": "Ganho %",
            "proventos": "Proventos 12m",
            "lucro_total": "Rentab. total R$",
            "lucro_total_pct": "Rentab. total %",
            "p_vp": "P/VP",
            "vacancia": "Vacância %",
            "liquidez_diaria": "Liquidez 30d",
            "cotistas": "Cotistas",
            "vp_cota": "VP/cota",
            "taxa_administracao": "Taxa adm. %",
            "ultimo_rendimento": "Último rend.",
            "variacao_12m": "Var. 12M %",
            "p_l": "P/L",
        }
    )
    config = {
        rotulo_ticker: st.column_config.TextColumn(width="small"),
        "Setor": st.column_config.TextColumn(width="medium"),
        "Qtd": st.column_config.NumberColumn(format="%d"),
        "Peso %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
        "Preço compra": st.column_config.NumberColumn(format="R$ %.2f"),
        "Preço atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Valor atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "DY %": st.column_config.NumberColumn(format="%.2f"),
        "Ganho R$": st.column_config.NumberColumn(format="R$ %.2f"),
        "Ganho %": st.column_config.NumberColumn(format="%.2f%%"),
        "Proventos 12m": st.column_config.NumberColumn(format="R$ %.2f"),
        "Rentab. total R$": st.column_config.NumberColumn(format="R$ %.2f"),
        "Rentab. total %": st.column_config.NumberColumn(format="%.2f%%"),
        "Critério": st.column_config.TextColumn(width="small"),
        "P/VP": st.column_config.NumberColumn(format="%.2f"),
        "Vacância %": st.column_config.NumberColumn(format="%.2f"),
        "Liquidez 30d": st.column_config.NumberColumn(format="R$ %.0f"),
        "Cotistas": st.column_config.NumberColumn(format="%d"),
        "VP/cota": st.column_config.NumberColumn(format="R$ %.2f"),
        "Taxa adm. %": st.column_config.NumberColumn(format="%.2f"),
        "Último rend.": st.column_config.NumberColumn(format="R$ %.2f"),
        "Var. 12M %": st.column_config.NumberColumn(format="%.2f%%"),
        "P/L": st.column_config.NumberColumn(format="%.2f"),
    }
    st.dataframe(
        tabela,
        width="stretch",
        hide_index=True,
        column_config={k: v for k, v in config.items() if k in tabela.columns},
    )
    st.download_button(
        f"Baixar CSV — {rotulo_ticker}s",
        exibicao.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{sufixo}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        width="stretch",
        key=f"csv_{sufixo}",
    )


def _bloco_classe(itens: list, mostrar_valores: bool, sufixo: str, rotulo_ticker: str):
    if not itens:
        st.info(f"Nenhum {rotulo_ticker.lower()} na carteira.")
        return
    totais = totais_de_itens(itens)
    _kpis(totais, mostrar_valores)
    if totais["sem_cotacao"]:
        st.warning("Sem cotação: " + ", ".join(totais["sem_cotacao"]))
    df = _df_grupo(itens)
    ticker_top, peso_top = _maior_peso(df)
    if ticker_top and peso_top and peso_top >= 25:
        st.warning(
            f"Concentração: **{ticker_top}** pesa {peso_top:.1f}% deste bloco. "
            "Acima de 25% vale revisar o tamanho da posição."
        )
    df_grafico = df.dropna(subset=["valor"])
    g1, g2 = st.columns(2, gap="medium")
    with g1:
        with card_grafico():
            tree = _fig_treemap(df_grafico, "Alocação por setor e ticker") if not df_grafico.empty else None
            if tree is None:
                st.info("Sem cotações para o mapa de alocação.")
            else:
                st.plotly_chart(tree, width="stretch", key=f"tree_{sufixo}")
    with g2:
        with card_grafico():
            if df.dropna(subset=["lucro_pct"]).empty:
                st.info("Sem variação de preço para o ranking.")
            else:
                st.plotly_chart(
                    _fig_ranking(df, "Quem sobe e quem cai vs compra"),
                    width="stretch",
                    key=f"rank_{sufixo}",
                )
    g3, g4 = st.columns(2, gap="medium")
    with g3:
        with card_grafico():
            if df_grafico.empty:
                st.info("Sem dados de setor.")
            else:
                st.plotly_chart(
                    _fig_setor(df_grafico, "Patrimônio por setor"),
                    width="stretch",
                    key=f"setorbar_{sufixo}",
                )
    with g4:
        with card_grafico():
            if mostrar_valores:
                st.plotly_chart(
                    _fig_projecao(totais),
                    width="stretch",
                    key=f"proj_{sufixo}",
                )
            else:
                st.caption("Projeção oculta enquanto os valores financeiros estão escondidos.")
    _tabela_grupo(itens, rotulo_ticker, sufixo, mostrar_valores)


def _diversificacao(fundos: list):
    st.subheader("Diversificação dos fundos")
    st.caption("Meta do gestor: galpão, shopping, empresarial e papel (≥3). Ações não entram.")
    setores_fii = [
        item["setor"]
        for item in fundos
        if item.get("setor") not in {None, "N/D", "Ação"}
    ]
    div = avaliar_diversificacao_setores(setores_fii)
    presentes = set(div.get("presentes") or [])
    selos = st.columns(len(SETORES_ALVO), gap="small")
    for i, setor in enumerate(SETORES_ALVO):
        with selos[i]:
            if setor in presentes:
                st.badge(setor, icon=":material/check:", color="green")
            else:
                st.badge(setor, icon=":material/close:", color="orange")
    cols = st.columns(len(SETORES_ALVO), gap="medium")
    contagem = {}
    for setor in setores_fii:
        contagem[setor] = contagem.get(setor, 0) + 1
    for i, setor in enumerate(SETORES_ALVO):
        n = contagem.get(setor, 0)
        with cols[i]:
            with st.container(border=True):
                if setor in presentes:
                    st.metric(setor, f"{n} fundo(s)", "na meta")
                else:
                    st.metric(setor, "ausente", "faltando")
    if div["passou"]:
        st.success(
            f"Setores na meta: {', '.join(div['presentes']) or 'nenhum'}. "
            f"Ainda falta: {', '.join(div['faltando']) or 'nenhum'}."
        )
    else:
        st.warning(
            "Fundos concentrados — o plano de rebalanceamento entra em Shopping, "
            "Empresarial e Galpão para fechar a meta."
        )


def _exportacoes(analise: dict):
    st.caption("Excel e PDF da carteira inteira (fundos e ações no mesmo arquivo).")
    data_hoje = datetime.now().strftime("%Y%m%d")
    d1, d2 = st.columns(2)
    if d1.button("Gerar Excel", width="stretch", key="gerar_xlsx"):
        try:
            st.session_state["_xlsx_carteira"] = exportar_carteira_bytes(analise)
        except Exception:
            st.session_state["_xlsx_carteira"] = None
            st.caption("Excel indisponível.")
    if st.session_state.get("_xlsx_carteira"):
        d1.download_button(
            "Baixar Excel",
            st.session_state["_xlsx_carteira"],
            file_name=f"carteira_{data_hoje}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key="dl_xlsx",
        )
    if d2.button("Gerar PDF", width="stretch", key="gerar_pdf"):
        try:
            from pdf_report import gerar_relatorio_pdf_bytes

            st.session_state["_pdf_carteira"] = gerar_relatorio_pdf_bytes(analise)
        except Exception:
            st.session_state["_pdf_carteira"] = None
            st.caption("PDF indisponível.")
    if st.session_state.get("_pdf_carteira"):
        d2.download_button(
            "Baixar PDF",
            st.session_state["_pdf_carteira"],
            file_name=f"carteira_{data_hoje}.pdf",
            mime="application/pdf",
            width="stretch",
            key="dl_pdf",
        )


def _referencias():
    st.subheader("Fundos de referência")
    st.caption("Só busca cotações quando você pedir.")
    if st.button("Carregar referências", key="carregar_refs"):
        st.session_state["_refs_fiis"] = True
    if not st.session_state.get("_refs_fiis"):
        return
    ref = []
    lote = buscar_cotacoes_lote(FIIS_POPULARES[:6])
    for ticker in FIIS_POPULARES[:6]:
        dados = lote.get(ticker) or {}
        if not dados:
            continue
        ref.append(
            {
                "Ticker": ticker,
                "Preço": dados.get("preco_atual") or dados.get("preco"),
                "Setor": (buscar_fii_por_ticker(ticker) or {}).get("setor") or "N/A",
            }
        )
    if ref:
        st.dataframe(pd.DataFrame(ref), width="stretch", hide_index=True)
    else:
        st.info("Sem cotações de referência neste momento.")


def render_painel(itens: list, analise: dict, mostrar_valores: bool):
    """Painel executivo + abas de fundos e ações."""
    fundos, acoes = partir_por_classe(itens)
    totais = totais_de_itens(itens)
    totais_f = totais_de_itens(fundos)
    totais_a = totais_de_itens(acoes)

    s1, s2, s3 = st.columns([1, 1, 2], gap="small")
    with s1:
        st.badge(f"{len(fundos)} fundos", icon=":material/warehouse:", color="primary")
    with s2:
        st.badge(f"{len(acoes)} ações", icon=":material/show_chart:", color="orange")
    with s3:
        st.caption(
            "Cotações Yahoo em cache · fundamentos em Atualizar critérios / Indicadores "
            "(Investidor10, Fundamentus, Funds Explorer e outras)"
        )
    _kpis(totais, mostrar_valores)

    e1, e2, e3 = st.columns([1.1, 1.1, 1], gap="medium")
    with e1:
        with card_grafico():
            mix = _fig_mix(totais_f, totais_a)
            if mix is None:
                st.info("Sem cotações para o mix fundos × ações.")
            else:
                st.plotly_chart(mix, width="stretch", key="mix_carteira")
    with e2:
        with card_grafico():
            if mostrar_valores and totais["lucro"] is not None:
                st.plotly_chart(_fig_waterfall(totais), width="stretch", key="water_carteira")
            else:
                st.caption("Resultado consolidado oculta-se sem cotação completa ou com valores escondidos.")
                saude = {"APROVADO": 0, "REPROVADO": 0, "N/D": 0, "AÇÃO": 0}
                for item in itens:
                    chave = item.get("criterio") or "N/D"
                    saude[chave] = saude.get(chave, 0) + 1
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Aprovados", saude.get("APROVADO", 0))
                s2.metric("Reprovados", saude.get("REPROVADO", 0))
                s3.metric("N/D", saude.get("N/D", 0))
                s4.metric("Ações", saude.get("AÇÃO", 0))
    with e3:
        with st.container(border=True):
            ticker_top, peso_top = _maior_peso(_df_grupo(itens))
            st.metric("Posições", f"{totais['n']}")
            if ticker_top and peso_top is not None:
                st.metric("Maior posição", ticker_top, f"{peso_top:.1f}% do patrimônio")
                if peso_top >= 25:
                    st.warning(f"{ticker_top} concentra {peso_top:.1f}% da carteira.")
            vf = totais_f["atual"] or 0
            va = totais_a["atual"] or 0
            soma = vf + va
            if soma > 0:
                st.metric("Peso em fundos", f"{vf / soma * 100:.1f}%")
                st.metric("Peso em ações", f"{va / soma * 100:.1f}%")

    tab_f, tab_a = st.tabs(
        [f"Fundos imobiliários ({len(fundos)})", f"Ações ({len(acoes)})"]
    )
    with tab_f:
        _bloco_classe(fundos, mostrar_valores, "fundos", "Fundo")
    with tab_a:
        _bloco_classe(acoes, mostrar_valores, "acoes", "Ação")

    st.divider()
    _diversificacao(fundos)
    st.divider()
    _exportacoes(analise)
    st.divider()
    _referencias()
