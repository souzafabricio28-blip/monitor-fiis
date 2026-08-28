import pandas as pd

import market_data
from scoring import calcular_score


class _TickerFake:
    def __init__(self, _symbol):
        indice = pd.date_range(
            end=pd.Timestamp.now(tz="America/Sao_Paulo"), periods=3, freq="90D"
        )
        self.dividends = pd.Series([1.0, 1.0, 1.0], index=indice)

    def history(self, period="5d"):
        return pd.DataFrame({"Close": [100.0]})


def test_dy_aceita_indice_com_timezone(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", _TickerFake)
    resultado = market_data.calcular_dy("XPTO11", preco=100)
    assert resultado is not None
    assert resultado["total_dividendos_12m"] == 3
    assert resultado["dy_anual"] == 3


def test_score_nao_premia_vacancia_ausente():
    assert calcular_score({}) == 50
    assert calcular_score({"vacancia": 0}) == 60


def test_divergencia_cruzada():
    assert market_data._divergencia_percentual(100, 111) == 11
    assert market_data._divergencia_percentual(None, 10) is None
