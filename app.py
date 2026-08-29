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
import streamlit as st

from auth import esta_autenticado, exigir_login, logout
from criterios import avaliar_ativo, avaliar_diversificacao_setores, classe_ativo, eh_fii
from dashboard_ui import render_painel
from db import USE_POSTGRES, DatabaseManager
from fiis_database import FIIS_POPULARES, buscar_fii_por_ticker
from market_data import (
    buscar_cotacoes_lote,
    buscar_dados_completos,
    buscar_historico,
    limpar_cache_memoria,
    sincronizar_proventos,
)
from portfolio import analisar_carteira, resumo_criterios
from queda_report import (
    LIMITE_QUEDA_PCT,
    gatilhos_de_queda,
    verificar_quedas_carteira,
)
from rebalanceamento import registrar_plano_no_banco
from scoring import calcular_score
from seed_local import garantir_carteira_local, garantir_plano_local
from telegram_notifier import verificar_alertas_watchlist
from ui_theme import aplicar_plotly, cabecalho_ativo, grafico as _grafico, logo_app, pagina

st.set_page_config(
    page_title="Monitor de FIIs",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

aplicar_plotly()


def buscar_dados_tempo_real(ticker: str, completo: bool = False) -> dict:
    return buscar_dados_completos(
        ticker,
        db=st.session_state.db,
        usar_cache=True,
        incluir_fundamentos=completo,
    )


def _invalidar_analise():
    st.session_state.pop("_dashboard_cache", None)


def _tabela_criterios(av: dict) -> pd.DataFrame:
    linhas = []
    for crit in av.get("criterios") or []:
        ok = crit.get("ok")
        if ok is True:
            resultado = "OK"
        elif ok is False:
            resultado = "REPROVADO"
        else:
            resultado = "N/D"
        linhas.append(
            {
                "Critério": crit.get("crit"),
                "Valor": crit.get("valor"),
                "Resultado": resultado,
                "Obs": crit.get("obs") or "",
            }
        )
    return pd.DataFrame(linhas)


def status_badge(status: str) -> str:
    if status == "aprovado":
        return "APROVADO"
    if status == "reprovado":
        return "REPROVADO"
    if status == "acao":
        return "AÇÃO"
    return "N/D"


def _resumo_posicao(ticker: str, av: dict | None, forcar: bool):
    """Usa catálogo/cache no dashboard; só raspa a web se o utilizador pedir."""
    curado = buscar_fii_por_ticker(ticker)
    if forcar:
        try:
            av = avaliar_ativo(ticker, permitir_scrape=True)
            st.session_state.db.salvar_avaliacao(ticker, av)
        except Exception:
            pass
    if av:
        tipo = (av.get("tipo") or "").lower()
        if tipo == "ação" or tipo == "acao":
            return av, {
                "status": "acao",
                "ok": 0,
                "fail": 0,
                "nd": 0,
            }, av.get("dados", {}).get("setor_final") or "Ação"
        resumo = resumo_criterios(av)
        setor = av.get("dados", {}).get("setor_final") or (curado or {}).get("setor") or "N/D"
        return av, resumo, setor
    if not eh_fii(ticker):
        return None, {"status": "acao", "ok": 0, "fail": 0, "nd": 0}, "Ação"
    return None, {"status": "nd", "ok": 0, "fail": 0, "nd": 0}, (curado or {}).get("setor") or "N/D"


def main():
    # Login antes de qualquer dado de negócio
    exigir_login()
    logo_app()

    with st.sidebar:
        st.markdown("**Monitor de FIIs**")
        st.caption("Resumo · indicadores · checklist")
        st.divider()
        if st.button("Atualizar cotações", width="stretch", type="primary"):
            st.session_state["forcar_cotacoes"] = True
            _invalidar_analise()
            limpar_cache_memoria()
            st.rerun()
        if st.button("Atualizar critérios", width="stretch"):
            st.session_state["forcar_criterios"] = True
            st.rerun()
        if esta_autenticado():
            st.caption(f"Sessão: {st.session_state.get('auth_user', 'admin')}")
            if st.button("Sair", width="stretch"):
                logout()
                st.rerun()
        st.divider()
        opcao = st.radio(
            "Navegação",
            [
                "Resumo",
                "Dividendos",
                "Carteira",
                "Rebalanceamento",
                "Indicadores",
                "Checklist",
                "Quedas 10%",
                "Watchlist",
                "Comparador",
                "Vigia",
                "Configurações",
            ],
        )
        st.caption(
            f"{'PostgreSQL/Neon' if USE_POSTGRES else 'SQLite local'} · "
            f"{datetime.now().strftime('%d/%m %H:%M')}"
        )

    if "db" not in st.session_state:
        try:
            st.session_state.db = DatabaseManager()
            garantir_carteira_local(st.session_state.db)
        except Exception as e:
            st.error("Erro ao conectar no banco. Verifique DATABASE_URL no ambiente.")
            st.caption(str(e))
            st.stop()
    if not st.session_state.get("_plano_local_ok"):
        garantir_plano_local(st.session_state.db)
        st.session_state["_plano_local_ok"] = True

    rotas = {
        "Resumo": exibir_dashboard,
        "Dividendos": exibir_proventos,
        "Carteira": exibir_carteira,
        "Rebalanceamento": exibir_rebalanceamento,
        "Indicadores": exibir_buscar_fii,
        "Checklist": exibir_criterios,
        "Quedas 10%": exibir_quedas,
        "Watchlist": exibir_watchlist,
        "Comparador": exibir_comparacao,
        "Vigia": exibir_vigia,
        "Configurações": exibir_configuracoes,
    }
    rotas[opcao]()


def _montar_carteira_enriquecida(max_idade_min: int = 20):
    analise = analisar_carteira(st.session_state.db, max_idade_min=max_idade_min)
    itens = []
    if "erro" in analise:
        return itens, analise
    forcar = bool(st.session_state.pop("forcar_criterios", False))
    for fii in analise["fiis"]:
        ticker = fii["ticker"]
        av = st.session_state.db.obter_avaliacao(ticker)
        av, resumo, setor = _resumo_posicao(ticker, av, forcar)
        dados_av = (av or {}).get("dados") or {}

        itens.append(
            {
                "ticker": ticker,
                "qtd": fii["quantidade"],
                "preco_compra": fii["preco_compra"],
                "preco_atual": fii["preco_atual"],
                "valor": fii["valor_atual"],
                "dy": fii["dy"],
                "setor": setor,
                "criterio": status_badge(resumo["status"]),
                "criterio_status": resumo["status"],
                "status_dados": fii["status_dados"],
                "confianca": fii["confianca"],
                "fonte": fii["fonte"],
                "coletado_em": fii["coletado_em"],
                "divergencias": "; ".join(fii["divergencias"]) or "",
                "proventos": fii["proventos_registrados"],
                "projecao_mensal": fii["projecao_renda_mensal"],
                "lucro_preco": fii.get("lucro"),
                "lucro_preco_pct": fii.get("lucro_pct"),
                "lucro_total": fii.get("lucro_com_dividendos"),
                "lucro_total_pct": fii.get("lucro_com_dividendos_pct"),
                "classe": "Fundo" if classe_ativo(ticker) == "fundo" else "Ação",
                "p_vp": dados_av.get("p_vp"),
                "vacancia": dados_av.get("vacancia"),
                "liquidez_diaria": dados_av.get("liquidez_diaria"),
                "cotistas": dados_av.get("cotistas"),
                "ultimo_rendimento": dados_av.get("ultimo_rendimento"),
                "variacao_12m": dados_av.get("variacao_12m"),
                "p_l": dados_av.get("p_l"),
            }
        )
    return itens, analise


def _partir_df_por_classe(df: pd.DataFrame, col: str = "ticker"):
    """Parte um DataFrame em (fundos, ações) pelo ticker."""
    if df is None or df.empty or col not in df.columns:
        vazio = df.iloc[0:0] if df is not None else pd.DataFrame()
        return vazio, vazio
    mask = df[col].map(lambda t: classe_ativo(str(t)) == "fundo")
    return df.loc[mask].copy(), df.loc[~mask].copy()


def _alternar_visibilidade_valores():
    db = st.session_state.db
    if "mostrar_valores_financeiros" not in st.session_state:
        salvo = db.get_config("mostrar_valores_financeiros", False)
        st.session_state.mostrar_valores_financeiros = bool(salvo)
    rotulo = (
        "Ocultar valores"
        if st.session_state.mostrar_valores_financeiros
        else "Mostrar valores"
    )
    if st.button(rotulo, key="toggle_valores_financeiros", type="secondary"):
        novo = not st.session_state.mostrar_valores_financeiros
        st.session_state.mostrar_valores_financeiros = novo
        db.set_config("mostrar_valores_financeiros", novo)
        st.rerun()


def exibir_dashboard():
    pagina(
        "Resumo da carteira",
        "Patrimônio, mix fundos × ações e indicadores no estilo Investidor10.",
        selo="Ao vivo",
    )
    forcar_cot = bool(st.session_state.pop("forcar_cotacoes", False))
    forcar_crit = bool(st.session_state.get("forcar_criterios", False))
    cache_dash = st.session_state.get("_dashboard_cache")
    if cache_dash and not forcar_cot and not forcar_crit:
        itens, analise = cache_dash["itens"], cache_dash["analise"]
    else:
        with st.spinner("Atualizando cotações da carteira..."):
            itens, analise = _montar_carteira_enriquecida(
                max_idade_min=0 if forcar_cot else 20
            )
        if "erro" not in analise:
            st.session_state["_dashboard_cache"] = {"itens": itens, "analise": analise}
    if "erro" in analise:
        st.info(analise["erro"])
        return
    quedas_compra = []
    for fii in analise.get("fiis") or []:
        g = gatilhos_de_queda(fii.get("preco_atual"), fii.get("preco_compra"))
        if g.get("atingiu"):
            quedas_compra.append(fii["ticker"])
    if quedas_compra:
        st.warning(
            f"Queda de {LIMITE_QUEDA_PCT:.0f}% ou mais vs compra: "
            + ", ".join(quedas_compra)
            + ". Abra **Quedas 10%** para o PDF com as notícias."
        )
    _alternar_visibilidade_valores()
    mostrar_valores = st.session_state.get("mostrar_valores_financeiros", False)

    if not itens:
        st.info("Carteira vazia. Adicione fundos ou ações na aba Carteira.")
        return

    render_painel(itens, analise, mostrar_valores)


def exibir_quedas():
    pagina(
        "Quedas de 10%",
        f"Quando o preço cai {LIMITE_QUEDA_PCT:.0f}% ou mais (vs compra, vs ontem "
        "ou vs a máxima do mês), o sistema junta as manchetes do Yahoo e do Google News "
        "e gera um PDF. Sem notícia o motivo fica N/D — não inventamos a causa. "
        "O download vai para o seu computador pelo navegador.",
    )
    cache = st.session_state.get("_dashboard_cache") or {}
    analise = cache.get("analise")
    if not analise or "erro" in (analise or {}):
        with st.spinner("Lendo a carteira..."):
            analise = analisar_carteira(st.session_state.db)
    if not analise or "erro" in analise:
        st.info("Carteira vazia.")
        return

    linhas = []
    for fii in analise.get("fiis") or []:
        g = gatilhos_de_queda(fii.get("preco_atual"), fii.get("preco_compra"))
        linhas.append(
            {
                "Classe": "Fundo" if classe_ativo(fii["ticker"]) == "fundo" else "Ação",
                "Ticker": fii["ticker"],
                "Preço atual": fii.get("preco_atual"),
                "Preço compra": fii.get("preco_compra"),
                "vs compra %": g.get("vs_compra"),
                "Alerta": "SIM" if g.get("atingiu") else "",
            }
        )
    df_q = pd.DataFrame(linhas)
    st.subheader("Fundos")
    fundos_q = df_q[df_q["Classe"] == "Fundo"] if not df_q.empty else df_q
    if fundos_q.empty:
        st.info("Nenhum fundo na carteira.")
    else:
        st.dataframe(fundos_q.drop(columns=["Classe"]), width="stretch", hide_index=True)
    st.subheader("Ações")
    acoes_q = df_q[df_q["Classe"] == "Ação"] if not df_q.empty else df_q
    if acoes_q.empty:
        st.info("Nenhuma ação na carteira.")
    else:
        st.dataframe(acoes_q.drop(columns=["Classe"]), width="stretch", hide_index=True)

    if st.button("Buscar notícias e gerar PDFs", type="primary", width="stretch"):
        with st.spinner("Lendo histórico e manchetes só dos que caíram 10%+..."):
            relatorios = verificar_quedas_carteira(
                st.session_state.db,
                analise.get("fiis") or [],
                enviar_telegram=True,
            )
        st.session_state["_relatorios_queda"] = relatorios
        if not relatorios:
            st.info(
                f"Nenhuma posição atingiu -{LIMITE_QUEDA_PCT:.0f}% agora "
                "(compra, fechamento anterior ou máxima do mês)."
            )
        else:
            st.success(f"{len(relatorios)} relatório(s) pronto(s) para baixar.")

    relatorios = st.session_state.get("_relatorios_queda") or []
    for resumo in relatorios:
        ticker = resumo.get("ticker")
        st.subheader(ticker)
        st.write(resumo.get("abertura") or "")
        st.write(resumo.get("motivo") or "N/D")
        pdf = resumo.get("pdf")
        if pdf:
            st.download_button(
                f"Baixar PDF — {ticker}",
                data=pdf,
                file_name=f"queda_{ticker}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                key=f"dl_queda_{ticker}",
                width="stretch",
            )


def _tabela_proventos(df_bloco: pd.DataFrame) -> pd.DataFrame:
    return (
        df_bloco[["data_pagamento", "ticker", "valor_por_cota", "qtd", "total"]]
        .rename(
            columns={
                "data_pagamento": "Data",
                "ticker": "Ticker",
                "valor_por_cota": "R$/cota",
                "qtd": "Cotas",
                "total": "Total R$",
            }
        )
        .sort_values("Data", ascending=False)
    )


def _bloco_proventos(titulo: str, df_bloco: pd.DataFrame, chave: str):
    st.subheader(titulo)
    if df_bloco.empty:
        st.info(f"Nenhum provento de {titulo.lower()} no período.")
        return
    total = float(df_bloco["total"].sum())
    st.metric("Total no período", f"R$ {total:,.2f}")
    por_mes = df_bloco.groupby("mes")["total"].sum().reset_index()
    por_mes.columns = ["Mês", "R$ recebido"]
    fig = _grafico(
        px.bar(por_mes, x="Mês", y="R$ recebido", title=f"Proventos — {titulo}")
    )
    st.plotly_chart(fig, width="stretch", key=f"prov_bar_{chave}")
    st.dataframe(_tabela_proventos(df_bloco), width="stretch", hide_index=True)


def exibir_proventos():
    """Calendário de proventos — histórico registado e estimativa mensal."""
    pagina("Dividendos", "Dividendos e JCP creditados. Fundos e ações em tabelas e gráficos separados.")
    db = st.session_state.db
    carteira = db.obter_carteira()

    if carteira.empty:
        st.info("Carteira vazia — adicione fundos ou ações na aba Carteira.")
        return

    c1, c2 = st.columns(2)
    if c1.button("Sincronizar proventos (Yahoo Finance)", width="stretch"):
        with st.spinner("Buscando dividendos dos últimos 12 meses..."):
            for _, row in carteira.iterrows():
                try:
                    sincronizar_proventos(db, str(row["ticker"]))
                except Exception:
                    pass
        st.success("Proventos sincronizados.")
        st.rerun()

    meses = c2.number_input("Meses de histórico", min_value=1, max_value=36, value=12)
    dividendos = db.obter_dividendos(meses=int(meses))

    if dividendos.empty:
        st.info(
            "Sem proventos registados. Clique em **Sincronizar proventos** "
            "para puxar do Yahoo Finance."
        )
        return

    dividendos["data_pagamento"] = pd.to_datetime(dividendos["data_pagamento"])
    dividendos["mes"] = dividendos["data_pagamento"].dt.to_period("M").astype(str)
    dividendos["valor_por_cota"] = pd.to_numeric(dividendos["valor_por_cota"], errors="coerce")

    carteira_dict = {
        str(r["ticker"]).upper(): int(r["quantidade"]) for _, r in carteira.iterrows()
    }
    dividendos["qtd"] = dividendos["ticker"].map(carteira_dict).fillna(0).astype(int)
    dividendos["total"] = dividendos["valor_por_cota"] * dividendos["qtd"]

    total_recebido = dividendos["total"].sum()
    proximo_mes = (
        dividendos.groupby("mes")["total"].sum().sort_index().iloc[-1]
        if not dividendos.empty else 0
    )
    m1, m2 = st.columns(2)
    m1.metric("Total recebido (período)", f"R$ {total_recebido:,.2f}")
    m2.metric("Último mês completo", f"R$ {proximo_mes:,.2f}")

    div_fundos, div_acoes = _partir_df_por_classe(dividendos, "ticker")
    _bloco_proventos("Fundos imobiliários", div_fundos, "fundos")
    st.divider()
    _bloco_proventos("Ações", div_acoes, "acoes")

    tabela_csv = _tabela_proventos(dividendos)
    csv_prov = tabela_csv.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar CSV de proventos (fundos e ações)",
        csv_prov,
        file_name=f"proventos_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        width="stretch",
    )

    st.subheader("Registrar provento manualmente")
    with st.form("add_provento", clear_on_submit=True):
        tickers_cart = sorted(carteira_dict.keys())
        col1, col2, col3 = st.columns(3)
        tk = col1.selectbox("Ativo", tickers_cart)
        data_prov = col2.date_input("Data de pagamento")
        valor_cota = col3.number_input("R$ por cota", min_value=0.0001, step=0.0001, format="%.4f")
        if st.form_submit_button("Registrar", type="primary", width="stretch"):
            db.salvar_dividendo(tk, data_prov.isoformat(), float(valor_cota))
            st.success(f"Provento de {tk} em {data_prov} registrado.")
            st.rerun()


