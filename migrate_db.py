"""
Migra dados do SQLite local para PostgreSQL (Neon/Render).

Uso:
  set DATABASE_URL=postgresql://...
  set SQLITE_PATH=caminho\\fii_data.db
  python migrate_db.py
"""

from __future__ import annotations

import os
import json
import sqlite3
import sys
from datetime import datetime

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import psycopg2

TABELAS = {
    "carteira": (
        ("ticker", "quantidade", "preco_compra", "data_compra"),
        ("ticker",),
    ),
    "cotacoes": (("ticker", "data", "preco"), ("ticker", "data")),
    "watchlist": (
        ("ticker", "preco_alvo", "data_adicionado", "notas"),
        ("ticker",),
    ),
    "dividendos": (
        ("ticker", "data_pagamento", "valor_por_cota"),
        ("ticker", "data_pagamento"),
    ),
    "cache_mercado": (("ticker", "payload", "atualizado_em"), ("ticker",)),
    "configuracoes": (("chave", "valor"), ("chave",)),
    "avaliacoes": (("ticker", "payload", "atualizado_em"), ("ticker",)),
    "movimentacoes": (
        (
            "ticker",
            "tipo",
            "quantidade",
            "preco_unitario",
            "taxas",
            "data_movimentacao",
            "observacoes",
            "idempotency_key",
        ),
        ("idempotency_key",),
    ),
}


def _tabela_existe(conn, tabela: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
        ).fetchone()
    )


def migrar_sqlite_para_postgres(sl_path: str, pg_url: str) -> dict:
    """Migra todas as entidades com upsert e retorna somente contagens."""
    if not pg_url or not pg_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL do PostgreSQL/Neon é obrigatória")
    if not os.path.exists(sl_path):
        raise FileNotFoundError(sl_path)

    # DatabaseManager cria/atualiza o schema PostgreSQL sem imprimir dados.
    from db import DatabaseManager

    auto_anterior = os.environ.pop("AUTO_MIGRATE_SQLITE", None)
    try:
        DatabaseManager(sl_path)
    finally:
        if auto_anterior is not None:
            os.environ["AUTO_MIGRATE_SQLITE"] = auto_anterior
    sl = sqlite3.connect(sl_path)
    pg = psycopg2.connect(pg_url)
    pg_cur = pg.cursor()
    iniciado = datetime.now().isoformat(timespec="seconds")
    relatorio = {"origem": {}, "destino_antes": {}, "destino_depois": {}}

    try:
        for tabela, (colunas, conflito) in TABELAS.items():
            if not _tabela_existe(sl, tabela):
                relatorio["origem"][tabela] = 0
                continue
            pg_cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            relatorio["destino_antes"][tabela] = int(pg_cur.fetchone()[0])
            rows = sl.execute(
                f"SELECT {', '.join(colunas)} FROM {tabela}"
            ).fetchall()
            relatorio["origem"][tabela] = len(rows)
            if not rows:
                continue

            atualizaveis = [c for c in colunas if c not in conflito]
            acao = (
                "DO UPDATE SET "
                + ", ".join(f"{c}=EXCLUDED.{c}" for c in atualizaveis)
                if atualizaveis
                else "DO NOTHING"
            )
            sql = (
                f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES "
                f"({', '.join(['%s'] * len(colunas))}) "
                f"ON CONFLICT ({', '.join(conflito)}) {acao}"
            )
            pg_cur.executemany(sql, rows)

        for tabela in TABELAS:
            pg_cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            relatorio["destino_depois"][tabela] = int(pg_cur.fetchone()[0])

        pg_cur.execute(
            "INSERT INTO sync_log (iniciado_em, concluido_em, status, contagens) "
            "VALUES (%s, %s, %s, %s)",
            (
                iniciado,
                datetime.now().isoformat(timespec="seconds"),
                "concluido",
                json.dumps(relatorio, ensure_ascii=False),
            ),
        )
        pg.commit()
        return relatorio
    except Exception:
        pg.rollback()
        raise
    finally:
        sl.close()
        pg.close()


def main():
    pg_url = os.environ.get("DATABASE_URL")
    sl_path = os.environ.get("SQLITE_PATH", "fii_data.db")
    try:
        relatorio = migrar_sqlite_para_postgres(sl_path, pg_url or "")
    except (ValueError, FileNotFoundError) as exc:
        print(f"Erro: {exc}")
        sys.exit(1)
    print("Migração concluída. Contagens (nenhuma posição foi exibida):")
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
