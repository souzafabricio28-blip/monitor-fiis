# 🏠 Monitor de FIIs - Fundos Imobiliários Brasileiros

Script completo para monitorar sua carteira de FIIs com cotações em tempo real, cálculos de rendimento, relatórios e alertas.

## 📋 Funcionalidades

- ✅ **Cotações em tempo real** via Yahoo Finance
- ✅ **Dados detalhados** via Investidor10 (Web Scraping)
- ✅ **Cálculo de Dividend Yield** (DY) mensal e anual
- ✅ **Relatórios HTML** com resumo da carteira
- ✅ **Alertas por email** para variações significativas
- ✅ **Dashboard gráfico** com Plotly
- ✅ **Armazenamento local** em SQLite
- ✅ **Execução automática** diária

## 🚀 Instalação

### 1. Pré-requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes)

### 2. Instalar dependências

Abra o terminal na pasta do projeto e execute:

```bash
pip install -r requirements.txt
```

### 3. Configurar

Edite o arquivo `config.json` com suas preferências:

```json
{
  "fiis": [
    {
      "ticker": "MXRF11",
      "quantidade": 100,
      "preco_compra": 10.50
    }
  ],
  "alertas": {
    "dy_minimo": 8.0,
    "dy_maximo": 20.0,
    "variacao_preco": 5.0
  }
}
```

## 💻 Uso

### Iniciar o programa

```bash
python fii_monitor.py
```

### Menu Principal

```
==================================================
🏠 MONITOR DE FIIS - Fundos Imobiliários
==================================================
1. 📊 Ver cotação de um FII
2. ➕ Adicionar FII à carteira
3. ➖ Remover FII da carteira
4. 📈 Ver carteira completa
5. 📉 Ver histórico de cotações
6. 💰 Ver dividendos
7. 📄 Gerar relatório HTML
8. 🔔 Verificar alertas
9. 🎨 Gerar gráficos
10. ⚙️ Configurações
11. 🔄 Atualizar todos os FIIs
12. 🔍 Investidor10 - Dados detalhados
0. 🚪 Sair
==================================================
```

### Exemplos de uso

#### Buscar dados detalhados no Investidor10

1. Digite `12` e pressione Enter
2. Escolha o FII desejado (1-5) ou digite `6` para personalizado
3. Veja dados como: Preço, DY, P/VP, Patrimônio, Vacância, Setor

#### Verificar cotação do MXRF11

1. Digite `1` e pressione Enter
2. Digite `MXRF11` e pressione Enter

#### Adicionar MXRF11 à carteira (R$ 240 investidos)

1. Digite `2` e pressione Enter
2. Ticker: `MXRF11`
3. Quantidade: `23` (aproximadamente 23 cotas a R$ 10,50)
4. Preço de compra: `10.50`

#### Gerar relatório

1. Digite `7` e pressione Enter
2. O relatório será aberto automaticamente no navegador

## ⚙️ Configuração

### Parâmetros de Alerta

| Parâmetro | Descrição | Padrão |
|-----------|-----------|--------|
| `dy_minimo` | DY mínimo antes de alertar | 8.0% |
| `dy_maximo` | DY máximo (possível armadilha) | 20.0% |
| `variacao_preco` | Variação % para alertar | 5.0% |

### Configuração de Email

Para receber alertas por email:

1. Ative as notificações em `config.json`
2. Configure um Gmail com **Senha de App**:
   - Acesse: https://myaccount.google.com/apppasswords
   - Gere uma senha específica para o app
3. Preencha os dados no arquivo de configuração

```json
{
  "email": {
    "ativar": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "email_remetente": "seu_email@gmail.com",
    "email_destinatario": "seu_email@gmail.com",
    "senha_app": "sua_senha_de_app"
  }
}
```

## 📅 Execução Automática

### Windows (Agendador de Tarefas)

