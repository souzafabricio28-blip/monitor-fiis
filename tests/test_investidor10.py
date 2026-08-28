from pathlib import Path

from investidor10 import Investidor10API, extrair_percentual, extrair_valor_br


def test_parser_brasileiro_preserva_nd():
    assert extrair_valor_br("R$ 1.234,56") == 1234.56
    assert extrair_valor_br("5,25") == 5.25
    assert extrair_valor_br("N/D") is None
    assert extrair_percentual("12,34%") == 12.34


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
