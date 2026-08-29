from queda_report import (
    gatilhos_de_queda,
    gerar_pdf_queda_bytes,
    montar_resumo,
    variacao_pct,
)


def test_variacao_nao_trata_ausente_como_zero():
    assert variacao_pct(None, 10) is None
    assert variacao_pct(9, 0) is None
    assert round(variacao_pct(90, 100), 1) == -10.0


def test_gatilho_dez_por_cento():
    ok = gatilhos_de_queda(90, preco_compra=100)
    assert ok["atingiu"] is True
    assert "preço de compra" in ok["disparos"]
    nao = gatilhos_de_queda(91, preco_compra=100)
    assert nao["atingiu"] is False
    sem_dado = gatilhos_de_queda(None, preco_compra=100)
    assert sem_dado["atingiu"] is False


def test_resumo_sem_noticia_fica_nd():
    queda = gatilhos_de_queda(80, preco_compra=100)
    resumo = montar_resumo("PETR4", queda, [])
    assert resumo["motivo_curto"] == "N/D"
    assert "inventa" in resumo["motivo"].lower()


def test_resumo_usa_manchete():
    queda = gatilhos_de_queda(80, preco_compra=100)
    resumo = montar_resumo(
        "PETR4",
        queda,
        [{"titulo": "Petrobras anuncia corte de produção", "fonte": "Valor"}],
    )
    assert "corte de produção" in resumo["motivo"]
    assert resumo["motivo_curto"].startswith("Petrobras")


def test_pdf_queda_bytes():
    queda = gatilhos_de_queda(80, preco_compra=100)
    resumo = montar_resumo("PETR4", queda, [{"titulo": "Noticia teste", "fonte": "Agencia"}])
    pdf = gerar_pdf_queda_bytes(resumo)
    assert pdf[:4] == b"%PDF"
