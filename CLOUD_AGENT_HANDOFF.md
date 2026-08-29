# Handoff para Cloud Agent — Monitor de FIIs (INVESTIMENTOS)

Data: 2026-08-28  
Workspace: `C:\Users\souza\Desktop\INVESTIMENTOS`  
Transcript local: `16677dc6-254b-4664-ac2a-871980e2af93.jsonl`

## Objetivo do projeto

Tornar o Monitor de FIIs **seguro, confiável e auditável**, priorizando FIIs e fontes gratuitas (Yahoo + Investidor10) com validação cruzada. Trabalho validado **localmente**; GitHub/Render/Neon só após aprovação do usuário.

## O que já foi implementado

### 1. Segurança
- Removidos scripts com credenciais hardcoded (`check_render.py`, `fix_render.py`, etc.)
- XSRF/CORS reativados em `.streamlit/config.toml`
- Sessão expira em 8h (`auth.py`)
- Produção exige `AUTH_USER` personalizado + senha ≥12 chars
- Telegram só via ambiente (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`); token removido do banco
- Backup SQLite: `.backups/fii_data_20260828_041113.db`

### 2. Dados confiáveis
- Fonte única: `market_data.py` + `investidor10.py`
- Metadados por indicador: fonte, horário, status, confiança, divergências
- `N/D` distinto de `0`
- `criterios.py` consome `market_data` para FIIs
- Score em `scoring.py` não premia vacância ausente

### 3. Carteira auditável
- Tabela `movimentacoes` (COMPRA/VENDA/SALDO_INICIAL, taxas, idempotency)
- 12 posições importadas como saldo inicial sem alterar PM
- `portfolio.py`: ganho de capital, proventos registrados, projeção de renda separados

### 4. Banco / migração
- Queries compatíveis SQLite + Neon
- `migrate_db.py` idempotente com contagens (sem expor posições)
- Schema versionado, índices, `sync_log`
- Tabela `plano_movimentacoes` para rebalanceamento pendente

### 5. Dashboard / operação
- Dashboard usa `analisar_carteira()` única
- Filtros por setor e critério
- Health check Render: `/_stcore/health`
- Atalhos locais apontam para `INVESTIMENTOS`
- Nova aba **Rebalanceamento** no menu

### 6. Testes
- 15 testes passando (`pytest`)
- Dependências fixadas (`requirements.txt`, `requirements-dev.txt`)
- CI em `.github/workflows/ci.yml`

## Carteira atual (12 ativos)

| Ticker | Qtd | PM | Critério FII |
|--------|-----|-----|--------------|
| MXRF11 | 40 | 9.23 | **APROVADO** (único FII) |
| BTCI11 | 10 | 8.97 | Reprovado (liquidez) |
| CPTS11 | 10 | 7.43 | Reprovado (liquidez) |
| GARE11 | 10 | 8.31 | Reprovado (liquidez) |
| KNSC11 | 10 | 9.04 | Reprovado (liquidez + <10a) |
| MANA11 | 10 | 9.11 | Reprovado (liquidez + 4a) |
| RURA11 | 12 | 8.14 | Reprovado (liquidez) |
| SNEL11 | 10 | 8.15 | Reprovado (liquidez + 4a) |
| VGHF11 | 10 | 5.32 | Reprovado (liquidez + 5a) |
| VGIR11 | 10 | 9.42 | Reprovado (liquidez + 8a) |
| VRTM11 | 10 | 6.57 | Reprovado (liquidez crítica) |
| PETR4 | 4 | 41.45 | Ação (critérios diferentes) |

Total investido ~R$ 1.356. Diversificação FII: **não passou** (só Papel + Galpão + Híbrido).

## Plano de rebalanceamento registrado no app

**20 movimentações pendentes** na aba **Rebalanceamento** (`plano_movimentacoes`):

### Manter
- **MXRF11** — núcleo aprovado

### Fase 1
- VRTM11 → VISC11 (Shopping)
- MANA11 → KNRI11 (Empresarial)
- SNEL11 → BTLG11 (Galpão)
- VGHF11 → KNCR11 (Papel aprovado)
- KNSC11 → KNCR11
- VGIR11 → KNCR11

### Fase 2
- BTCI11 → KNCR11
- CPTS11 → MXRF11

### Fase 3
- GARE11 → BTLG11
- RURA11 → XPML11

### Decisão separada
- **PETR4** — manter fora do monitor FII ou realocar

Fluxo: executar na corretora → confirmar no app (Registrar VENDA/COMPRA executada).

## Pendências antes de deploy

1. Rotacionar manualmente senha Neon e token Render
2. Configurar no Render: `AUTH_USER`, `AUTH_PASSWORD`, `DATABASE_URL`, Telegram
3. Usuário aprovar commit/push/deploy (nada foi publicado ainda)

## Arquivos principais

- `app.py`, `db.py`, `market_data.py`, `investidor10.py`, `portfolio.py`, `criterios.py`
- `rebalanceamento.py`, `auth.py`, `migrate_db.py`, `scoring.py`
- `tests/`, `render.yaml`, `.env.example`

## Próximos passos sugeridos para Cloud Agent

1. Tema escuro persistido em `.streamlit/config.toml` e `render.yaml`
2. KNRI11 classificado como Empresarial pelo catálogo curado
3. Aviso `AUTH_PASSWORD` não mostra mais formulário falso nem PIN
4. Dashboard mais rápido (cotações em paralelo; critérios sob demanda)
5. Proventos 12m sincronizados do Yahoo; PETR4 marcado como AÇÃO
6. Plano de rebalanceamento pré-carregado no SQLite local
7. Continuar execução na corretora e confirmar na aba Rebalanceamento
8. Rotacionar senha Neon e token Render se ainda estiverem expostos

## Instrução para o Cloud Agent

Continue a partir deste estado. **Não faça deploy nem commit sem aprovação explícita do usuário.** Preserve carteira/watchlist existentes. Use a aba Rebalanceamento para movimentações pendentes.
