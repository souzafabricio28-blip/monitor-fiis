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
    assert len(resultado["pagamentos"]) == 3
    assert resultado["pagamentos"][0]["valor"] == 1.0


def test_score_nao_premia_vacancia_ausente():
    assert calcular_score({}) == 50
    assert calcular_score({"vacancia": 0}) == 60


def test_sincroniza_proventos_no_sqlite(tmp_path, monkeypatch):
    import db as db_module
    from db import DatabaseManager
    from market_data import sincronizar_proventos
    from portfolio import _proventos_registrados

    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    db = DatabaseManager(str(tmp_path / "div.db"))
    db.registrar_movimentacao(
        "MXRF11", "SALDO_INICIAL", 40, 9.23, data_movimentacao="2025-12-01"
    )
    gravados = sincronizar_proventos(
        db,
        "MXRF11",
        [{"data": "2026-01-15", "valor": 0.10}, {"data": "2026-02-15", "valor": 0.10}],
    )
    assert gravados == 2
    assert _proventos_registrados(db, "MXRF11") == 8.0


def test_dados_sem_fundamentos_nao_raspa(monkeypatch):
    chamadas = []
    extras = []
    monkeypatch.setattr(
        market_data._api, "buscar_ativo", lambda ticker: chamadas.append(ticker) or {"erro": "x"}
    )
    monkeypatch.setattr(
        market_data, "consultar_fontes_extras", lambda ticker: extras.append(ticker) or []
    )
    monkeypatch.setattr(
        market_data,
        "buscar_cotacao",
        lambda ticker: {"preco_atual": 9.5, "preco": 9.5, "variacao": 0},
    )
    monkeypatch.setattr(
        market_data,
        "calcular_dy",
        lambda ticker, preco=None: {
            "dy_anual": 12.0,
            "dy_mensal": 1.0,
            "total_dividendos_12m": 1.2,
            "pagamentos": [],
        },
    )
    market_data.limpar_cache_memoria()
    dados = market_data.buscar_dados_completos(
        "MXRF11", incluir_fundamentos=False, usar_cache=False
    )
    assert chamadas == []
    assert extras == []
    assert dados["preco_atual"] == 9.5
    assert dados.get("vacancia") is None
    assert dados["dy"] == 12.0


def test_close_de_historico_multiindex():
    cols = pd.MultiIndex.from_product([["Close"], ["MXRF11.SA", "KNCR11.SA"]])
    hist = pd.DataFrame([[9.1, 10.2], [9.3, 10.4]], columns=cols)
    assert market_data._close_de_historico(hist, "MXRF11.SA") == 9.3
    cols2 = pd.MultiIndex.from_product([["MXRF11.SA"], ["Open", "Close"]])
    hist2 = pd.DataFrame([[9.0, 9.4]], columns=cols2)
    assert market_data._close_de_historico(hist2, "MXRF11.SA") == 9.4


def test_buscar_cotacoes_lote_usa_download(monkeypatch):
    cols = pd.MultiIndex.from_product([["Close"], ["MXRF11.SA", "PETR4.SA"]])
    hist = pd.DataFrame([[10.0, 40.0]], columns=cols)

    def _download(**_kwargs):
        return hist

    monkeypatch.setattr(market_data.yf, "download", _download)
    monkeypatch.setattr(market_data, "_cotacao_do_investidor10", lambda _t: None)
    lote = market_data.buscar_cotacoes_lote(["MXRF11", "PETR4"])
    assert lote["MXRF11"]["preco_atual"] == 10.0
    assert lote["PETR4"]["preco_atual"] == 40.0


def test_lote_prefere_cotacao_investidor10(monkeypatch):
    monkeypatch.setattr(
        market_data,
        "_cotacao_do_investidor10",
        lambda ticker: {
            "ticker": ticker,
            "preco_atual": 13.57,
            "preco": 13.57,
            "fonte": "Investidor10",
            "dy": 8.43,
        },
    )
    saida = {"ITSA3": {"preco_atual": 1.35, "fonte": "Yahoo Finance"}}
    market_data._aplicar_cotacoes_investidor10(saida, ["ITSA3"])
    assert saida["ITSA3"]["preco_atual"] == 13.57
    assert saida["ITSA3"]["fonte"] == "Investidor10"
    assert saida["ITSA3"]["preco_yahoo"] == 1.35


def test_cotacao_usa_ultimo_close_valido(monkeypatch):
    class _Ticker:
        def __init__(self, _symbol):
            pass

        def history(self, period="5d"):
            return pd.DataFrame(
                {
                    "Close": [9.30, float("nan")],
                    "Open": [9.20, 9.25],
                    "High": [9.40, 9.40],
                    "Low": [9.10, 9.20],
                    "Volume": [1000, float("nan")],
                }
            )

    monkeypatch.setattr(market_data.yf, "Ticker", _Ticker)
    cotacao = market_data.buscar_cotacao("MXRF11")
    assert cotacao is not None
    assert cotacao["preco_atual"] == 9.3
    assert cotacao["variacao_dia"] is not None