def exibir_carteira():
    pagina(
        "Sua carteira",
        "Fundos (tickers 11/12, ex.: MXRF11) e ações (ex.: PETR4) ficam em listas separadas. "
        "A classe é detectada pelo ticker.",
    )

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
        if ticker:
            st.caption(
                f"{ticker} entra como **{'fundo' if eh_fii(ticker) else 'ação'}**."
            )
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
                _invalidar_analise()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    carteira = st.session_state.db.obter_carteira()
    if carteira.empty:
        st.info("Carteira vazia.")
    else:
        tickers_pos = [str(r["ticker"]).upper() for _, r in carteira.iterrows()]
        precos = {}
        faltando = []
        for ticker in tickers_pos:
            cached = st.session_state.db.get_cache(ticker, 120)
            if cached and cached.get("preco_atual") is not None:
                precos[ticker] = float(cached["preco_atual"])
            else:
                faltando.append(ticker)
        if faltando:
            for ticker, cot in buscar_cotacoes_lote(faltando).items():
                if cot.get("preco_atual") is not None:
                    precos[ticker] = float(cot["preco_atual"])

        def _lista(titulo, pred):
            st.subheader(titulo)
            linhas = [row for _, row in carteira.iterrows() if pred(str(row["ticker"]).upper())]
            if not linhas:
                st.info("Nenhuma posição neste grupo.")
                return
            for row in linhas:
                ticker = row["ticker"]
                qtd = int(row["quantidade"])
                preco_compra = float(row["preco_compra"])
                total = qtd * preco_compra
                preco_atual = precos.get(str(ticker).upper())
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
                    _invalidar_analise()
                    st.rerun()

        _lista("Fundos imobiliários", eh_fii)
        _lista("Ações", lambda t: not eh_fii(t))

    st.subheader("Histórico de transações")
    st.caption("Todas as compras, vendas e saldos iniciais — o preço médio da posição usa este histórico.")
    movimentos = st.session_state.db.obter_movimentacoes()
    if movimentos.empty:
        st.info("Nenhuma movimentação registrada ainda.")
        return

    movimentos = movimentos.copy()
    if "ticker" in movimentos.columns:
        movimentos["classe"] = movimentos["ticker"].map(
            lambda t: "Fundo" if eh_fii(str(t)) else "Ação"
        )
    colunas = {
        "classe": "Classe",
        "data_movimentacao": "Data",
        "ticker": "Ticker",
        "tipo": "Tipo",
        "quantidade": "Qtd",
        "preco_unitario": "Preço R$",
        "taxas": "Taxas R$",
        "observacoes": "Observações",
    }
    existentes = [c for c in colunas if c in movimentos.columns]
    for titulo, classe in (("Fundos", "Fundo"), ("Ações", "Ação")):
        st.caption(titulo)
        bloco = movimentos[movimentos["classe"] == classe] if "classe" in movimentos.columns else movimentos
        if bloco.empty:
            st.info(f"Sem movimentações de {titulo.lower()}.")
            continue
        tabela = bloco[existentes].rename(columns=colunas)
        if "Data" in tabela.columns:
            tabela = tabela.sort_values("Data", ascending=False)
        st.dataframe(tabela, width="stretch", hide_index=True)
    st.download_button(
        "Baixar CSV do histórico",
        movimentos.rename(columns=colunas).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"movimentacoes_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        width="stretch",
    )


