"""
Persistência unificada: SQLite (local) ou PostgreSQL (Neon/Render).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(
    DATABASE_URL and DATABASE_URL.startswith(("postgresql://", "postgres://"))
)


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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS movimentacoes (
                    id BIGSERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    preco_unitario REAL NOT NULL,
                    taxas REAL NOT NULL DEFAULT 0,
                    data_movimentacao TEXT NOT NULL,
                    observacoes TEXT,
                    idempotency_key TEXT UNIQUE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    versao INTEGER PRIMARY KEY,
                    aplicado_em TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_log (
                    id BIGSERIAL PRIMARY KEY,
                    iniciado_em TEXT NOT NULL,
                    concluido_em TEXT,
                    status TEXT NOT NULL,
                    contagens TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS plano_movimentacoes (
                    id BIGSERIAL PRIMARY KEY,
                    fase INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    preco_referencia REAL,
                    valor_estimado REAL,
                    par_ticker TEXT,
                    motivo TEXT,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    criado_em TEXT NOT NULL,
                    executado_em TEXT,
                    idempotency_key TEXT UNIQUE
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS movimentacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    preco_unitario REAL NOT NULL,
                    taxas REAL NOT NULL DEFAULT 0,
                    data_movimentacao TEXT NOT NULL,
                    observacoes TEXT,
                    idempotency_key TEXT UNIQUE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    versao INTEGER PRIMARY KEY,
                    aplicado_em TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    iniciado_em TEXT NOT NULL,
                    concluido_em TEXT,
                    status TEXT NOT NULL,
                    contagens TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS plano_movimentacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fase INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    preco_referencia REAL,
                    valor_estimado REAL,
                    par_ticker TEXT,
                    motivo TEXT,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    criado_em TEXT NOT NULL,
                    executado_em TEXT,
                    idempotency_key TEXT UNIQUE
                )
                """
            )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_cotacoes_ticker_data "
            "ON cotacoes(ticker, data)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_dividendos_ticker_data "
            "ON dividendos(ticker, data_pagamento)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_movimentacoes_ticker_data "
            "ON movimentacoes(ticker, data_movimentacao)"
        )
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.use_pg:
            cur.execute(
                "INSERT INTO schema_version (versao, aplicado_em) VALUES (%s, %s) "
                "ON CONFLICT (versao) DO NOTHING",
                (2, agora),
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO schema_version (versao, aplicado_em) VALUES (?, ?)",
                (2, agora),
            )
        conn.commit()
        conn.close()
        self._sanitizar_configuracoes()
        self._importar_saldos_iniciais()

        if self.use_pg and os.environ.get("AUTO_MIGRATE_SQLITE") == "1":
            self._migrate_sqlite_if_needed()

    def _sanitizar_configuracoes(self):
        """Remove segredos (token Telegram legado, apikey WhatsApp) do banco."""
        conn = self._get_conn()
        cur = conn.cursor()
        for chave, padrao_ativar in (("telegram", False), ("whatsapp", True)):
            cur.execute(
                f"SELECT valor FROM configuracoes WHERE chave = {_ph()}",
                (chave,),
            )
            row = cur.fetchone()
            if not row:
                continue
            try:
                atual = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                atual = {}
            if not isinstance(atual, dict):
                atual = {}
            seguro = json.dumps(
                {"ativar": bool(atual.get("ativar", padrao_ativar))},
                ensure_ascii=False,
            )
            if self.use_pg:
                cur.execute(
                    "UPDATE configuracoes SET valor = %s WHERE chave = %s",
                    (seguro, chave),
                )
            else:
                cur.execute(
                    "UPDATE configuracoes SET valor = ? WHERE chave = ?",
                    (seguro, chave),
                )
        conn.commit()
        conn.close()

    def _importar_saldos_iniciais(self):
        """Registra cada posição legada uma vez, sem alterar seu resumo."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT ticker, quantidade, preco_compra, data_compra FROM carteira")
        for ticker, quantidade, preco, data_compra in cur.fetchall():
            chave = f"saldo-inicial:{ticker}"
            params = (
                ticker,
                "SALDO_INICIAL",
                int(quantidade),
                float(preco),
                0.0,
                data_compra,
                "Importado automaticamente da posição existente",
                chave,
            )
            if self.use_pg:
                cur.execute(
                    "INSERT INTO movimentacoes "
                    "(ticker, tipo, quantidade, preco_unitario, taxas, data_movimentacao, "
                    "observacoes, idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (idempotency_key) DO NOTHING",
                    params,
                )
            else:
                cur.execute(
                    "INSERT OR IGNORE INTO movimentacoes "
                    "(ticker, tipo, quantidade, preco_unitario, taxas, data_movimentacao, "
                    "observacoes, idempotency_key) VALUES (?,?,?,?,?,?,?,?)",
                    params,
                )
        conn.commit()
        conn.close()

    def _migrate_sqlite_if_needed(self):
        """Migração explícita e idempotente; habilitada por AUTO_MIGRATE_SQLITE=1."""
        if not os.path.exists(self.db_path):
            return {}
        from migrate_db import migrar_sqlite_para_postgres

        return migrar_sqlite_para_postgres(self.db_path, DATABASE_URL)

    def obter_carteira(self) -> pd.DataFrame:
        conn = self._get_conn()
        try:
            return pd.read_sql_query("SELECT * FROM carteira ORDER BY ticker", conn)
        finally:
            conn.close()

    def adicionar_fii(self, ticker: str, quantidade: int, preco: float):
        """Registra compra e atualiza o resumo compatível da carteira."""
        return self.registrar_movimentacao(ticker, "COMPRA", quantidade, preco)

    def registrar_movimentacao(
        self,
        ticker: str,
        tipo: str,
        quantidade: int,
        preco_unitario: float,
        taxas: float = 0.0,
        data_movimentacao: Optional[str] = None,
        observacoes: str = "",
        idempotency_key: Optional[str] = None,
    ) -> str:
        ticker = ticker.upper().replace(".SA", "").strip()
        tipo = tipo.upper().strip()
        quantidade = int(quantidade)
        preco_unitario = float(preco_unitario)
        taxas = float(taxas)
        if tipo not in {"COMPRA", "VENDA", "SALDO_INICIAL"}:
            raise ValueError("Tipo deve ser COMPRA, VENDA ou SALDO_INICIAL")
        if quantidade <= 0 or preco_unitario < 0 or taxas < 0:
            raise ValueError("Quantidade deve ser positiva; preço e taxas não podem ser negativos")

        conn = self._get_conn()
        cur = conn.cursor()
        if tipo == "VENDA":
            cur.execute(
                f"SELECT quantidade FROM carteira WHERE ticker = {_ph()}",
                (ticker,),
            )
            atual = cur.fetchone()
            if not atual or quantidade > int(atual[0]):
                conn.close()
                raise ValueError("Venda maior que a posição disponível")

        chave = idempotency_key or str(uuid.uuid4())
        data = data_movimentacao or datetime.now().strftime("%Y-%m-%d")
        params = (
            ticker,
            tipo,
            quantidade,
            preco_unitario,
            taxas,
            data,
            observacoes,
            chave,
        )
        if self.use_pg:
            cur.execute(
                "INSERT INTO movimentacoes "
                "(ticker,tipo,quantidade,preco_unitario,taxas,data_movimentacao,"
                "observacoes,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (idempotency_key) DO NOTHING",
                params,
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO movimentacoes "
                "(ticker,tipo,quantidade,preco_unitario,taxas,data_movimentacao,"
                "observacoes,idempotency_key) VALUES (?,?,?,?,?,?,?,?)",
                params,
            )
        conn.commit()
        conn.close()
        self._recalcular_posicao(ticker)
        return chave

    def _recalcular_posicao(self, ticker: str):
        movimentos = self.obter_movimentacoes(ticker)
        quantidade = 0
        custo = 0.0
        ultima_data = datetime.now().strftime("%Y-%m-%d")
        for _, mov in movimentos.iterrows():
            qtd = int(mov["quantidade"])
            tipo = mov["tipo"]
            ultima_data = str(mov["data_movimentacao"])[:10]
            if tipo in {"COMPRA", "SALDO_INICIAL"}:
                quantidade += qtd
                custo += qtd * float(mov["preco_unitario"]) + float(mov["taxas"])
            elif tipo == "VENDA" and quantidade:
                custo -= min(qtd, quantidade) * (custo / quantidade)
                quantidade -= qtd

        conn = self._get_conn()
        cur = conn.cursor()
        if quantidade <= 0:
            cur.execute(f"DELETE FROM carteira WHERE ticker = {_ph()}", (ticker,))
        else:
            preco_medio = custo / quantidade
            if self.use_pg:
                cur.execute(
                    "INSERT INTO carteira (ticker,quantidade,preco_compra,data_compra) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (ticker) DO UPDATE SET "
                    "quantidade=EXCLUDED.quantidade, preco_compra=EXCLUDED.preco_compra, "
                    "data_compra=EXCLUDED.data_compra",
                    (ticker, quantidade, round(preco_medio, 4), ultima_data),
                )
            else:
                cur.execute(
                    "INSERT OR REPLACE INTO carteira "
                    "(ticker,quantidade,preco_compra,data_compra) VALUES (?,?,?,?)",
                    (ticker, quantidade, round(preco_medio, 4), ultima_data),
                )
        conn.commit()
        conn.close()

    def obter_movimentacoes(self, ticker: Optional[str] = None) -> pd.DataFrame:
        conn = self._get_conn()
        try:
            if ticker:
                return pd.read_sql_query(
                    f"SELECT * FROM movimentacoes WHERE ticker = {_ph()} "
                    "ORDER BY data_movimentacao, id",
                    conn,
                    params=(ticker.upper(),),
                )
            return pd.read_sql_query(
                "SELECT * FROM movimentacoes ORDER BY data_movimentacao DESC, id DESC",
                conn,
            )
        finally:
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
        """Encerra a posição ao preço médio, preservando o histórico."""
        ticker = ticker.upper().replace(".SA", "").strip()
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT quantidade, preco_compra FROM carteira WHERE ticker = {_ph()}",
            (ticker,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            self.registrar_movimentacao(
                ticker,
                "VENDA",
                int(row[0]),
                float(row[1]),
                observacoes="Encerramento de posição pelo comando remover",
            )

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
        limite = (datetime.now() - timedelta(days=max(int(dias), 0))).strftime("%Y-%m-%d")
        try:
            return pd.read_sql_query(
                f"SELECT data, preco FROM cotacoes WHERE ticker = {ph} "
                f"AND data >= {ph} ORDER BY data",
                conn,
                params=(ticker.upper(), limite),
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
        limite = (datetime.now() - timedelta(days=max(int(meses), 0) * 31)).strftime(
            "%Y-%m-%d"
        )
        try:
            if ticker:
                return pd.read_sql_query(
                    f"SELECT * FROM dividendos WHERE ticker = {_ph()} "
                    f"AND data_pagamento >= {_ph()} ORDER BY data_pagamento DESC",
                    conn,
                    params=(ticker.upper(), limite),
                )
            return pd.read_sql_query(
                f"SELECT * FROM dividendos WHERE data_pagamento >= {_ph()} "
                "ORDER BY data_pagamento DESC",
                conn,
                params=(limite,),
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

    def salvar_plano_rebalanceamento(self, itens: list) -> int:
        """Substitui o plano pendente por um novo roteiro de rebalanceamento."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM plano_movimentacoes WHERE status = 'pendente'")
        inseridos = 0
        for item in itens:
            params = (
                int(item["fase"]),
                int(item["ordem"]),
                item["tipo"],
                item["ticker"].upper(),
                int(item["quantidade"]),
                item.get("preco_referencia"),
                item.get("valor_estimado"),
                (item.get("par_ticker") or "").upper() or None,
                item.get("motivo", ""),
                item.get("status", "pendente"),
                item.get("criado_em") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                item["idempotency_key"],
            )
            if self.use_pg:
                cur.execute(
                    "INSERT INTO plano_movimentacoes "
                    "(fase, ordem, tipo, ticker, quantidade, preco_referencia, "
                    "valor_estimado, par_ticker, motivo, status, criado_em, idempotency_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (idempotency_key) DO UPDATE SET "
                    "quantidade=EXCLUDED.quantidade, preco_referencia=EXCLUDED.preco_referencia, "
                    "valor_estimado=EXCLUDED.valor_estimado, motivo=EXCLUDED.motivo, "
                    "status='pendente', executado_em=NULL",
                    params,
                )
            else:
                cur.execute(
                    "INSERT OR REPLACE INTO plano_movimentacoes "
                    "(fase, ordem, tipo, ticker, quantidade, preco_referencia, "
                    "valor_estimado, par_ticker, motivo, status, criado_em, idempotency_key) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    params,
                )
            inseridos += 1
        conn.commit()
        conn.close()
        return inseridos

    def obter_plano_rebalanceamento(
        self, status: Optional[str] = None
    ) -> pd.DataFrame:
        conn = self._get_conn()
        try:
            if status:
                return pd.read_sql_query(
                    f"SELECT * FROM plano_movimentacoes WHERE status = {_ph()} "
                    "ORDER BY fase, ordem, CASE tipo WHEN 'VENDA' THEN 0 ELSE 1 END, id",
                    conn,
                    params=(status,),
                )
            return pd.read_sql_query(
                "SELECT * FROM plano_movimentacoes "
                "ORDER BY fase, ordem, CASE tipo WHEN 'VENDA' THEN 0 ELSE 1 END, id",
                conn,
            )
        finally:
            conn.close()

    def executar_item_plano(
        self,
        item_id: int,
        preco_real: float,
        taxas: float = 0.0,
        data_movimentacao: Optional[str] = None,
    ):
        """Registra a movimentação real na carteira e marca o item do plano como executado."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM plano_movimentacoes WHERE id = {_ph()}", (item_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise ValueError("Item do plano não encontrado")
        cols = [d[0] for d in cur.description]
        item = dict(zip(cols, row))
        if item.get("status") == "executado":
            conn.close()
            raise ValueError("Este item já foi executado")
        conn.close()

        obs = f"Plano rebalanceamento f{item['fase']} — {item.get('motivo', '')}"
        chave = f"exec-plano-{item_id}-{item['idempotency_key']}"
        self.registrar_movimentacao(
            item["ticker"],
            item["tipo"],
            int(item["quantidade"]),
            float(preco_real),
            float(taxas),
            data_movimentacao,
            observacoes=obs,
            idempotency_key=chave,
        )

        conn = self._get_conn()
        cur = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            f"UPDATE plano_movimentacoes SET status = 'executado', executado_em = {_ph()} "
            f"WHERE id = {_ph()}",
            (agora, item_id),
        )
        conn.commit()
        conn.close()
