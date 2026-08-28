# Monitor de FIIs

Dashboard Streamlit + CLI para acompanhar carteira de FIIs brasileiros, com
cotações (Yahoo Finance), dados do Investidor10, critérios do gestor e
persistência em SQLite (local) ou PostgreSQL/Neon (produção).

## Stack

- `app.py` — dashboard web (Streamlit)
- `main.py` — menu completo (dashboard, CLI, PDF, Excel, Telegram, agendador)
- `fii_monitor.py` — monitor em terminal
- `db.py` — banco unificado (SQLite / Neon)
- `market_data.py` — cotações + DY timezone-safe + cache
- `investidor10.py` — scraper único
- `criterios.py` — regras de avaliação (Ricardo / RT Tintas)
- `portfolio.py` — análise da carteira para PDF/Excel/HTML

## Instalação

```bash
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e preencha `DATABASE_URL` se for usar Neon:

```bash
# Windows
set DATABASE_URL=postgresql://USER:PASS@HOST/neondb?sslmode=require
```

## Uso

```bash
# Dashboard
streamlit run app.py

# Menu completo
python main.py

# CLI
python fii_monitor.py

# Atualização diária
python fii_monitor.py --daily

# Migrar SQLite -> Neon (sem senha no código)
set DATABASE_URL=...
set SQLITE_PATH=fii_data.db
python migrate_db.py
```

## Deploy (Render)

- `Procfile` e `render.yaml` sobem o Streamlit
- Configure `DATABASE_URL` no painel do Render (nunca no Git)
- Troque a senha do Neon se ela já apareceu em commits antigos

## Critérios do gestor (aba Critérios)

FIIs: DY mensal 0,60–1,50%, vacância ≤ 10%, P/VP 0,70–1,10, liquidez,
+10 anos, diversificar galpão/shopping/empresarial/papel.

Ações: sem prejuízo 5 anos, liquidez, P/VP ≥ 0,60, +10 anos, dívida < PL,
crescimento 10 anos.
