import sqlite3

import pytest

from migrate_db import TABELAS, _tabela_existe, migrar_sqlite_para_postgres


def test_migracao_cobre_todas_entidades():
    assert {
        "carteira",
        "watchlist",
        "cotacoes",
        "dividendos",
        "configuracoes",
        "avaliacoes",
        "movimentacoes",
    }.issubset(TABELAS)


def test_detecta_tabela_sqlite():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE carteira (ticker TEXT)")
    assert _tabela_existe(conn, "carteira")
    assert not _tabela_existe(conn, "watchlist")
    conn.close()


def test_migracao_recusa_destino_invalido(tmp_path):
    origem = tmp_path / "origem.db"
    sqlite3.connect(origem).close()
    with pytest.raises(ValueError):
        migrar_sqlite_para_postgres(str(origem), "sqlite:///destino.db")
