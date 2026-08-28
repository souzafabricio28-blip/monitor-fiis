"""
Persistência unificada: SQLite (local) ou PostgreSQL (Neon/Render).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional

import pandas as pd

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))


def _ph() -> str:
    return "%s" if USE_POSTGRES else "?"


class DatabaseManager:
    """Gerencia carteira, cotações, watchlist, cache e configurações."""

    def __init__(self, db_path: str = "fii_data.db"):
        self.db_path = db_path
        self.use_pg = USE_POSTGRES
        self.init_database()

    def _get_conn(self):
        if self.use_pg:
            import psycopg2

            return psycopg2.connect(DATABASE_URL)
        return sqlite3.connect(self.db_path)

    def init_database(self):
        conn = self._get_conn()
        cur = conn.cursor()

        if self.use_pg:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS carteira (
                    ticker TEXT PRIMARY KEY,
                    quantidade INTEGER NOT NULL,
                    preco_compra REAL NOT NULL,
                    data_compra TEXT NOT NULL
                )
                """
            )
            cur.execute(
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
            cur.execute(
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dividendos (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    data_pagamento TEXT NOT NULL,
                    valor_por_cota REAL NOT NULL,
                    UNIQUE(ticker, data_pagamento)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_mercado (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS avaliacoes (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )
                """
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS carteira (
                    ticker TEXT PRIMARY KEY,
                    quantidade INTEGER NOT NULL,
                    preco_compra REAL NOT NULL,
                    data_compra TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cotacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    data TEXT NOT NULL,
                    preco REAL NOT NULL,
                    UNIQUE(ticker, data)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    preco_alvo REAL,
                    data_adicionado TEXT NOT NULL,
                    notas TEXT,
                    UNIQUE(ticker)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dividendos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    data_pagamento TEXT NOT NULL,
                    valor_por_cota REAL NOT NULL,
                    UNIQUE(ticker, data_pagamento)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_mercado (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS avaliacoes (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )
                """
            )

        conn.commit()
        conn.close()

        if self.use_pg:
            self._migrate_sqlite_if_needed()

    def _migrate_sqlite_if_needed(self):
        pg_conn = self._get_conn()
        pg_cur = pg_conn.cursor()
        pg_cur.execute("SELECT COUNT(*) FROM carteira")
        if pg_cur.fetchone()[0] > 0:
            pg_conn.close()
            return

        if not os.path.exists(self.db_path):
            pg_conn.close()
            return

        try:
            sl_conn = sqlite3.connect(self.db_path)
            sl_cur = sl_conn.cursor()

            sl_cur.execute(
                "SELECT ticker, quantidade, preco_compra, data_compra FROM carteira"
            )
            for row in sl_cur.fetchall():
                pg_cur.execute(
                    "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
                    row,
                )

            sl_cur.execute("SELECT ticker, data, preco FROM cotacoes")
            for row in sl_cur.fetchall():
                pg_cur.execute(
                    "INSERT INTO cotacoes (ticker, data, preco) VALUES (%s, %s, %s) "
                    "ON CONFLICT (ticker, data) DO NOTHING",
                    row,
                )

            try:
                sl_cur.execute(
                    "SELECT ticker, preco_alvo, data_adicionado, notas FROM watchlist"
                )
                for row in sl_cur.fetchall():
                    pg_cur.execute(
                        "INSERT INTO watchlist (ticker, preco_alvo, data_adicionado, notas) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
                        row,
                    )
            except sqlite3.OperationalError:
                pass

            pg_conn.commit()
            sl_conn.close()
        finally:
            pg_conn.close()

    def obter_carteira(self) -> pd.DataFrame:
        conn = self._get_conn()
        try:
            return pd.read_sql_query("SELECT * FROM carteira ORDER BY ticker", conn)
        finally:
            conn.close()

    def adicionar_fii(self, ticker: str, quantidade: int, preco: float):
        """Soma cotas e recalcula preço médio (não apaga a posição)."""
        ticker = ticker.upper().replace(".SA", "").strip()
        conn = self._get_conn()
        cur = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d")
        ph = _ph()

        cur.execute(
            f"SELECT quantidade, preco_compra FROM carteira WHERE ticker = {ph}",
            (ticker,),
        )
        existente = cur.fetchone()

        if existente:
            qtd_antiga = int(existente[0])
            preco_antigo = float(existente[1])
            nova_qtd = qtd_antiga + quantidade
            preco_medio = ((qtd_antiga * preco_antigo) + (quantidade * preco)) / nova_qtd
            cur.execute(
                f"UPDATE carteira SET quantidade = {ph}, preco_compra = {ph}, "
                f"data_compra = {ph} WHERE ticker = {ph}",
                (nova_qtd, round(preco_medio, 4), data, ticker),
            )
        else:
            cur.execute(
                f"INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) "
                f"VALUES ({ph}, {ph}, {ph}, {ph})",
                (ticker, quantidade, preco, data),
            )

        conn.commit()
        conn.close()

    def atualizar_carteira(self, ticker: str, quantidade: int, preco_compra: float):
        """Substitui a posição (usado pelo CLI)."""
        ticker = ticker.upper().replace(".SA", "").strip()
        conn = self._get_conn()
        cur = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d")
        ph = _ph()

        if self.use_pg:
            cur.execute(
                "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO UPDATE SET "
                "quantidade = EXCLUDED.quantidade, preco_compra = EXCLUDED.preco_compra, "
                "data_compra = EXCLUDED.data_compra",
                (ticker, quantidade, preco_compra, data),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO carteira (ticker, quantidade, preco_compra, data_compra) "
                "VALUES (?, ?, ?, ?)",
                (ticker, quantidade, preco_compra, data),
            )
        conn.commit()
        conn.close()

    def remover_fii(self, ticker: str):
        ticker = ticker.upper().replace(".SA", "").strip()
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM carteira WHERE ticker = {_ph()}", (ticker,))
        conn.commit()
        conn.close()

    def salvar_cotacao(self, ticker: str, preco: float, data: Optional[str] = None):
        ticker = ticker.upper().replace(".SA", "").strip()
        data = data or datetime.now().strftime("%Y-%m-%d")
        conn = self._get_conn()
        cur = conn.cursor()
        if self.use_pg:
            cur.execute(
                "INSERT INTO cotacoes (ticker, data, preco) VALUES (%s, %s, %s) "
                "ON CONFLICT (ticker, data) DO UPDATE SET preco = EXCLUDED.preco",
                (ticker, data, preco),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO cotacoes (ticker, data, preco) VALUES (?, ?, ?)",
                (ticker, data, preco),
            )
        conn.commit()
        conn.close()

    def obter_cotacoes(self, ticker: str, dias: int = 30) -> pd.DataFrame:
        conn = self._get_conn()
        ph = _ph()
        try:
            return pd.read_sql_query(
                f"SELECT data, preco FROM cotacoes WHERE ticker = {ph} "
                f"AND data >= date('now', '-{int(dias)} days') ORDER BY data",
                conn,
                params=(ticker.upper(),),
            )
        finally:
            conn.close()

    def salvar_dividendo(self, ticker: str, data_pagamento: str, valor: float):
        conn = self._get_conn()
        cur = conn.cursor()
        if self.use_pg:
            cur.execute(
                "INSERT INTO dividendos (ticker, data_pagamento, valor_por_cota) "
                "VALUES (%s, %s, %s) ON CONFLICT (ticker, data_pagamento) "
                "DO UPDATE SET valor_por_cota = EXCLUDED.valor_por_cota",
                (ticker.upper(), data_pagamento, valor),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO dividendos "
                "(ticker, data_pagamento, valor_por_cota) VALUES (?, ?, ?)",
                (ticker.upper(), data_pagamento, valor),
            )
        conn.commit()
        conn.close()

    def obter_dividendos(self, ticker: Optional[str] = None, meses: int = 12) -> pd.DataFrame:
        conn = self._get_conn()
        try:
            if ticker:
                return pd.read_sql_query(
                    f"SELECT * FROM dividendos WHERE ticker = {_ph()} "
                    f"ORDER BY data_pagamento DESC",
                    conn,
                    params=(ticker.upper(),),
                )
            return pd.read_sql_query(
                "SELECT * FROM dividendos ORDER BY data_pagamento DESC",
                conn,
            )
        finally:
            conn.close()

    def adicionar_watchlist(
        self, ticker: str, preco_alvo: Optional[float] = None, notas: str = ""
    ):
        ticker = ticker.upper().replace(".SA", "").strip()
        conn = self._get_conn()
        cur = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d %H:%M")
        if self.use_pg:
            cur.execute(
                "INSERT INTO watchlist (ticker, preco_alvo, data_adicionado, notas) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO UPDATE SET "
                "preco_alvo = EXCLUDED.preco_alvo, notas = EXCLUDED.notas, "
                "data_adicionado = EXCLUDED.data_adicionado",
                (ticker, preco_alvo, data, notas),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO watchlist "
                "(ticker, preco_alvo, data_adicionado, notas) VALUES (?, ?, ?, ?)",
                (ticker, preco_alvo, data, notas),
            )
        conn.commit()
        conn.close()

    def remover_watchlist(self, ticker: str):
        ticker = ticker.upper().replace(".SA", "").strip()
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM watchlist WHERE ticker = {_ph()}", (ticker,))
        conn.commit()
        conn.close()

    def obter_watchlist(self) -> pd.DataFrame:
        conn = self._get_conn()
        try:
            return pd.read_sql_query(
                "SELECT * FROM watchlist ORDER BY data_adicionado DESC", conn
            )
        finally:
            conn.close()

    def get_cache(self, ticker: str, max_age_minutes: int = 20) -> Optional[dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT payload, atualizado_em FROM cache_mercado WHERE ticker = {_ph()}",
            (ticker.upper(),),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        try:
            atualizado = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            idade = (datetime.now() - atualizado).total_seconds() / 60
            if idade > max_age_minutes:
                return None
            return json.loads(row[0])
        except Exception:
            return None

    def set_cache(self, ticker: str, payload: dict):
        conn = self._get_conn()
        cur = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        if self.use_pg:
            cur.execute(
                "INSERT INTO cache_mercado (ticker, payload, atualizado_em) "
                "VALUES (%s, %s, %s) ON CONFLICT (ticker) DO UPDATE SET "
                "payload = EXCLUDED.payload, atualizado_em = EXCLUDED.atualizado_em",
                (ticker.upper(), raw, agora),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO cache_mercado (ticker, payload, atualizado_em) "
                "VALUES (?, ?, ?)",
                (ticker.upper(), raw, agora),
            )
        conn.commit()
        conn.close()

    def get_config(self, chave: str, default: Any = None) -> Any:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT valor FROM configuracoes WHERE chave = {_ph()}", (chave,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return row[0]

    def set_config(self, chave: str, valor: Any):
        conn = self._get_conn()
        cur = conn.cursor()
        raw = json.dumps(valor, ensure_ascii=False)
        if self.use_pg:
            cur.execute(
                "INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) "
                "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor",
                (chave, raw),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                (chave, raw),
            )
        conn.commit()
        conn.close()

    def salvar_avaliacao(self, ticker: str, payload: dict):
        conn = self._get_conn()
        cur = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        if self.use_pg:
            cur.execute(
                "INSERT INTO avaliacoes (ticker, payload, atualizado_em) "
                "VALUES (%s, %s, %s) ON CONFLICT (ticker) DO UPDATE SET "
                "payload = EXCLUDED.payload, atualizado_em = EXCLUDED.atualizado_em",
                (ticker.upper(), raw, agora),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO avaliacoes (ticker, payload, atualizado_em) "
                "VALUES (?, ?, ?)",
                (ticker.upper(), raw, agora),
            )
        conn.commit()
        conn.close()

    def obter_avaliacao(self, ticker: str, max_age_hours: int = 24) -> Optional[dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT payload, atualizado_em FROM avaliacoes WHERE ticker = {_ph()}",
            (ticker.upper(),),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        try:
            atualizado = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            idade = (datetime.now() - atualizado).total_seconds() / 3600
            if idade > max_age_hours:
                return None
            return json.loads(row[0])
        except Exception:
            return None
