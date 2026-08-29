from dashboard_ui import kpis_da_carteira, partir_por_classe, totais_de_itens


def test_partir_por_classe_separa_petr4():
    fundos, acoes = partir_por_classe(
        [
            {"ticker": "MXRF11", "valor": 100, "qtd": 10, "preco_compra": 10},
            {"ticker": "PETR4", "valor": 80, "qtd": 2, "preco_compra": 40},
            {"ticker": "TAEE11", "valor": 50, "qtd": 1, "preco_compra": 38},
        ]
    )
    assert [i["ticker"] for i in fundos] == ["MXRF11"]
    assert [i["ticker"] for i in acoes] == ["PETR4", "TAEE11"]


def test_totais_nao_trata_sem_cotacao_como_zero():
    totais = totais_de_itens(
        [
            {"ticker": "MXRF11", "qtd": 10, "preco_compra": 10, "valor": 110, "proventos": 5, "projecao_mensal": 1},
            {"ticker": "HGLG11", "qtd": 1, "preco_compra": 100, "valor": None, "proventos": 0},
        ]
    )
    assert totais["sem_cotacao"] == ["HGLG11"]
    assert totais["lucro"] is None
    assert totais["atual"] == 110


def test_kpis_da_carteira_tem_seis_cards_e_nao_inventa_zero():
    totais = totais_de_itens(
        [
            {"ticker": "MXRF11", "qtd": 10, "preco_compra": 10, "valor": None, "proventos": 0},
        ]
    )
    cards = kpis_da_carteira(totais, mostrar_valores=True)
    assert [c["label"] for c in cards] == [
        "Investido",
        "Patrimônio",
        "Ganho de capital",
        "Rentab. total",
        "Proventos 12m",
        "Projeção / mês",
    ]
    patrimonio = next(c for c in cards if c["label"] == "Patrimônio")
    ganho = next(c for c in cards if c["label"] == "Ganho de capital")
    assert patrimonio["delta"] == "parcial"
    assert ganho["valor"] == "N/D"
