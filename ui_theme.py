"""Tema visual no estilo Investidor10: fundo claro, verde #009974, cards de indicadores."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from investidor10 import formatar_compacto, formatar_numero, formatar_pct

FUNDO = "#F5F5F4"
SUPERFICIE = "#FFFFFF"
PRIMARIA = "#009974"
TEXTO = "#293038"
MUTED = "#5F6C7D"
GRADE = "#E3E6ED"
POSITIVO = "#009974"
NEGATIVO = "#ED1752"
FUNDOS_COR = "#009974"
ACOES_COR = "#4D81E7"

CORES_GRAFICO = [
    "#009974",
    "#4D81E7",
    "#CF6A17",
    "#10B981",
    "#59886B",
    "#A07D45",
    "#2299DD",
    "#ED1752",
]

TEMA_PLOTLY = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=TEXTO, size=13, family="Inter, sans-serif"),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.16),
    margin=dict(l=8, r=8, t=48, b=16),
    hoverlabel=dict(bgcolor=SUPERFICIE, font_size=12, bordercolor=GRADE),
    colorway=CORES_GRAFICO,
    title=dict(font=dict(size=15, color=TEXTO)),
)


def aplicar_plotly() -> None:
    px.defaults.template = "plotly_white"
    px.defaults.color_discrete_sequence = CORES_GRAFICO


def grafico(fig):
    fig.update_layout(**TEMA_PLOTLY)
    tipos = {getattr(tr, "type", "") for tr in fig.data}
    if tipos & {"bar", "scatter", "waterfall"}:
        fig.update_xaxes(gridcolor=GRADE, zerolinecolor=GRADE, linecolor=GRADE)
        fig.update_yaxes(gridcolor=GRADE, zerolinecolor=GRADE, linecolor=GRADE)
    return fig


def logo_app() -> None:
    st.logo(
        ":material/show_chart:",
        icon_image=":material/show_chart:",
        size="large",
    )


def pagina(titulo: str, descricao: str | None = None, selo: str | None = None) -> None:
    if selo:
        st.badge(selo, icon=":material/bolt:", color="green")
    st.header(titulo)
    if descricao:
        st.caption(descricao)


def metricas_em_cards(itens: list[dict], por_linha: int = 5) -> None:
    """Faixa de indicadores no estilo Investidor10 (rótulo pequeno, valor grande)."""
    if not itens:
        return
    for inicio in range(0, len(itens), por_linha):
        fatia = itens[inicio : inicio + por_linha]
        cols = st.columns(len(fatia), gap="small")
        for col, item in zip(cols, fatia):
            with col:
                with st.container(border=True):
                    st.metric(
                        item["label"],
                        item["valor"],
                        item.get("delta"),
                        help=item.get("ajuda"),
                    )


def cabecalho_ativo(
    ticker: str,
    nome: str | None,
    classe: str,
    dados: dict | None = None,
) -> None:
    """Cabeçalho de ativo: ticker + cards Cotação / DY / P/VP / Liquidez / Var 12M."""
    dados = dados or {}
    c1, c2 = st.columns([3, 1])
    with c1:
        st.header(ticker)
        extra = nome if nome and nome.upper() != ticker.upper() else None
        if extra:
            st.caption(extra)
    with c2:
        st.badge(
            "Fundo imobiliário" if classe in {"fundo", "fii"} else "Ação",
            icon=":material/apartment:" if classe in {"fundo", "fii"} else ":material/show_chart:",
            color="green" if classe in {"fundo", "fii"} else "blue",
        )
        if dados.get("gestao"):
            st.caption(f"Gestão {dados['gestao']}")
    metricas_em_cards(cards_resumo_i10(dados, classe), por_linha=5)
    extras = cards_detalhe_i10(dados, classe)
    if extras:
        metricas_em_cards(extras, por_linha=4)


def cards_resumo_i10(dados: dict, classe: str) -> list[dict]:
    preco = dados.get("preco_atual") if dados.get("preco_atual") is not None else dados.get("preco")
    var_dia = dados.get("variacao_dia")
    if var_dia is None:
        var_dia = dados.get("variacao")
    itens = [
        {
            "label": "Cotação",
            "valor": formatar_compacto(preco) if preco is not None else "N/D",
            "delta": f"{var_dia:+.2f}%".replace(".", ",") if var_dia is not None else None,
            "ajuda": "Preço do Investidor10 ou Yahoo.",
        },
        {
            "label": "DY (12M)",
            "valor": formatar_pct(dados.get("dy")),
        },
        {
            "label": "P/VP",
            "valor": formatar_numero(dados.get("p_vp")),
        },
        {
            "label": "Liquidez diária",
            "valor": formatar_compacto(dados.get("liquidez_diaria")),
            "ajuda": "Média dos últimos 30 dias no Investidor10.",
        },
        {
            "label": "Variação (12M)",
            "valor": formatar_pct(dados.get("variacao_12m")),
        },
    ]
    if classe in {"acao"} and dados.get("p_l") is not None:
        itens.insert(
            3,
            {"label": "P/L", "valor": formatar_numero(dados.get("p_l"))},
        )
        itens = itens[:5]
    return itens


def cards_detalhe_i10(dados: dict, classe: str) -> list[dict]:
    if classe not in {"fundo", "fii"}:
        return []
    cotistas = dados.get("cotistas")
    return [
        {
            "label": "Vacância",
            "valor": formatar_pct(dados.get("vacancia"), 2),
        },
        {
            "label": "VP / cota",
            "valor": formatar_compacto(dados.get("vp_cota")),
        },
        {
            "label": "Último rendimento",
            "valor": formatar_compacto(dados.get("ultimo_rendimento")),
        },
        {
            "label": "Taxa adm.",
            "valor": formatar_pct(dados.get("taxa_administracao"), 2),
        },
        {
            "label": "Cotistas",
            "valor": f"{int(cotistas):,}".replace(",", ".") if cotistas else "N/D",
        },
        {
            "label": "Cotas emitidas",
            "valor": (
                f"{int(dados['cotas_emitidas']):,}".replace(",", ".")
                if dados.get("cotas_emitidas")
                else "N/D"
            ),
        },
        {
            "label": "Patrimônio",
            "valor": formatar_compacto(dados.get("patrimonio")),
        },
        {
            "label": "Segmento",
            "valor": str(dados.get("setor") or dados.get("setor_final") or "N/D"),
        },
    ]


def card_grafico(titulo: str | None = None):
    box = st.container(border=True)
    if titulo:
        box.caption(titulo)
    return box
