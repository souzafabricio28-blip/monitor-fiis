"""
Popula SQLite local vazio com a carteira documentada.

Não altera Neon/PostgreSQL. Idempotente: só corre se a carteira estiver vazia.
"""

from __future__ import annotations

from typing import Sequence

# Posições alinhadas ao extrato Nubank (custódia 01/09/2026).
# PM: histórico local quando conhecido; ITSA4 usa cotação do extrato.
POSICOES_LOCAIS: Sequence[tuple[str, int, float]] = (
    ("MXRF11", 48, 9.23),
    ("BTCI11", 10, 8.97),
    ("CPTS11", 10, 7.43),
    ("GARE11", 10, 8.31),
    ("KNSC11", 10, 9.04),
    ("MANA11", 10, 9.11),
    ("SNEL11", 10, 8.15),
    ("VGHF11", 10, 5.32),
    ("VRTM11", 10, 6.57),
    ("BBAS3", 1, 20.96),
    ("KLBN4", 1, 3.81),
    ("PETR4", 4, 41.45),
    ("ITSA4", 2, 13.16),
)


def garantir_carteira_local(db) -> int:
    """Insere saldo inicial local. Devolve quantas posições foram criadas."""
    if getattr(db, "use_pg", False):
        return 0
    carteira = db.obter_carteira()
    if carteira is not None and not carteira.empty:
        return 0

    inseridos = 0
    for ticker, quantidade, preco in POSICOES_LOCAIS:
        db.registrar_movimentacao(
            ticker,
            "SALDO_INICIAL",
            quantidade,
            preco,
            data_movimentacao="2025-01-01",
            observacoes="Saldo inicial local",
            idempotency_key=f"seed-local-{ticker}",
        )
        inseridos += 1
    return inseridos


def garantir_plano_local(db) -> int:
    """Regista o roteiro de rebalanceamento no SQLite vazio, sem ir à rede."""
    if getattr(db, "use_pg", False):
        return 0
    plano = db.obter_plano_rebalanceamento()
    if plano is not None and not plano.empty:
        return 0

    from datetime import datetime

    from rebalanceamento import DECISAO_SEPARADA, MANTER, ROTEIRO

    carteira = {
        str(row["ticker"]).upper(): (
            int(row["quantidade"]),
            float(row["preco_compra"]),
        )
        for _, row in db.obter_carteira().iterrows()
    }
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    itens = []
    for passo in ROTEIRO:
        venda = passo["venda"]
        compra = passo["compra"]
        posicao = carteira.get(venda)
        if not posicao:
            continue
        qtd_venda, preco_venda = posicao
        valor_venda = qtd_venda * preco_venda
        qtd_compra = max(1, int(valor_venda / preco_venda)) if preco_venda else 10
        itens.append(
            {
                "fase": passo["fase"],
                "ordem": passo["ordem"],
                "tipo": "VENDA",
                "ticker": venda,
                "quantidade": qtd_venda,
                "preco_referencia": preco_venda,
                "valor_estimado": round(valor_venda, 2),
                "par_ticker": compra,
                "motivo": passo["motivo_venda"],
                "status": "pendente",
                "criado_em": agora,
                "idempotency_key": f"seed-plano-f{passo['fase']}-o{passo['ordem']}-venda-{venda}",
            }
        )
        itens.append(
            {
                "fase": passo["fase"],
                "ordem": passo["ordem"],
                "tipo": "COMPRA",
                "ticker": compra,
                "quantidade": qtd_compra,
                "preco_referencia": None,
                "valor_estimado": None,
                "par_ticker": venda,
                "motivo": passo["motivo_compra"],
                "status": "pendente",
                "criado_em": agora,
                "idempotency_key": f"seed-plano-f{passo['fase']}-o{passo['ordem']}-compra-{compra}-{venda}",
            }
        )

    if not itens:
        return 0
    inseridos = db.salvar_plano_rebalanceamento(itens)
    db.set_config(
        "plano_rebalanceamento_meta",
        {
            "criado_em": agora,
            "titulo": "Rebalanceamento — critérios do gestor",
            "manter": list(MANTER),
            "decisoes": list(DECISAO_SEPARADA),
            "resumo": {
                "vendas": sum(1 for i in itens if i["tipo"] == "VENDA"),
                "compras": sum(1 for i in itens if i["tipo"] == "COMPRA"),
                "fases": 3,
            },
        },
    )
    return inseridos