def exibir_rebalanceamento():
    pagina(
        "Plano de rebalanceamento",
        "Este plano cobre só FIIs (DY, vacância, P/VP, anos de bolsa, setores). "
        "Ações como PETR4 ficam em Decisão separada — não entram no roteiro de fundos. "
        "Execute na corretora e confirme aqui para atualizar carteira e histórico.",
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
        tabela = []
        rotulos = []
        mapa = {}
        for _, item in pendentes.iterrows():
            rotulo = (
                f"Fase {int(item['fase'])} · {item['tipo']} {item['ticker']} "
                f"({int(item['quantidade'])} cotas)"
            )
            rotulos.append(rotulo)
            mapa[rotulo] = item
            tabela.append(
                {
                    "Fase": int(item["fase"]),
                    "Tipo": item["tipo"],
                    "Ticker": item["ticker"],
                    "Qtd": int(item["quantidade"]),
                    "Par": item.get("par_ticker") or "",
                    "Motivo": item.get("motivo") or "",
                }
            )
        st.dataframe(pd.DataFrame(tabela), width="stretch", hide_index=True)
        escolhido = st.selectbox("Confirmar na corretora", rotulos)
        item = mapa[escolhido]
        preco_ref = item.get("preco_referencia")
        preco_default = float(preco_ref) if pd.notna(preco_ref) else 10.0
        with st.form("exec_plano_unico"):
            preco_exec = st.number_input(
                f"Preço executado de {item['ticker']} (R$)",
                min_value=0.01,
                value=preco_default,
                step=0.01,
            )
            taxas = st.number_input("Taxas (R$)", min_value=0.0, value=0.0, step=0.01)
            if st.form_submit_button(
                f"Registrar {item['tipo']} executada",
                type="primary",
                width="stretch",
            ):
                try:
                    db.executar_item_plano(
                        int(item["id"]),
                        float(preco_exec),
                        float(taxas),
                    )
                    st.success(f"{item['tipo']} de {item['ticker']} registrada na carteira.")
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
        csv_plano = pd.DataFrame(checklist).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Baixar checklist da corretora (CSV)",
            csv_plano,
            file_name=f"checklist_rebalanceamento_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            width="stretch",
        )


