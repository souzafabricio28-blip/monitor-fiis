from queda_report import (
    _parse_infomoney_posts,
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


def test_pdf_queda_varias_manchetes_longas():
    """fpdf2 deixa o cursor à direita após multi_cell; várias fontes quebravam o PDF."""
    queda = gatilhos_de_queda(80, preco_compra=100)
    noticias = [
        {
            "titulo": "Fundo recua apos resultado e mercado reage com vendas",
            "fonte": "InfoMoney",
        },
        {
            "titulo": "https://www.infomoney.com.br/mercados/" + ("mxrf11-queda-longa-" * 12),
            "fonte": "Google News",
        },
        {
            "titulo": "Gestora comenta desconto em relacao ao valor patrimonial",
            "fonte": "Yahoo Finance",
        },
    ]
    resumo = montar_resumo("MXRF11", queda, noticias)
    pdf = gerar_pdf_queda_bytes(resumo)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 200


def test_parse_infomoney_posts():
    posts = [
        {
            "title": {"rendered": "MXRF11 recua ap&#243;s resultado"},
            "excerpt": {"rendered": "<p>O fundo caiu no preg&#227;o.</p>"},
            "link": "https://www.infomoney.com.br/mercados/mxrf11-recua/",
        },
        {"title": {"rendered": "Sem link"}, "excerpt": {"rendered": ""}, "link": ""},
    ]
    itens = _parse_infomoney_posts(posts, 8)
    assert len(itens) == 1
    assert itens[0]["titulo"] == "MXRF11 recua após resultado"
    assert itens[0]["origem"] == "InfoMoney"
    assert "caiu" in itens[0]["resumo"]
    assert itens[0]["link"].startswith("https://www.infomoney.com.br/")
