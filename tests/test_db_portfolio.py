from datetime import datetime

import db as db_module
from db import DatabaseManager
from portfolio import _proventos_registrados


def _db_local(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    return DatabaseManager(str(tmp_path / "teste.db"))


def test_movimentacoes_preco_medio_e_venda(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.registrar_movimentacao("XPTO11", "COMPRA", 10, 10, taxas=1)
    db.registrar_movimentacao("XPTO11", "COMPRA", 10, 20, taxas=1)
    posicao = db.obter_carteira().iloc[0]
    assert posicao["quantidade"] == 20
    assert posicao["preco_compra"] == 15.1

    db.registrar_movimentacao("XPTO11", "VENDA", 5, 25, taxas=0.5)
    posicao = db.obter_carteira().iloc[0]
    assert posicao["quantidade"] == 15
    assert posicao["preco_compra"] == 15.1


def test_idempotencia_e_provento_efetivo(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    chave = "compra-importada-1"
    hoje = datetime.now().strftime("%Y-%m-%d")
    db.registrar_movimentacao(
        "XPTO11", "COMPRA", 10, 10, data_movimentacao=hoje, idempotency_key=chave
    )
    db.registrar_movimentacao(
        "XPTO11", "COMPRA", 10, 10, data_movimentacao=hoje, idempotency_key=chave
    )
    assert len(db.obter_movimentacoes("XPTO11")) == 1
    db.salvar_dividendo("XPTO11", hoje, 1.25)
    assert _proventos_registrados(db, "XPTO11") == 12.5


def test_schema_e_consultas_portaveis(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    assert len(db.obter_cotacoes("XPTO11", dias=30)) == 0
    assert len(db.obter_dividendos(meses=12)) == 0
    conn = db._get_conn()
    assert conn.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] == 2
    conn.close()
    monkeypatch.setattr(db_module, "USE_POSTGRES", True)
    assert db_module._ph() == "%s"


def test_token_telegram_legado_e_removido(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.set_config(
        "telegram", {"ativar": True, "token": "nao-pode-ficar", "chat_id": "123"}
    )
    db = DatabaseManager(db.db_path)
    assert db.get_config("telegram") == {"ativar": True}
