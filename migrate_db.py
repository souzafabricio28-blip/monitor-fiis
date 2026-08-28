import sqlite3
import psycopg2

PG_URL = "postgresql://neondb_owner:npg_8hKVLoZECT5n@ep-lucky-rice-axsczsuk-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"
SL_PATH = r"C:\Users\souza\Desktop\INVESTIMENTOS\fii_data.db"

sl = sqlite3.connect(SL_PATH)
pg = psycopg2.connect(PG_URL)

sl_cur = sl.cursor()
pg_cur = pg.cursor()

pg_cur.execute('''CREATE TABLE IF NOT EXISTS carteira (
    ticker TEXT PRIMARY KEY,
    quantidade INTEGER NOT NULL,
    preco_compra REAL NOT NULL,
    data_compra TEXT NOT NULL
)''')
pg_cur.execute('''CREATE TABLE IF NOT EXISTS cotacoes (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    data TEXT NOT NULL,
    preco REAL NOT NULL,
    UNIQUE(ticker, data)
)''')
pg_cur.execute('''CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    preco_alvo REAL,
    data_adicionado TEXT NOT NULL,
    notas TEXT,
    UNIQUE(ticker)
)''')

sl_cur.execute("SELECT ticker, quantidade, preco_compra, data_compra FROM carteira")
rows = sl_cur.fetchall()
print(f"Migrando {len(rows)} fiis da carteira...")
for row in rows:
    pg_cur.execute(
        "INSERT INTO carteira (ticker, quantidade, preco_compra, data_compra) VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
        row
    )
    print(f"  {row}")

sl_cur.execute("SELECT ticker, data, preco FROM cotacoes")
rows = sl_cur.fetchall()
print(f"Migrando {len(rows)} cotacoes...")
for row in rows:
    pg_cur.execute(
        "INSERT INTO cotacoes (ticker, data, preco) VALUES (%s, %s, %s) ON CONFLICT (ticker, data) DO NOTHING",
        row
    )

sl_cur.execute("SELECT ticker, preco_alvo, data_adicionado, notas FROM watchlist")
rows = sl_cur.fetchall()
print(f"Migrando {len(rows)} watchlist...")
for row in rows:
    pg_cur.execute(
        "INSERT INTO watchlist (ticker, preco_alvo, data_adicionado, notas) VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
        row
    )

pg.commit()

pg_cur.execute("SELECT COUNT(*) FROM carteira")
print(f"\nVerificando: {pg_cur.fetchone()[0]} fiis no PostgreSQL")
pg_cur.execute("SELECT * FROM carteira")
for r in pg_cur.fetchall():
    print(f"  {r}")

sl.close()
pg.close()
print("\nMigracao concluida!")
