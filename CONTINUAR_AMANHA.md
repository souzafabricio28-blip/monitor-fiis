# Continuar amanhã — 29/08/2026 (noite)

Conversa salva para retomar no dia seguinte. **Não cole chaves neste arquivo.** Segredos ficam no `.env` (gitignored) e no Render.

## Onde paramos

O Fabricio pediu para **tirar o Telegram** (`TELEGRAM_TOKEN`) e mandar alertas no **WhatsApp 11 97367-4455**.

Isso **já funciona**:

- Destino fixo: **+55 11 97367-4455** (`WHATSAPP_PHONE=5511973674455`).
- Envio via **CallMeBot** (`whatsapp_notifier.py`). `telegram_notifier.py` foi apagado.
- O bot ativou a API nesse número. Teste enviado daqui chegou no WhatsApp: *Monitor de FIIs: WhatsApp ligado…*
- Em **Configurações** a faixa verde apareceu: **Apikey detectada. Alertas saem para esse número.** Ativar WhatsApp está marcado.
- Dá para colar a apikey no campo **Apikey do CallMeBot** (o site no Render às vezes não tem a variável de ambiente).

Também nesta sequência:

- Chave **OpenRouter** ligada no Vigia (`OPENROUTER_API_KEY` no `.env`). Prefixo `sk-or-` vai para `https://openrouter.ai/api/v1`, não para a OpenAI.
- Visual Status Invest (carvão + laranja). Indicadores Investidor10. Fundos e ações separados.

## O que o app avisa no WhatsApp

Watchlist no alvo, queda ≥ 10% e o **Vigia** (saúde do site + carteira). Número: +55 11 97367-4455.

Não enviar `Stop` ao CallMeBot (isso pausa o bot). Contato oficial do bot: **+34 623 76 13 63**. Se perder a chave: `Recover APIKey`.

## Git / site

- Branch de trabalho: `cursor/continuar-monitor-fiis-1fa4`
- GitHub produção: `souzafabricio28-blip/monitor-fiis` branch **`master`** (último push desta sessão: campo da apikey em Configurações).
- Site: `https://monitor-fiis-6dk7.onrender.com`
- Preview local: Streamlit na porta **45217**
- **Render não dispara sozinho** (não há `RENDER_DEPLOY_HOOK` nem `RENDER_API_KEY` no `.env`). Se o site no ar estiver atrasado: **Manual Deploy** no painel.
- `python subir_producao.py` copia o código commitado para o GitHub `master` e tenta o hook (hoje só o GitHub atualiza).

## Segredos (não versionar)

No `.env` local já existem (não repetir no chat nem no Git):

- `WHATSAPP_APIKEY` + `WHATSAPP_PHONE`
- `OPENROUTER_API_KEY`
- `GH_TOKEN` (PAT `repo`, **sem** escopo `workflow` — por isso o `subir_producao.py` **não** altera `.github/workflows/`)

No Render, conferir amanhã se existem:

- `WHATSAPP_APIKEY` (e opcional `WHATSAPP_PHONE=5511973674455`)
- `OPENROUTER_API_KEY` (resumo do Vigia no ar)
- `AUTH_USER` / `AUTH_PASSWORD` / `DATABASE_URL`

Chaves já apareceram neste chat: convém **rotacionar** OpenRouter e o PAT do GitHub se a conversa puder ser vista por outros.

## Como retomar

1. Abrir o Monitor (local `:45217` ou o site no ar).
2. **Configurações**: confirmar faixa verde do WhatsApp. Se amarela no Render, colar a apikey e **Salvar WhatsApp**, ou colocar `WHATSAPP_APIKEY` no Environment e Manual Deploy.
3. **Vigia** → Rodar vigia agora (com enviar WhatsApp) para um teste de ponta a ponta no ar.
4. Se o visual/código no Render estiver velho: Manual Deploy.

## Pedidos já entregues (contexto)

- Critérios do gestor (Ricardo / RT Tintas): DY mensal 0,60–1,50%, vacância ≤10%, P/VP 0,70–1,10 (FII) / ≥0,60 (ação), liquidez, ≥10 anos **exceto** incorporação/troca de nome (XPLG11, HSML11, RZTR11), diversificação ≥3 de {Papel, Galpão, Shopping, Empresarial}. Ausente = **N/D**, nunca 0.
- TAEE11 é ação (unit). Lista WhatsApp do Ricardo: análise no PDF, não no app.
- P/VP de PN (SAPR4, KLBN4) via Fundamentus.
- Sem `unsafe_allow_html` no login.

## Arquivos desta troca Telegram → WhatsApp

`whatsapp_notifier.py`, `app.py` (Configurações + Vigia), `vigia.py`, `scheduler.py`, `queda_report.py`, `db.py` (apikey WhatsApp pode ficar no banco; token Telegram legado some), `main.py`, `.env.example`, `render.yaml`.

## Amanhã (se o Fabricio não pedir outra coisa)

- Conferir se o **Render** já está no código novo e com WhatsApp verde.
- Colocar `OPENROUTER_API_KEY` no Render se o Vigia no ar ainda for só regras.
- Não recriar Telegram.
- Não commitar `.env`.
