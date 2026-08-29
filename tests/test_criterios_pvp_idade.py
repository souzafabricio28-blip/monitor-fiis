from criterios import (
    _criterio_idade_fii,
    escolher_pvp_acao,
    parse_pvp_fundamentus,
)


HTML_FUNDAMENTUS = """
<table class="w728">
<tr>
<td class="label"><span class="txt">P/L</span></td>
<td class="data"><span class="txt">5,42</span></td>
<td class="label"><span class="txt">P/VP</span></td>
<td class="data"><span class="txt">0,81</span></td>
</tr>
</table>
"""

HTML_KLBN = """
<td class="label">P/VP</td>
<td class="data">2,47</td>
"""


def test_parse_pvp_fundamentus_sapr4():
    assert parse_pvp_fundamentus(HTML_FUNDAMENTUS) == 0.81


def test_parse_pvp_fundamentus_klbn4():
    assert parse_pvp_fundamentus(HTML_KLBN) == 2.47


def test_parse_pvp_fundamentus_ausente_nao_vira_zero():
    assert parse_pvp_fundamentus("<html>sem indicador</html>") is None
    assert parse_pvp_fundamentus("") is None


def test_escolher_pvp_acao_prefere_fundamentus_ao_yahoo_distorcido():
    valor, fonte = escolher_pvp_acao(0.16, 0.81)
    assert valor == 0.81
    assert fonte == "fundamentus"

    valor, fonte = escolher_pvp_acao(0.49, 2.47)
    assert valor == 2.47
    assert fonte == "fundamentus"


def test_escolher_pvp_acao_cai_para_preco_sobre_vpa():
    valor, fonte = escolher_pvp_acao(0.16, None, book_value=7.0, preco=5.67)
    assert fonte == "preco/vpa"
    assert abs(valor - (5.67 / 7.0)) < 1e-9


def test_escolher_pvp_acao_yahoo_so_como_ultimo_recurso():
    valor, fonte = escolher_pvp_acao(0.16, None)
    assert valor == 0.16
    assert fonte == "yahoo"


def test_idade_fii_incorporacao_passa_mesmo_com_ticker_jovem():
    xplg = _criterio_idade_fii("XPLG11", 2018)
    assert xplg["ok"] is True
    assert "incorporação" in xplg["valor"].lower() or "incorporacao" in xplg["valor"].lower()

    hsml = _criterio_idade_fii("HSML11", 2018)
    assert hsml["ok"] is True

    rztr = _criterio_idade_fii("RZTR11", 2020)
    assert rztr["ok"] is True


def test_idade_fii_sem_incorporacao_respeita_dez_anos():
    mxrf = _criterio_idade_fii("MXRF11", 2011)
    assert mxrf["ok"] is True

    jovem = _criterio_idade_fii("MANA11", 2022)
    assert jovem["ok"] is False

    sem_dado = _criterio_idade_fii("XXXX11", None)
    assert sem_dado["ok"] is None
    assert sem_dado["valor"] == "N/D"


def test_idade_fii_incorporacao_sem_ano_do_ticker_ainda_passa():
    av = _criterio_idade_fii("XPLG11", None)
    assert av["ok"] is True
    assert av["valor"] != "N/D"


def test_avaliar_acao_usa_pvp_fundamentus(monkeypatch):
    import pandas as pd

    import criterios

    class _Yahoo:
        info = {
            "longName": "Sanepar",
            "priceToBook": 0.16,
            "bookValue": 7.0,
            "dividendYield": 0.06,
            "sector": "Utilities",
            "totalDebt": 1,
            "totalStockholderEquity": 10,
        }
        financials = pd.DataFrame()

        def history(self, period="5d"):
            return pd.DataFrame({"Close": [5.67], "Volume": [1_000_000]})

    monkeypatch.setattr(criterios.yf, "Ticker", lambda *_a, **_k: _Yahoo())
    monkeypatch.setattr(criterios, "_pvp_fundamentus", lambda ticker: 0.81)
    monkeypatch.setattr(criterios, "_lucro_5_anos", lambda ticker: {"anos": 5, "passou": True})
    monkeypatch.setattr(criterios, "_divida_patrimonio", lambda ticker: {"passou": True, "divida": 1, "patrimonio": 10})
    monkeypatch.setattr(criterios, "_crescimento_10_anos", lambda ticker: {"passou": True, "anos": 5})
    monkeypatch.setattr(criterios, "checar_liquidez", lambda *a, **k: (True, 1_000_000, 500_000))

    av = criterios.avaliar_acao("SAPR4", permitir_scrape=False)
    pvp = next(c for c in av["criterios"] if c["crit"].startswith("P/VP"))
    assert pvp["ok"] is True
    assert pvp["valor"] == "0.81"
    assert "fundamentus" in pvp["obs"]
    assert av["dados"]["p_vp_fonte"] == "fundamentus"
