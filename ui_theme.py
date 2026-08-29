"""Tema visual compartilhado: cores, gráficos e blocos nativos do Streamlit."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

FUNDO = "#08090D"
SUPERFICIE = "#13151C"
PRIMARIA = "#6EE7B7"
TEXTO = "#F4F1EA"
GRADE = "#252A33"
POSITIVO = "#6EE7B7"
NEGATIVO = "#FB7185"
FUNDOS_COR = "#6EE7B7"
ACOES_COR = "#F5C16C"

CORES_GRAFICO = [
    "#6EE7B7",
    "#7DD3FC",
    "#F5C16C",
    "#F0A3B8",
    "#A5B4FC",
    "#FDBA74",
    "#67E8F9",
    "#FCA5A5",
]

TEMA_PLOTLY = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=TEXTO, size=13, family="Outfit, DM Sans, sans-serif"),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.16),
    margin=dict(l=8, r=8, t=48, b=16),
    hoverlabel=dict(bgcolor=SUPERFICIE, font_size=12, bordercolor=GRADE),
    colorway=CORES_GRAFICO,
    title=dict(font=dict(size=15, color=TEXTO)),
)


def aplicar_plotly() -> None:
    px.defaults.template = "plotly_dark"
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
        ":material/apartment:",
        icon_image=":material/apartment:",
        size="large",
    )


def pagina(titulo: str, descricao: str | None = None, selo: str | None = None) -> None:
    if selo:
        st.badge(selo, icon=":material/bolt:", color="primary")
    st.header(titulo)
    if descricao:
        st.caption(descricao)


def metricas_em_cards(itens: list[dict], por_linha: int = 3) -> None:
    """Cada KPI em um card com borda nativa (sem HTML)."""
    if not itens:
        return
    for inicio in range(0, len(itens), por_linha):
        fatia = itens[inicio : inicio + por_linha]
        cols = st.columns(len(fatia), gap="medium")
        for col, item in zip(cols, fatia):
            with col:
                with st.container(border=True):
                    st.metric(
                        item["label"],
                        item["valor"],
                        item.get("delta"),
                        help=item.get("ajuda"),
                    )


def card_grafico(titulo: str | None = None):
    box = st.container(border=True)
    if titulo:
        box.caption(titulo)
    return box
