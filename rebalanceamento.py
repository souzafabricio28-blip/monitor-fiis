"""
Plano de rebalanceamento baseado nos critérios do gestor.
Movimentações ficam PENDENTES até o usuário executar na corretora e confirmar no app.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from market_data import buscar_dados_completos

# Pares venda -> compra sugerida (fase, ordem dentro da fase)
ROTEIRO = [
    {
        "fase": 1,
        "ordem": 1,
        "venda": "VRTM11",
        "compra": "VISC11",
        "motivo_venda": "Liquidez crítica (R$ 209 mil/dia)",
        "motivo_compra": "Entrar em Shopping; 4 critérios OK",
    },
    {
        "fase": 1,
        "ordem": 2,
        "venda": "MANA11",
        "compra": "KNRI11",
        "motivo_venda": "Fundo novo (4 anos) e baixa liquidez",
        "motivo_compra": "Entrar em Empresarial; referência do segmento",
    },
    {
        "fase": 1,
        "ordem": 3,
        "venda": "SNEL11",
        "compra": "BTLG11",
        "motivo_venda": "Fundo novo (4 anos) e baixa liquidez",
        "motivo_compra": "Reforçar Galpão com fundo mais líquido que GARE11",
    },
    {
        "fase": 1,
        "ordem": 4,
        "venda": "VGHF11",
        "compra": "KNCR11",
        "motivo_venda": "Fundo novo (5 anos) e baixa liquidez",
        "motivo_compra": "Papel aprovado nos critérios (5 OK)",
    },
    {
        "fase": 1,
        "ordem": 5,
        "venda": "KNSC11",
        "compra": "KNCR11",
        "motivo_venda": "Fundo jovem (6 anos) e baixa liquidez",
        "motivo_compra": "Consolidar papel em KNCR11 (segundo núcleo)",
    },
    {
        "fase": 1,
        "ordem": 6,
        "venda": "VGIR11",
        "compra": "KNCR11",
        "motivo_venda": "Faltam 2 anos para +10 anos; baixa liquidez",
        "motivo_compra": "Consolidar papel em KNCR11",
    },
    {
        "fase": 2,
        "ordem": 1,
        "venda": "BTCI11",
        "compra": "KNCR11",
        "motivo_venda": "Papel redundante; falha só liquidez vs referência",
        "motivo_compra": "Reforçar núcleo aprovado (MXRF11 + KNCR11)",
    },
    {
        "fase": 2,
        "ordem": 2,
        "venda": "CPTS11",
        "compra": "MXRF11",
        "motivo_venda": "Papel redundante; falha só liquidez vs referência",
        "motivo_compra": "Reforçar MXRF11 (único FII 100% aprovado hoje)",
    },
    {
        "fase": 3,
        "ordem": 1,
        "venda": "GARE11",
        "compra": "BTLG11",
        "motivo_venda": "Galpão ilíquido; dados incompletos",
        "motivo_compra": "Consolidar exposição logística",
    },
    {
        "fase": 3,
        "ordem": 2,
        "venda": "RURA11",
        "compra": "XPML11",
        "motivo_venda": "Híbrido ilíquido; único com pequeno prejuízo",
        "motivo_compra": "Reforçar Shopping (segundo nome)",
    },
]

MANTER = [
    {
        "ticker": "MXRF11",
        "motivo": "Único FII aprovado; maior posição; alta liquidez",
    },
]

DECISAO_SEPARADA = [
    {
        "ticker": "PETR4",
        "motivo": "É ação, não FII. Falha só crescimento 10 anos. "
        "Decidir se mantém fora do monitor FII ou realoca em FIIs.",
    },
]


def _preco(ticker: str, db=None) -> Optional[float]:
    dados = buscar_dados_completos(ticker, db=db, usar_cache=True)
    valor = dados.get("preco_atual")
    return float(valor) if valor is not None else None


def _qtd_compra(valor_venda: float, preco_destino: Optional[float]) -> int:
    if not preco_destino or preco_destino <= 0:
        return 10
    return max(1, int(valor_venda / preco_destino))


def gerar_plano(db=None) -> Dict:
    """Monta itens de venda/compra com quantidades e preços de referência."""
    from db import DatabaseManager

    db = db or DatabaseManager()
    carteira = {
        row["ticker"]: int(row["quantidade"])
        for _, row in db.obter_carteira().iterrows()
    }
    itens: List[Dict] = []
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for passo in ROTEIRO:
        venda = passo["venda"]
        compra = passo["compra"]
        qtd_venda = carteira.get(venda)
        if not qtd_venda:
            continue

        preco_venda = _preco(venda, db) or 0.0
        valor_venda = qtd_venda * preco_venda if preco_venda else 0.0
        preco_compra = _preco(compra, db)
        qtd_compra = _qtd_compra(valor_venda, preco_compra)

        itens.append(
            {
                "fase": passo["fase"],
                "ordem": passo["ordem"],
                "tipo": "VENDA",
                "ticker": venda,
                "quantidade": qtd_venda,
                "preco_referencia": preco_venda or None,
                "valor_estimado": round(valor_venda, 2) if valor_venda else None,
                "par_ticker": compra,
                "motivo": passo["motivo_venda"],
                "status": "pendente",
                "criado_em": agora,
                "idempotency_key": f"plano-f{passo['fase']}-o{passo['ordem']}-venda-{venda}",
            }
        )
        itens.append(
            {
                "fase": passo["fase"],
                "ordem": passo["ordem"],
                "tipo": "COMPRA",
                "ticker": compra,
                "quantidade": qtd_compra,
                "preco_referencia": preco_compra,
                "valor_estimado": round(qtd_compra * preco_compra, 2)
                if preco_compra
                else None,
                "par_ticker": venda,
                "motivo": passo["motivo_compra"],
                "status": "pendente",
                "criado_em": agora,
                "idempotency_key": f"plano-f{passo['fase']}-o{passo['ordem']}-compra-{compra}-{venda}",
            }
        )

    return {
        "criado_em": agora,
        "titulo": "Rebalanceamento — critérios do gestor",
        "manter": MANTER,
        "decisoes": DECISAO_SEPARADA,
        "itens": itens,
        "resumo": {
            "vendas": sum(1 for i in itens if i["tipo"] == "VENDA"),
            "compras": sum(1 for i in itens if i["tipo"] == "COMPRA"),
            "fases": 3,
        },
    }


def registrar_plano_no_banco(db=None) -> Dict:
    from db import DatabaseManager

    db = db or DatabaseManager()
    plano = gerar_plano(db)
    inseridos = db.salvar_plano_rebalanceamento(plano["itens"])
    db.set_config(
        "plano_rebalanceamento_meta",
        {
            "criado_em": plano["criado_em"],
            "titulo": plano["titulo"],
            "manter": plano["manter"],
            "decisoes": plano["decisoes"],
            "resumo": plano["resumo"],
        },
    )
    return {"plano": plano, "inseridos": inseridos}
