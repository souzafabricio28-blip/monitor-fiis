import db as db_module
from db import DatabaseManager
from portfolio import rentabilidade_total
from whatsapp_notifier import (
    alvo_de_preco_atingido,
    verificar_alertas_watchlist,
)


def _db_local(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    return DatabaseManager(str(tmp_path / "melhorias.db"))


def test_rentabilidade_total_soma_preco_e_proventos():
    lucro, pct = rentabilidade_total(110, 10, 100)
    assert lucro == 20
    assert pct == 20.0


def test_rentabilidade_total_nao_trata_cotacao_ausente_como_zero():
    assert rentabilidade_total(None, 10, 100) == (None, None)
    assert rentabilidade_total(110, None, 100) == (10, 10.0)
    assert rentabilidade_total(0, 0, 0) == (None, None)


def test_alvo_de_preco_exige_valores_reais():
    assert alvo_de_preco_atingido(9.5, 10) is True
    assert alvo_de_preco_atingido(10, 10) is True
    assert alvo_de_preco_atingido(10.01, 10) is False
    assert alvo_de_preco_atingido(None, 10) is False
    assert alvo_de_preco_atingido(0, 10) is False
    assert alvo_de_preco_atingido(9.5, None) is False


def test_watchlist_alerta_dedup_sem_rede(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.adicionar_watchlist("MXRF11", 10.0)
    db.set_config("whatsapp", {"ativar": True})
    monkeypatch.setenv("WHATSAPP_APIKEY", "teste-apikey")

    disparos = []

    def _fake_alerta(titulo, mensagem, tipo="info"):
        disparos.append((titulo, mensagem, tipo))
        return True

    monkeypatch.setattr("whatsapp_notifier.enviar_alerta", _fake_alerta)

    primeiro = verificar_alertas_watchlist(db, precos={"MXRF11": 9.5}, enviar=True)
    assert len(primeiro["disparados"]) == 1
    assert len(primeiro["enviados"]) == 1
    assert len(disparos) == 1

    segundo = verificar_alertas_watchlist(db, precos={"MXRF11": 9.2}, enviar=True)
    assert len(segundo["disparados"]) == 1
    assert segundo["enviados"] == []
    assert len(segundo["omitidos_dedup"]) == 1
    assert len(disparos) == 1

    acima = verificar_alertas_watchlist(db, precos={"MXRF11": 12.0}, enviar=True)
    assert acima["disparados"] == []

    de_novo = verificar_alertas_watchlist(db, precos={"MXRF11": 9.0}, enviar=True)
    assert len(de_novo["enviados"]) == 1
    assert len(disparos) == 2


def test_watchlist_sem_preco_nao_dispara(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.adicionar_watchlist("KNCR11", 100.0)
    resultado = verificar_alertas_watchlist(
        db, precos={"KNCR11": None}, enviar=False
    )
    assert resultado["disparados"] == []
    assert "KNCR11" in resultado["sem_preco"]


def test_preferencia_valores_persistida(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    assert db.get_config("mostrar_valores_financeiros", False) is False
    db.set_config("mostrar_valores_financeiros", True)
    outro = DatabaseManager(db.db_path)
    assert outro.get_config("mostrar_valores_financeiros") is True


def test_avaliar_fii_sem_scrape_usa_catalogo(monkeypatch):
    import pandas as pd

    import criterios

    def fail_scrape(*_a, **_k):
        raise AssertionError("scrape HTML não deveria ocorrer")

    monkeypatch.setattr(criterios, "_buscar_fiis_com", fail_scrape)
    monkeypatch.setattr(criterios, "_buscar_investidor10", fail_scrape)
    monkeypatch.setattr(criterios, "_ano_listagem_yahoo", fail_scrape)
    monkeypatch.setattr(
        "market_data.buscar_cotacao",
        lambda ticker: {"preco_atual": 10.0, "volume": 1000},
    )
    monkeypatch.setattr(
        "market_data.calcular_dy",
        lambda ticker, preco=None: {
            "dy_anual": 12.0,
            "dy_mensal": 1.0,
            "total_dividendos_12m": 1.2,
        },
    )
    monkeypatch.setattr(
        criterios, "checar_liquidez", lambda *a, **k: (True, 1_000_000, 500_000)
    )

    class _Yahoo:
        info = {"longName": "Maxi Renda", "priceToBook": 1.02}

        def history(self, period="5d"):
            return pd.DataFrame({"Close": [10.0], "Volume": [1000]})

    monkeypatch.setattr(criterios.yf, "Ticker", lambda *_a, **_k: _Yahoo())

    av = criterios.avaliar_fii("MXRF11", permitir_scrape=False)
    vac = next(c for c in av["criterios"] if "Vacância" in c["crit"])
    assert vac["ok"] is None
    assert vac["valor"] == "N/D"
    anos = next(c for c in av["criterios"] if "10 anos" in c["crit"])
    assert anos["ok"] is True
    dy = next(c for c in av["criterios"] if c["crit"].startswith("DY Mensal"))
    assert dy["ok"] is True
    assert av["dados"]["setor_final"] == "Papel"


def test_ano_listagem_catalogo_nao_raspa():
    from criterios import _ano_listagem

    assert _ano_listagem("MXRF11", "fii", permitir_scrape=False) == 2011
    assert _ano_listagem("KNRI11", "fii", permitir_scrape=False) == 2010
    assert _ano_listagem("XPML11", "fii", permitir_scrape=False) == 2017
