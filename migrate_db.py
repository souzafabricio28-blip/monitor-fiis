"""
Migra dados do SQLite local para PostgreSQL (Neon/Render).

Uso:
  set DATABASE_URL=postgresql://...
  set SQLITE_PATH=caminho\\fii_data.db
  python migrate_db.py
"""

from __future__ import annotations

import os
import sqlite3
import sys

import psycopg2


def main():
    pg_url = os.environ.get("DATABASE_URL")
    sl_path = os.environ.get("SQLITE_PATH", "fii_data.db")

    if not pg_url or not pg_url.startswith("postgresql"):
        print("Defina DATABASE_URL com a connection string do Neon/Postgres.")
        print("Exemplo: set DATABASE_URL=postgresql://user:pass@host/db?sslmode=require")
        sys.exit(1)

    if not os.path.exists(sl_path):
        print(f"Arquivo SQLite nao encontrado: {sl_path}")
        print("Defina SQLITE_PATH se o banco estiver em outro caminho.")
        sys.exit(1)

    sl = sqlite3.connect(sl_path)
    pg = psycopg2.connect(pg_url)
    sl_cur = sl.cursor()
    pg_cur = pg.cursor()

    pg_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS carteira (
            ticker TEXT PRIMARY KEY,
            quantidade INTEGER NOT NULL,
            preco_compra REAL NOT NULL,
            data_compra TEXT NOT NULL
        )
        """
    )
    pg_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cotacoes (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            data TEXT NOT NULL,
            preco REAL NOT NULL,
            UNIQUE(ticker, data)
        )
        """
    )
    pg_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            preco_alvo REAL,
            data_adicionado TEXT NOT NULL,
            notas TEXT,
            UNIQUE(ticker)
        )
        """
    )

    sl_cur.execute(
        "SELECT ticker, quantidade, preco_compra, data_compra FROM carteira"
    )
    rows = sl_cur.fetchall()
    print(f"Migrando {len(rows)} fiis da carteira...")
    for row in rows:
        pg_cur.execute(
            "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
            row,
        )
        print(f"  {row}")

    sl_cur.execute("SELECT ticker, data, preco FROM cotacoes")
    rows = sl_cur.fetchall()
    print(f"Migrando {len(rows)} cotacoes...")
    for row in rows:
        pg_cur.execute(
            "INSERT INTO cotacoes (ticker, data, preco) VALUES (%s, %s, %s) "
            "ON CONFLICT (ticker, data) DO NOTHING",
            row,
        )

    try:
        sl_cur.execute(
            "SELECT ticker, preco_alvo, data_adicionado, notas FROM watchlist"
        )
        rows = sl_cur.fetchall()
        print(f"Migrando {len(rows)} watchlist...")
        for row in rows:
            pg_cur.execute(
                "INSERT INTO watchlist (ticker, preco_alvo, data_adicionado, notas) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
                row,
            )
    except sqlite3.OperationalError:
        print("Tabela watchlist inexistente no SQLite — ignorando.")

    pg.commit()
    pg_cur.execute("SELECT COUNT(*) FROM carteira")
    print(f"\nVerificando: {pg_cur.fetchone()[0]} fiis no PostgreSQL")
    pg_cur.execute("SELECT * FROM carteira")
    for r in pg_cur.fetchall():
        print(f"  {r}")

    sl.close()
    pg.close()
    print("\nMigracao concluida!")


if __name__ == "__main__":
    main()
