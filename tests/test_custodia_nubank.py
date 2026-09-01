from custodia_nubank import (
    CHAVE_SYNC,
    CUSTODIA_NUBANK_20260901,
    sincronizar_custodia_nubank,
)
import db as db_module
from db import DatabaseManager


def _db_local(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    return DatabaseManager(str(tmp_path / "custodia.db"))


def test_sincronizar_custodia_nubank_ajusta_e_realoca(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.registrar_movimentacao("MXRF11", "SALDO_INICIAL", 59, 9.23)
    db.registrar_movimentacao("PETR4", "SALDO_INICIAL", 5, 42.26)
    db.registrar_movimentacao("ITSA3", "SALDO_INICIAL", 2, 26.50)
    db.registrar_movimentacao("RURA11", "SALDO_INICIAL", 12, 8.14)

    primeiro = sincronizar_custodia_nubank(db)
    assert primeiro["aplicado"] is True

    carteira = {
        str(r["ticker"]).upper(): int(r["quantidade"])
        for _, r in db.obter_carteira().iterrows()
    }
    assert carteira["MXRF11"] == 48
    assert carteira["PETR4"] == 4
    assert "ITSA3" not in carteira
    assert carteira["ITSA4"] == 2
    assert "RURA11" not in carteira
    assert set(carteira) == set(CUSTODIA_NUBANK_20260901)

    segundo = sincronizar_custodia_nubank(db)
    assert segundo["aplicado"] is False
    assert db.get_config(CHAVE_SYNC)