1. Abra o **Agendador de Tarefas**
2. Crie uma nova tarefa
3. Configurações:
   - **Nome**: Monitor FII Diário
   - **Triiger**: Diariamente às 18:00
   - **Ação**: Iniciar programa
   - **Programa**: `python`
   - **Argumentos**: `C:\camin\para\fii_monitor.py --daily`
   - **Iniciar em**: `C:\camin\para\fii_monitor`

### Linux/Mac (crontab)

```bash
# Editar crontab
crontab -e

# Adicionar linha (executa todo dia às 18:00)
0 18 * * * /usr/bin/python3 /camin/para/fii_monitor.py --daily
```

## 📁 Estrutura de Arquivos

```
fii_monitor/
├── fii_monitor.py           # Script principal
├── investidor10_scraper.py  # Scraper standalone
├── investidor10_integration.py  # Integração ao monitor
├── test_investidor10.py     # Teste da integração
├── config.json              # Configurações
├── requirements.txt         # Dependências
├── fii_data.db              # Banco de dados (criado automaticamente)
├── fii_monitor.log          # Log de execução
└── relatorios/              # Pasta de relatórios
    └── relatorio_fii_YYYYMMDD_HHMMSS.html
```

## 🎯 Dicas para Iniciantes

### Sobre MXRF11

O MXRF11 é um FII de renda fixa (crédito imobiliário) com:
- **Ticker**: MXRF11
- **Tipo**: Recebíveis Imobiliários
- **DY típico**: 10% ao ano
- **Pagamento**: Mensal

### Dicas de investimento

1. **Diversifique** - Não coloque tudo em um único FII
2. **DY não é tudo** - Verifique também a qualidade do fundo
3. **Liquidez** - Prefira FIIs com bom volume de negociação
4. **Histórico** - Analise o histórico de pagamentos
5. **Vacância** - Para FIIs de tijolo, verifique a vacância

### Cálculos importantes

- **DY Anual** = (Dividendos 12 meses / Preço Atual) × 100
- **DY Mensal** = DY Anual / 12
- **Rentabilidade** = ((Valor Atual - Valor Investido) / Valor Investido) × 100

## 🔍 Integração Investidor10

O sistema agora inclui **Web Scraping** do Investidor10 para obter dados detalhados de FIIs.

### Dados obtidos do Investidor10:

| Dado | Descrição |
|------|-----------|
| **Preço atual** | Cotação em tempo real |
| **Dividend Yield** | DY mensal e anual |
| **P/VP** | Preço sobre valor patrimonial |
| **Patrimônio líquido** | PL do fundo |
| **Vacância** | % de imóveis vago |
| **Liquidez** | Volume diário de negociação |
| **Setor** | Logística, Shopping, Papel, etc. |

### Como usar:

1. Execute: `python fii_monitor.py`
2. Escolha opção `12`
3. Selecione o FII desejado
4. Veja os dados detalhados

### Teste rápido:

```bash
python test_investidor10.py
```

### Scraper standalone:

```bash
python investidor10_scraper.py
```

## 🔧 Solução de Problemas

### "Biblioteca não encontrada"

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### "Erro ao buscar cotação"

1. Verifique sua conexão com a internet
2. O ticker está correto? (ex: MXRF11, não MXRF11.SA)
3. Tente novamente em alguns minutos

### "Não foi possível enviar email"

1. Verifique se a senha de app está correta
2. Certifique-se de que o Gmail permite apps menos seguros
3. Teste manualmente primeiro

## 📊 Exemplo de Relatório

O relatório HTML gerado inclui:

- Resumo da carteira (total investido, valor atual, dividendos)
- Tabela detalhada por FII
- Lucro/prejuízo por FII
- Dividend Yield de cada FII
- Data e hora de geração

## 📝 Licença

Este script é para uso pessoal. Sinta-se livre para modificar e melhorar.

## 🤝 Contribuições

Melhorias sugeridas:
- [ ] Adicionar mais tipos de gráficos
- [ ] Importar dados de corretoras
- [ ] Calcular IR sobre dividendos
- [ ] Adicionar indicadores fundamentalistas
- [ ] Criar interface web (Streamlit)

---

**Desenvolvido para monitoramento de FIIs brasileiros** 🇧🇷
