# Monitor de FIIs

Dashboard Streamlit para acompanhar uma carteira de FIIs brasileiros: cotações
(Yahoo Finance), dados do Investidor10, critérios do gestor, rebalanceamento e
persistência em SQLite (local) ou PostgreSQL/Neon (produção).

## Rodar localmente

```bash
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py --server.port=45217
```

Tema escuro no estilo Status Invest em `.streamlit/config.toml`: fundo `#1A1A1A`,
destaque laranja `#F39200`, texto `#F5F5F5` e menu lateral carvão (nunca branco
no branco). O dashboard carrega cotações em lote no Yahoo e reutiliza cache; scrape do
Investidor10 (vacância, liquidez, cotistas, VP/cota, taxa de adm., variação 12M)
roda em **Atualizar critérios** ou na página **Indicadores**.

Fundos e ações ficam em abas no **Resumo**: mix, treemap de
alocação, ranking vs compra, peso de cada posição e diversificação por setor.

Se definir `AUTH_PASSWORD`, o login aparece antes da carteira. Sem essa variável
e sem Neon, o dashboard abre em modo local.

No dashboard dá para baixar CSV, Excel e PDF da carteira. A rentabilidade total
soma variação de preço e proventos registados (cotação ausente permanece N/D).
A aba Carteira mostra o histórico de transações. A watchlist dispara WhatsApp
no +55 11 97367-4455 quando o preço atinge o alvo (`WHATSAPP_APIKEY`). A
preferência Mostrar/Ocultar valores fica gravada no banco. A aba **Quedas 10%**
gera PDF com manchetes quando um ativo cai 10% ou mais; sem notícia o motivo
é N/D.

A diversificação usa o catálogo (mostra o que falta: shopping, empresarial,
galpão) sem esperar o scrape. Os critérios partem do Yahoo Finance e da tabela
de anos de listagem; Investidor10 só entra se você pedir **Atualizar critérios**.

## Vigia (monitoramento)

Não dá para “instalar o ChatGPT” no Render sem uma chave e um processo acordado. O app tem o **Vigia**:

1. No dashboard: menu **Vigia** → **Rodar vigia agora** (saúde do site + carteira).
2. Na máquina ou no cron: `python vigia.py` (e `python scheduler.py` às 18:45).
3. Com `WHATSAPP_APIKEY`, o relatório vai no WhatsApp (+55 11 97367-4455).
4. Com `OPENROUTER_API_KEY`, `GROQ_API_KEY` ou `OPENAI_API_KEY`, um modelo resume o relatório. Sem chave, só regras (site fora, queda 10%, watchlist, proventos zerados). Chave `sk-or-…` vai para o OpenRouter, não para a API da OpenAI.

Ative o CallMeBot **uma vez**: no WhatsApp, adicione o contato **+34 623 76 13 63**, envie `I allow callmebot to send me messages`, copie a apikey e coloque em `WHATSAPP_APIKEY` no `.env` e no Render. Sem essa chave o servidor não consegue mandar mensagem. Se já ativou e perdeu a chave, mande `Recover APIKey` para o mesmo contato.

Outro caminho: no Cursor, crie uma **Automação agendada** pedindo para checar o site, o health e te avisar. Isso usa o agente da conversa, não um modelo dentro do Render.

## Testes

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Produção (Render)

Serviço em uso: `https://monitor-fiis-6dk7.onrender.com`

Quando pedir para **subir** as alterações, o fluxo é commit de tudo o que está versionado, push no GitHub `master` e deploy no Render (o site no ar). Segredos (`.env`) nunca sobem.

```bash
python subir_producao.py
```

Isso copia o código já commitado para `souzafabricio28-blip/monitor-fiis` (`master`) e dispara o Render.

No `.env` local (nunca no Git):

| Variável | Uso |
|----------|-----|
| `GH_TOKEN` | PAT com Contents write no `monitor-fiis` |
| `RENDER_DEPLOY_HOOK` | URL do Deploy Hook do serviço (Render → Settings) |

No GitHub: **Settings → Secrets → Actions → `RENDER_DEPLOY_HOOK`**. O PAT precisa do escopo **workflow** para o Actions publicar `deploy-render.yml`; sem isso o `subir_producao.py` sobe o app e dispara o hook, mas não altera workflows.

Configure no painel do Render (nunca no Git):

| Variável | Uso |
|----------|-----|
| `DATABASE_URL` | Neon (`sslmode=require`) |
| `AUTH_USER` | usuário personalizado (não `admin`) |
| `AUTH_PASSWORD` | senha com 12+ caracteres |
| `WHATSAPP_PHONE` | `5511973674455` (padrão) |
| `WHATSAPP_APIKEY` | apikey do CallMeBot (obrigatória para enviar) |
| `OPENROUTER_API_KEY` | opcional — resumo do Vigia via OpenRouter |

O tema Status Invest (carvão + laranja) também pode ser reforçado com
`STREAMLIT_THEME_*` (já listadas em `render.yaml`).

Antes do próximo deploy público, rotacione a senha do Neon e o token da API do
Render se já tiverem sido expostos.

## Critérios do gestor

FIIs: DY mensal 0,60–1,50%, vacância ≤ 10%, P/VP 0,70–1,10, liquidez, +10 anos
e diversificação entre galpão, shopping, empresarial e papel.

Ações: P/VP vem do Fundamentus (VPA da B3). O Yahoo distorce P/B de PN
(SAPR4, KLBN4). Dado ausente permanece N/D, nunca 0.

FIIs com ticker “jovem” por troca de nome ou incorporação (XPLG11, HSML11,
RZTR11, BTLG11) herdam a idade de bolsa da origem — não reprovam só pelo IPO
do código atual.

KNRI11 fica no setor **Empresarial** (catálogo curado), não como híbrido.

Para um PDF resumido da lista do Ricardo (28/08/2026), sem tela no app:

```bash
python gerar_pdf_lista_gestor.py
```
