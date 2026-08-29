from pathlib import Path

from ui_theme import CORES_GRAFICO, FUNDO, PRIMARIA, SUPERFICIE, TEXTO


def test_tema_config_usa_paleta_menta():
    texto = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert f'primaryColor = "{PRIMARIA}"' in texto
    assert f'backgroundColor = "{FUNDO}"' in texto
    assert f'secondaryBackgroundColor = "{SUPERFICIE}"' in texto
    assert f'textColor = "{TEXTO}"' in texto
    assert 'baseRadius = "0.85rem"' in texto
    assert 'buttonRadius = "full"' in texto
    assert "Outfit" in texto
    assert "DM Sans" in texto


def test_paleta_de_graficos_nao_e_a_violeta_antiga():
    assert "#818CF8" not in CORES_GRAFICO
    assert PRIMARIA in CORES_GRAFICO