def exibir_buscar_fii():
    pagina(
        "Indicadores",
        "Mesmos cards da página pública do Investidor10: cotação, DY, P/VP, "
        "liquidez, vacância, cotistas e o restante. Informe um fundo (MXRF11) "
        "ou uma ação (PETR4).",
    )
    c1, c2 = st.columns([3, 1])
    ticker = c1.text_input("Ticker", "MXRF11").upper()
    buscar = c2.button("Buscar", type="primary", width="stretch")

    if not buscar:
        return

    with st.spinner("Buscando no Yahoo e no Investidor10..."):
        dados = buscar_dados_tempo_real(ticker, completo=True)

    if "erro" in dados:
        st.error(dados["erro"])
        return

    score = calcular_score(dados)
    try:
        av = avaliar_ativo(ticker)
        st.session_state.db.salvar_avaliacao(ticker, av)
        resumo = resumo_criterios(av)
        dados_av = av.get("dados") or {}
        for campo, valor in dados_av.items():
            if dados.get(campo) in (None, "") and valor not in (None, ""):
                dados[campo] = valor
    except Exception:
        av = None
        resumo = {"status": "nd", "ok": 0, "fail": 0, "nd": 0}

    eh_fundo = classe_ativo(ticker) == "fundo"
    cabecalho_ativo(
        dados.get("ticker", ticker),
        dados.get("nome") or dados.get("razao_social"),
        "fundo" if eh_fundo else "acao",
        dados,
    )
    st.caption(
        f"{dados.get('fonte', '')} · {dados.get('horario_dados', '')} · "
        f"status {dados.get('status_geral', 'N/D')} · confiança {dados.get('confianca', 'N/D')} · "
        f"score {score:.0f}/100 · {status_badge(resumo['status'])}"
    )
    if dados.get("url") or dados.get("url_investidor10"):
        st.caption(dados.get("url") or dados.get("url_investidor10"))

    preco = dados.get("preco_atual") if dados.get("preco_atual") is not None else dados.get("preco")

    if dados.get("divergencias"):
        st.warning(" · ".join(dados["divergencias"]))
    with st.expander("Auditoria das fontes"):
        qualidade = pd.DataFrame.from_dict(dados.get("qualidade", {}), orient="index")
        st.dataframe(qualidade, width="stretch")

    if av:
        st.subheader("Critérios do gestor")
        tabela = _tabela_criterios(av)
        if tabela.empty:
            st.caption("Sem critérios para este ticker.")
        else:
            st.dataframe(tabela, width="stretch", hide_index=True)

    with st.expander("Histórico de preço (3 meses)"):
        hist = buscar_historico(ticker, periodo="3mo")
        if hist is not None and not hist.empty:
            hist = hist.reset_index()
            hist.columns = [str(c) for c in hist.columns]
            data_col = next((c for c in hist.columns if c.lower() in ("date", "datetime", "index")), None)
            if data_col and "Close" in hist.columns:
                fig_hist = _grafico(
                    px.line(hist, x=data_col, y="Close", title=f"{ticker} — Preço de fecho (3m)")
                )
                st.plotly_chart(fig_hist, width="stretch")
            else:
                st.dataframe(hist, width="stretch")
        else:
            st.caption("Histórico não disponível neste momento.")

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
    pagina(
        "Checklist",
        "FIIs: DY mensal 0,60–1,50% · Vacância ≤ 10% · P/VP 0,70–1,10 · "
        "liquidez · +10 anos · diversificar galpão/shopping/empresarial/papel. "
        "Ações: sem prejuízo 5 anos · liquidez · P/VP ≥ 0,60 · +10 anos · dívida < PL.",
    )

    ticker = st.text_input("Avaliar ticker", "MXRF11").upper()
    if st.button("Avaliar", type="primary"):
        with st.spinner("Avaliando..."):
            av = avaliar_ativo(ticker, permitir_scrape=True)
            st.session_state.db.salvar_avaliacao(ticker, av)
            st.session_state["avaliacao_detalhe"] = av
            st.session_state["avaliacao_ticker"] = ticker

    av_detalhe = st.session_state.get("avaliacao_detalhe")
    if av_detalhe and st.session_state.get("avaliacao_ticker") == ticker:
        resumo = resumo_criterios(av_detalhe)
        classe = "fundo" if classe_ativo(ticker) == "fundo" else "acao"
        dados_av = av_detalhe.get("dados") or {}
        cabecalho_ativo(
            ticker,
            dados_av.get("nome") or dados_av.get("razao_social"),
            classe,
            dados_av,
        )
        st.caption(
            f"Aprovados: {resumo['ok']} · Reprovados: {resumo['fail']} · N/D: {resumo['nd']}"
        )
        st.dataframe(_tabela_criterios(av_detalhe), width="stretch", hide_index=True)

    st.divider()
    st.subheader("Carteira sob os critérios")
    st.caption(
        "Fundos e ações em tabelas separadas. Os critérios de FII (DY, vacância, P/VP) "
        "não se aplicam a ações. **Atualizar critérios** busca no Investidor10 "
        "vacância, liquidez, cotistas, VP/cota, taxa de adm. e variação 12 meses."
    )
    carteira = st.session_state.db.obter_carteira()
    if carteira.empty:
        st.info("Carteira vazia.")
        return

    rows_fundos = []
    rows_acoes = []
    setores = []
    for _, row in carteira.iterrows():
        ticker_pos = str(row["ticker"]).upper()
        av = st.session_state.db.obter_avaliacao(ticker_pos)
        if classe_ativo(ticker_pos) != "fundo":
            if av:
                resumo = resumo_criterios(av)
                rows_acoes.append(
                    {
                        "Ticker": ticker_pos,
                        "Status": status_badge(resumo["status"]),
                        "OK": resumo["ok"],
                        "Fail": resumo["fail"],
                        "N/D": resumo["nd"],
                    }
                )
            else:
                rows_acoes.append(
                    {
                        "Ticker": ticker_pos,
                        "Status": "AÇÃO",
                        "OK": 0,
                        "Fail": 0,
                        "N/D": 0,
                    }
                )
            continue
        if av:
            resumo = resumo_criterios(av)
            setor = av.get("dados", {}).get("setor_final") or (
                buscar_fii_por_ticker(ticker_pos) or {}
            ).get("setor") or "N/D"
            rows_fundos.append(
                {
                    "Ticker": ticker_pos,
                    "Status": status_badge(resumo["status"]),
                    "OK": resumo["ok"],
                    "Fail": resumo["fail"],
                    "N/D": resumo["nd"],
                    "Setor": setor,
                }
            )
            setores.append(setor)
        else:
            setor = (buscar_fii_por_ticker(ticker_pos) or {}).get("setor") or "N/D"
            rows_fundos.append(
                {
                    "Ticker": ticker_pos,
                    "Status": "N/D",
                    "OK": 0,
                    "Fail": 0,
                    "N/D": 0,
                    "Setor": setor,
                }
            )
            setores.append(setor)

    st.markdown("**Fundos imobiliários**")
    if rows_fundos:
        st.dataframe(pd.DataFrame(rows_fundos), width="stretch", hide_index=True)
    else:
        st.info("Nenhum fundo na carteira.")
    st.markdown("**Ações**")
    if rows_acoes:
        st.dataframe(pd.DataFrame(rows_acoes), width="stretch", hide_index=True)
    else:
        st.info("Nenhuma ação na carteira.")
    div = avaliar_diversificacao_setores(setores)
    st.write(
        f"Diversificação dos fundos: {', '.join(div['presentes']) or 'nenhum setor principal'} · "
        f"Faltando: {', '.join(div['faltando']) or 'nenhum'}"
    )
    if div["passou"]:
        st.success("Diversificação OK (≥3 setores-alvo). Ações não entram nessa conta.")
    else:
        st.warning("Diversificação dos fundos insuficiente. Ações não entram nessa conta.")


