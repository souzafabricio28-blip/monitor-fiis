from pathlib import Path

from ui_theme import (
    CORES_GRAFICO,
    FUNDO,
    PRIMARIA,
    SUPERFICIE,
    TEXTO,
    cards_detalhe_i10,
    cards_resumo_i10,
)


def test_tema_config_usa_paleta_investidor10():
    texto = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert f'primaryColor = "{PRIMARIA}"' in texto
    assert f'backgroundColor = "{FUNDO}"' in texto
    assert f'secondaryBackgroundColor = "{SUPERFICIE}"' in texto
    assert f'textColor = "{TEXTO}"' in texto
    assert 'base = "light"' in texto
    assert PRIMARIA == "#009974"
    assert "Inter" in texto
    assert 'baseRadius = "0.5rem"' in texto


def test_paleta_de_graficos_nao_e_a_violeta_antiga():
    assert "#818CF8" not in CORES_GRAFICO
    assert PRIMARIA in CORES_GRAFICO


def test_cards_resumo_i10_formatam_nd():
    cards = cards_resumo_i10({}, "fii")
    assert [c["label"] for c in cards] == [
        "Cotação",
        "DY (12M)",
        "P/VP",
        "Liquidez diária",
        "Variação (12M)",
    ]
    assert all(c["valor"] == "N/D" for c in cards)


def test_cards_detalhe_fii_incluem_vacancia():
    cards = cards_detalhe_i10(
        {"vacancia": 2.9, "cotistas": 608340, "setor": "Logístico"},
        "fii",
    )
    vac = next(c for c in cards if c["label"] == "Vacância")
    assert vac["valor"] == "2,90%"
    cot = next(c for c in cards if c["label"] == "Cotistas")
    assert cot["valor"] == "608.340"
    assert cards_detalhe_i10({}, "acao") == []
