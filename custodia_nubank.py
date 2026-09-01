"""Custódia Nubank — sincroniza a carteira com o extrato.

Fonte: Extrato de Custódia Nu Investimentos, custódia em 01/09/2026.
Quantidades são a fonte da verdade. Preço médio existente é preservado;
só entra PM provisório (cotação do extrato) em ticker novo sem histórico.
"""

from __future__ import annotations

from typing import Any

# ticker -> (quantidade, cotação unitária no extrato — só para posição nova)
CUSTODIA_NUBANK_20260901: dict[str, tuple[int, float]] = {
    "KNSC11": (10, 9.00),
    "VGHF11": (10, 5.32),
    "MXRF11": (48, 9.21),
    "CPTS11": (10, 7.40),
    "MANA11": (10, 9.05),
    "BTCI11": (10, 9.11),
    "VRTM11": (10, 6.44),
    "SNEL11": (10, 8.26),
    "GARE11": (10, 8.36),
    "BBAS3": (1, 21.25),
    "KLBN4": (1, 3.77),
    "PETR4": (4, 46.87),
    "ITSA4": (2, 13.16),
}

# Tickers errados / legado → ticker correto no extrato
REALOCAR: dict[str, str] = {
    "ITSA3": "ITSA4",
}

CHAVE_SYNC = "custodia_nubank_20260901"


def sincronizar_custodia_nubank(
    db: Any,
    *,
    forcar: bool = False,
    posicoes: dict[str, tuple[int, float]] | None = None,
    chave: str = CHAVE_SYNC,
) -> dict[str, Any]:
    """Alinha a carteira ao extrato. Idempotente via configuracoes[chave]."""
    if not forcar and db.get_config(chave):
        return {"aplicado": False, "motivo": "ja_sincronizado"}

    alvo = dict(posicoes or CUSTODIA_NUBANK_20260901)
    carteira = db.obter_carteira()
    atuais: dict[str, tuple[int, float]] = {}
    if carteira is not None and not carteira.empty:
        for _, row in carteira.iterrows():
            ticker = str(row["ticker"]).upper()
            atuais[ticker] = (int(row["quantidade"]), float(row["preco_compra"]))

    alteracoes: list[str] = []

    # 1) Realocar tickers errados (ex.: ITSA3 → ITSA4) preservando custo
    for origem, destino in REALOCAR.items():
        if origem not in atuais:
            continue
        qtd_origem, pm_origem = atuais[origem]
        db.remover_fii(origem)
        alteracoes.append(f"removeu {origem}")
        atuais.pop(origem, None)

        qtd_destino, cotacao = alvo.get(destino, (qtd_origem, pm_origem))
        pm = pm_origem
        # PM de ITSA3 ~26 com 2 cotas costuma ser o total, não o unitário
        if origem == "ITSA3" and pm > 20:
            pm = round(pm / 2, 4)
        if destino in atuais:
            # já existe destino: só ajusta quantidade depois
            pass
        else:
            db.registrar_movimentacao(
                destino,
                "SALDO_INICIAL",
                int(qtd_destino),
                float(pm if pm > 0 else cotacao),
                data_movimentacao="2026-09-01",
                observacoes=f"Realocado de {origem} conforme extrato Nubank 01/09/2026",
                idempotency_key=f"{chave}:realoca:{origem}:{destino}",
            )
            atuais[destino] = (int(qtd_destino), float(pm if pm > 0 else cotacao))
            alteracoes.append(f"realocou {origem}→{destino} qtd={qtd_destino} pm={pm:.4f}")

    # Recarrega após realocações
    carteira = db.obter_carteira()
    atuais = {}
    if carteira is not None and not carteira.empty:
        for _, row in carteira.iterrows():
            ticker = str(row["ticker"]).upper()
            atuais[ticker] = (int(row["quantidade"]), float(row["preco_compra"]))

    # 2) Remover o que não está no extrato
    for ticker in sorted(atuais):
        if ticker not in alvo:
            db.remover_fii(ticker)
            alteracoes.append(f"excluiu {ticker} (ausente no extrato)")
            atuais.pop(ticker, None)

    # 3) Criar / ajustar quantidades
    for ticker, (qtd_alvo, cotacao) in sorted(alvo.items()):
        if ticker not in atuais:
            db.registrar_movimentacao(
                ticker,
                "SALDO_INICIAL",
                int(qtd_alvo),
                float(cotacao),
                data_movimentacao="2026-09-01",
                observacoes="Saldo do extrato Nubank 01/09/2026 (PM provisório = cotação do extrato)",
                idempotency_key=f"{chave}:novo:{ticker}",
            )
            alteracoes.append(f"incluiu {ticker} qtd={qtd_alvo}")
            continue
        qtd_atual, _pm = atuais[ticker]
        if qtd_atual == qtd_alvo:
            continue
        acao = db.ajustar_quantidade(ticker, int(qtd_alvo))
        alteracoes.append(f"{ticker}: {qtd_atual}→{qtd_alvo} ({acao})")

    db.set_config(
        chave,
        {
            "sincronizado_em": "2026-09-01",
            "fonte": "Nubank_Extrato_de_Custodia[01_09_26_20_17_20].pdf",
            "posicoes": {t: q for t, (q, _) in alvo.items()},
            "alteracoes": alteracoes,
        },
    )
    return {"aplicado": True, "alteracoes": alteracoes, "posicoes": len(alvo)}
