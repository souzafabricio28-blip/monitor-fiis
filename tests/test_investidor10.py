from pathlib import Path

from investidor10 import (
    Investidor10API,
    classe_investidor10,
    extrair_percentual,
    extrair_valor_br,
    extrair_valor_compacto,
    formatar_compacto,
    url_ativo,
)


def test_parser_brasileiro_preserva_nd():
    assert extrair_valor_br("R$ 1.234,56") == 1234.56
    assert extrair_valor_br("5,25") == 5.25
    assert extrair_valor_br("N/D") is None
    assert extrair_percentual("12,34%") == 12.34
    assert extrair_valor_compacto("R$ 17,30 M") == 17_300_000
    assert extrair_valor_compacto("R$ 7,59 Bilhões") == 7_590_000_000
    assert formatar_compacto(17_300_000) == "R$ 17,30 M"
    assert formatar_compacto(float("nan")) == "N/D"
    from investidor10 import formatar_numero, formatar_pct, numero_valido, valor_ausente

    assert numero_valido(float("nan")) is None
    assert numero_valido(float("inf")) is None
    assert numero_valido(9.3) == 9.3
    assert valor_ausente(float("nan")) is True
    assert valor_ausente(0) is False
    assert valor_ausente("Híbrido") is False
    assert formatar_pct(float("nan")) == "N/D"
    assert formatar_numero(float("nan")) == "N/D"


def test_parser_html_sem_rede():
    html = (Path(__file__).parent / "fixtures" / "investidor10_fii.html").read_text(
        encoding="utf-8"
    )
    dados = Investidor10API().parse_html("XPTO11", html)
    assert dados["preco"] == 101.25
    assert dados["dy"] == 12.34
    assert dados["p_vp"] == 0.98
    assert dados["patrimonio"] == 1_500_000_000
    assert dados["vacancia"] == 7.25
    assert dados["setor"].lower() == "logístico"


def test_parser_hglg11_estilo_investidor10():
    html = (Path(__file__).parent / "fixtures" / "investidor10_hglg11.html").read_text(
        encoding="utf-8"
    )
    dados = Investidor10API().parse_html("HGLG11", html)
    assert dados["preco"] == 148.09
    assert dados["variacao_dia"] == 0.02
    assert dados["dy"] == 8.91
    assert dados["p_vp"] == 0.89
    assert dados["liquidez_diaria"] == 17_300_000
    assert dados["variacao_12m"] == 4.81
    assert dados["vacancia"] == 2.9
    assert dados["cotistas"] == 608340
    assert dados["cotas_emitidas"] == 45601734
    assert dados["vp_cota"] == 166.43
    assert dados["patrimonio"] == 7_590_000_000
    assert dados["taxa_administracao"] == 0.6
    assert dados["gestao"] == "Ativa"
    assert dados["ultimo_rendimento"] == 1.17
    assert "Logístico" in dados["setor"]
    assert dados["tipo"] == "Fundo de Tijolo"


def test_parser_petr4_cards():
    html = (Path(__file__).parent / "fixtures" / "investidor10_petr4.html").read_text(
        encoding="utf-8"
    )
    dados = Investidor10API().parse_html("PETR4", html)
    assert dados["preco"] == 43.55
    assert dados["variacao_dia"] == 1.99
    assert dados["variacao_12m"] == 48.12
    assert dados["p_l"] == 4.21
    assert dados["p_vp"] == 1.17
    assert dados["dy"] == 8.47


def test_url_fii_vs_acao():
    assert classe_investidor10("HGLG11") == "fii"
    assert classe_investidor10("TAEE11") == "acao"
    assert classe_investidor10("PETR4") == "acao"
    assert url_ativo("HGLG11").endswith("/fiis/hglg11/")
    assert url_ativo("PETR4").endswith("/acoes/petr4/")
    assert url_ativo("TAEE11").endswith("/acoes/taee11/")
