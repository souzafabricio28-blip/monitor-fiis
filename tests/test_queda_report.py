from queda_report import (
    _custo_desatualizado,
    _noticia_do_ticker,
    _parse_infomoney_posts,
    complementar_motivo_com_ia,
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


def test_descarta_manchete_de_itsa4_e_agenda():
    assert not _noticia_do_ticker(
        "ITSA3",
        {"titulo": "Itaúsa (ITSA4) pagará R$ 2,8 bi em proventos no dia 28; veja valor por ação"},
    )
    assert not _noticia_do_ticker(
        "ITSA3",
        {"titulo": "Petrobras, Itaú e Weg pagam dividendos em agosto; veja a agenda completa"},
    )
    assert not _noticia_do_ticker(
        "ITSA3",
        {"titulo": "Allos, Equatorial e Alupar pagam dividendos em julho; veja agenda completa"},
    )
    assert _noticia_do_ticker(
        "ITSA3",
        {"titulo": "ITSA3 recua após realização de lucros na B3"},
    )


def test_custo_desatualizado_nao_inventa_tombo():
    queda = gatilhos_de_queda(
        13.57,
        preco_compra=26.55,
        preco_anterior=13.60,
        maxima_periodo=14.10,
    )
    assert queda["atingiu"] is True
    assert _custo_desatualizado(queda) is True
    resumo = montar_resumo(
        "ITSA3",
        queda,
        [
            {
                "titulo": "Itaúsa (ITSA4) pagará R$ 2,8 bi em proventos no dia 28; veja valor por ação",
                "fonte": "InfoMoney",
            }
        ],
    )
    assert resumo["custo_desatualizado"] is True
    assert resumo["noticias"] == []
    assert "custo desatualizado" in resumo["abertura"].casefold()
    assert "ITSA4" not in resumo["motivo"]
    assert resumo["motivo_curto"] == "Custo na carteira desatualizado"
    queda = gatilhos_de_queda(80, preco_compra=100)
    resumo = montar_resumo(
        "PETR4",
        queda,
        [{"titulo": "Petrobras anuncia corte de produção", "fonte": "Valor"}],
    )
    assert "corte de produção" in resumo["motivo"]
    assert resumo["motivo_curto"].startswith("Petrobras")
    assert "Motivo mais citado" in resumo["motivo"]


def test_motivo_prioriza_manchete_de_queda():
    queda = gatilhos_de_queda(80, preco_compra=100)
    resumo = montar_resumo(
        "MXRF11",
        queda,
        [
            {"titulo": "Selic permanece e mercado discute fundos", "fonte": "Geral"},
            {
                "titulo": "MXRF11 recua apos resultado abaixo do esperado",
                "fonte": "InfoMoney",
                "resumo": "O fundo caiu no pregao apos numeros fracos de inadimplencia.",
            },
        ],
    )
    assert "recua" in resumo["motivo_curto"].casefold()
    assert "inadimplencia" in resumo["motivo"].casefold()
    assert "MXRF11 caiu" in resumo["motivo"]


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


def test_pdf_queda_muitas_manchetes_quebra_pagina():
    """Cabeçalho na 2ª página não pode deixar o cursor sem largura."""
    queda = gatilhos_de_queda(80, preco_compra=100)
    noticias = [
        {
            "titulo": f"Manchete {i} " + ("queda de fundos imobiliarios no mercado " * 6),
            "fonte": f"Fonte {i}",
        }
        for i in range(20)
    ]
    resumo = montar_resumo("HGLG11", queda, noticias)
    pdf = gerar_pdf_queda_bytes(resumo)
    assert pdf[:4] == b"%PDF"
    assert b"/Type /Page" in pdf or b"/Type/Page" in pdf


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


def test_ia_substitui_motivo_quando_ha_chave(monkeypatch):
    queda = gatilhos_de_queda(80, preco_compra=100)
    resumo = montar_resumo(
        "PETR4",
        queda,
        [{"titulo": "Petrobras anuncia corte de producao", "fonte": "Valor"}],
    )

    monkeypatch.setattr(
        "vigia._chave_llm",
        lambda: ("tok", "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4o-mini"),
    )

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "A queda veio do corte de producao anunciado pela Petrobras, "
                                "segundo a manchete do Valor."
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr("queda_report.requests.post", lambda *a, **k: _Resp())
    out = complementar_motivo_com_ia(resumo)
    assert out["motivo_ia"] is True
    assert "corte de producao" in out["motivo"].casefold()
    assert out["motivo_curto"].startswith("A queda veio")