def exibir_watchlist():
    pagina(
        "Watchlist",
        "Fundos e ações em listas separadas. Se o preço atual cair até o alerta, "
        "o agendador envia Telegram (TELEGRAM_TOKEN e TELEGRAM_CHAT_ID). Nada de token no banco.",
    )
    with st.form("add_wl", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ticker = c1.text_input("Ticker", placeholder="MXRF11").upper()
        alerta = c2.number_input("Alerta de preço baixo (R$)", min_value=0.0, value=0.0, step=0.01)
        if ticker:
            st.caption(
                f"{ticker} entra como **{'fundo' if eh_fii(ticker) else 'ação'}**."
            )
        if st.form_submit_button("Adicionar", type="primary", width="stretch") and ticker:
            st.session_state.db.adicionar_watchlist(
                ticker, alerta if alerta > 0 else None, ""
            )
            st.rerun()

    watchlist = st.session_state.db.obter_watchlist()
    if watchlist.empty:
        st.info("Watchlist vazia.")
        return

    rows_wl = []
    precos_wl = {}
    tickers_wl = [str(r["ticker"]).upper() for _, r in watchlist.iterrows()]
    lote_wl = {}
    faltando_wl = []
    for ticker in tickers_wl:
        cached = st.session_state.db.get_cache(ticker, 120)
        if cached and cached.get("preco_atual") is not None:
            lote_wl[ticker] = cached
        else:
            faltando_wl.append(ticker)
    if faltando_wl:
        lote_wl.update(buscar_cotacoes_lote(faltando_wl))
    for _, row in watchlist.iterrows():
        ticker = row["ticker"]
        alerta_preco = row.get("preco_alvo")
        dados = lote_wl.get(str(ticker).upper()) or {}
        preco = dados.get("preco_atual") or dados.get("preco")
        dy = dados.get("dy")
        score = calcular_score(dados)
        if preco is not None:
            precos_wl[str(ticker).upper()] = float(preco)

        if alerta_preco and preco is not None:
            pct_alerta = (float(preco) - float(alerta_preco)) / float(alerta_preco) * 100
            if float(preco) <= float(alerta_preco):
                alerta_status = "NO ALVO"
            elif float(preco) <= float(alerta_preco) * 1.05:
                alerta_status = "Perto"
            else:
                alerta_status = f"+{pct_alerta:.1f}%"
        else:
            alerta_status = ""

        rows_wl.append({
            "Classe": "Fundo" if eh_fii(str(ticker)) else "Ação",
            "Ticker": ticker,
            "Preço": f"R$ {float(preco):.2f}" if preco is not None else "N/D",
            "DY %": f"{float(dy):.2f}" if dy is not None else "N/D",
            "Score": f"{score:.0f}/100",
            "Alerta R$": f"R$ {float(alerta_preco):.2f}" if alerta_preco else "—",
            "Status alerta": alerta_status,
        })

    df_wl = pd.DataFrame(rows_wl)
    col_wf, col_wa = st.columns(2)
    with col_wf:
        st.markdown("**Fundos**")
        fundos_wl = df_wl[df_wl["Classe"] == "Fundo"]
        if fundos_wl.empty:
            st.caption("Nenhum fundo na lista.")
        else:
            st.dataframe(
                fundos_wl.drop(columns=["Classe"]),
                width="stretch",
                hide_index=True,
            )
    with col_wa:
        st.markdown("**Ações**")
        acoes_wl = df_wl[df_wl["Classe"] == "Ação"]
        if acoes_wl.empty:
            st.caption("Nenhuma ação na lista.")
        else:
            st.dataframe(
                acoes_wl.drop(columns=["Classe"]),
                width="stretch",
                hide_index=True,
            )

    w1, w2 = st.columns(2)
    if w1.button("Verificar alvos agora", type="primary", width="stretch"):
        resultado = verificar_alertas_watchlist(
            st.session_state.db, precos=precos_wl, enviar=True
        )
        n = len(resultado.get("enviados") or [])
        d = len(resultado.get("disparados") or [])
        if d == 0:
            st.info("Nenhum ticker da watchlist está no alvo agora.")
        elif n:
            st.success(f"{d} no alvo · {n} alerta(s) Telegram novo(s).")
        else:
            ja = len(resultado.get("omitidos_dedup") or [])
            if not resultado.get("telegram_ok"):
                st.warning(
                    f"{d} no alvo, mas o Telegram está inativo. "
                    "Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID e ative em Configurações."
                )
            else:
                st.info(f"{d} no alvo · {ja} já tinham sido notificados neste alvo.")

    remover = st.selectbox("Remover da watchlist", [""] + [r["Ticker"] for r in rows_wl])
    if remover and st.button("Remover selecionado", type="secondary"):
        st.session_state.db.remover_watchlist(remover)
        st.rerun()


def exibir_vigia():
    pagina(
        "Vigia",
        "Pinga a saúde do site, lê a carteira (quedas, watchlist, proventos) e "
        "opcionalmente pede um resumo a um modelo se GROQ_API_KEY ou OPENAI_API_KEY "
        "estiver no ambiente. Sem chave, o relatório é só regras — não inventa texto.",
    )
    from vigia import SITE_PADRAO, rodar_vigia

    st.caption(
        "No Render o processo dorme: o vigia também acorda o app. "
        "Telegram usa TELEGRAM_TOKEN e TELEGRAM_CHAT_ID."
    )
    tem_ia = bool(os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    if tem_ia:
        st.success("Chave de modelo detectada — o resumo em linguagem natural será pedido à API.")
    else:
        st.info(
            "Sem GROQ_API_KEY / OPENAI_API_KEY o vigia usa só regras (site no ar, queda 10%, "
            "watchlist, proventos zerados). Para IA de verdade, coloque uma dessas chaves no .env."
        )
    enviar = st.checkbox("Enviar no Telegram se estiver configurado", value=True)
    if st.button("Rodar vigia agora", type="primary", width="stretch"):
        with st.spinner("Checando saúde e carteira..."):
            resultado = rodar_vigia(db=st.session_state.db, enviar=enviar)
        st.session_state["_vigia_ultimo"] = resultado
        if resultado["saude"].get("ok"):
            st.success("Site no ar.")
        else:
            st.error("Site não respondeu no health check.")
        if resultado.get("telegram"):
            st.success("Resumo enviado no Telegram.")
        elif enviar:
            st.caption("Telegram não enviado (faltam token/chat ou está desligado).")

    ultimo = st.session_state.get("_vigia_ultimo")
    if not ultimo:
        st.caption("Ainda não rodou nesta sessão.")
        return
    st.subheader("Último relatório")
    st.code(ultimo.get("texto") or "", language=None)
    st.caption(f"Coletado em {ultimo.get('coletado_em')} · {SITE_PADRAO}")


def exibir_comparacao():
    pagina(
        "Comparador",
        "Compare só FIIs (até a lista abaixo). Ações não entram nesta tabela — "
        "use Indicadores para PETR4 e similares.",
    )
    carteira = st.session_state.db.obter_carteira()
    opcoes = [t for t in FIIS_POPULARES if eh_fii(t)]
    if not carteira.empty:
        for ticker in carteira["ticker"].tolist():
            t = str(ticker).upper()
            if eh_fii(t) and t not in opcoes:
                opcoes.append(t)
    selecionados = st.multiselect(
        "Selecione os fundos",
        opcoes,
        default=opcoes[:3],
    )
    if not selecionados:
        st.info("Escolha pelo menos um fundo para comparar.")
        return

    acoes_escolhidas = [t for t in selecionados if not eh_fii(str(t))]
    if acoes_escolhidas:
        st.warning("Ignorados (não são fundos): " + ", ".join(acoes_escolhidas))
    selecionados = [t for t in selecionados if eh_fii(str(t))]
    if not selecionados:
        st.info("Informe tickers de FII (terminados em 11 ou 12).")
        return

    dados_lista = []
    with st.spinner("Buscando cotações para comparação..."):
        lote = buscar_cotacoes_lote(selecionados)
        for ticker in selecionados:
            dados = lote.get(str(ticker).upper()) or buscar_dados_tempo_real(ticker)
            if not dados or "erro" in dados:
                continue
            dados = dict(dados)
            dados["ticker"] = str(ticker).upper()
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
            st.plotly_chart(
                _grafico(px.bar(df, x="ticker", y="dy", title="DY (%)")),
                width="stretch",
            )
    with c2:
        if "p_vp" in df.columns:
            st.plotly_chart(
                _grafico(px.bar(df, x="ticker", y="p_vp", title="P/VP")),
                width="stretch",
            )


def exibir_configuracoes():
    pagina("Configurações", "Segredos ficam só no ambiente. Nada de senha ou token no Git.")
    st.info(
        "Segredos (senha do app, DATABASE_URL, tokens) ficam só no Render/Neon — "
        "nunca no Git. Preferir TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no ambiente. "
        "Com Telegram ativo, o agendador avisa quando um ticker da watchlist atinge o preço-alvo."
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
