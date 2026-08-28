"""
Critérios do Gestor (RICARDO - RT Tintas)

Avalia FIIs e ações conforme os critérios de investimento definidos:

FIIs:
  - Pagamento de pelo menos 0,60% a 1,50% ao mês nos últimos 12 meses (DY mensal)
  - Vacância de no máximo 10%
  - P/VP entre 0,70 e 1,10
  - Liquidez acima da média
  - Mesclar galpão, shopping, empresarial e papéis (avaliado no nível da carteira)
  - Mais de 10 anos de bolsa (exceto se comprado por outro fundo)

Ações:
  - Não ter prejuízo nos últimos 5 anos direto
  - Ter liquidez
  - P/VP acima de 0,60
  - Mais de 10 anos de bolsa
  - Não pode ter dívida maior que patrimônio
  - Crescimento nos últimos 10 anos

Quando um dado não está disponível (ou é pouco confiável), o critério é marcado
como N/D (sem dados) em vez de "aprovado" ou "reprovado".
"""

import re
import statistics
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

REFERENCIA_FIIS = [
    "MXRF11", "KNRI11", "HGLG11", "XPML11", "KNCR11", "BTLG11",
]
REFERENCIA_ACOES = [
    "PETR4", "VALE3", "ITUB4", "WEGE3", "ABEV3", "BBAS3",
]

_liq_cache = {}
_fiis_cache = {}


class NdorInvalido:
    """Marcador para valores sem dados suficientemente confiáveis"""

    def __repr__(self):
        return "N/D"


ND = NdorInvalido()


def _valor_negociado_diario(ticker, hist=None):
    try:
        if hist is None:
            hist = yf.Ticker(f"{ticker}.SA").history(period="5d")
        if hist is None or hist.empty:
            return None
        volume_medio = float(hist["Volume"].tail(5).mean())
        preco = float(hist["Close"].iloc[-1])
        if preco <= 0:
            return None
        return volume_medio * preco
    except Exception:
        return None


def _volume_referencia(tipo):
    key = f"liq_{tipo}"
    if key in _liq_cache:
        return _liq_cache[key]

    lista = REFERENCIA_FIIS if tipo == "fii" else REFERENCIA_ACOES
    valores = []
    for ticker in lista:
        try:
            valor = _valor_negociado_diario(ticker)
            if valor:
                valores.append(valor)
        except Exception:
            continue

    resultado = statistics.median(valores) if valores else 0
    _liq_cache[key] = resultado
    return resultado


def checar_liquidez(ticker, tipo, valor_negociado=None):
    """Liquidez acima da média do mercado. Retorna (ok, valor, media)."""
    if valor_negociado is None:
        valor_negociado = _valor_negociado_diario(ticker)
    media = _volume_referencia(tipo)
    if not valor_negociado or not media:
        return None, valor_negociado, media
    return valor_negociado > media, valor_negociado, media


def _dy_mensal(ticker, preco):
    """DY médio mensal dos últimos 12 meses em % (0,60-1,50 = faixa saudável)."""
    try:
        acao = yf.Ticker(f"{ticker}.SA")
        divs = acao.dividends
        if divs is None or len(divs) == 0:
            return None
        idx = divs.index
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        divs = pd.Series(divs.to_numpy(), index=idx)
        meta = pd.Timestamp((datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
        recentes = divs[divs.index >= meta]
        if recentes.empty:
            recentes = divs.tail(12)
        soma = float(recentes.sum())
        if preco and preco > 0 and soma > 0:
            return soma / preco / 12 * 100
    except Exception:
        pass
    return None


_ANOS_LISTAGEM = {
    # Anos de listagem curados (fontes públicas: CVM, relatórios do fundo,
    # fiis.com.br begindate). Usados antes do scraping por confiabilidade.
    "MXRF11": 2011,   # Maxi Renda - início da negociação 07/2011 (fiis.com.br)
    "VGIR11": 2018,   # Valora CRI CDI - início 27/07/2018 (fiis.com.br)
    "BTCI11": 2008,   # BTG CRI - criação em 2008
    "CPTS11": 2014,   # Capitânia Securities - início em 2014
    "KNSC11": 2020,   # FII KINEA SC - IPO em 2020
    "MANA11": 2022,   # FII MANATI - lançado em 05/2022
    "SNEL11": 2022,   # Suno Energias Limpas - registro CVM 12/2022
    "VGHF11": 2021,   # Valora Hedge Fund - IPO em 2021
    "PETR4": 1997,    # Petrobras - IPO da privatização em 1997
    # GARE11, VRTM11: ano não confirmado -> ficam para scraping/N-D
}


def _ano_listagem(ticker, tipo):
    """Ano de listagem (tabela curada, fiis.com.br ou scraping Investidor10)."""
    ticker = ticker.upper().replace(".SA", "").strip()
    if ticker in _ANOS_LISTAGEM:
        return _ANOS_LISTAGEM[ticker]

    ano_atual = datetime.now().year
    if tipo == "fii":
        dados_fiis = _buscar_fiis_com(ticker)
        if dados_fiis and dados_fiis.get("begindate"):
            ano = int(dados_fiis["begindate"][:4])
            if 1975 <= ano < ano_atual:
                return ano

    base = "fiis" if tipo == "fii" else "acoes"
    url = f"https://investidor10.com.br/{base}/{ticker.lower()}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        texto = resp.text
        padroes = [
            r"(?:fundad[oa]|desde|listad[oa]|listagem|ingressou|iniciou)[^0-9]{0,40}(?:19|20)\d{2}",
            r"(?:19[8-9]\d|20[0-2]\d)\s*[-–—]\s*(?:atual|presente|hoje)",
        ]
        for padrao in padroes:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                anos = [int(a) for a in re.findall(r"(?:19|20)\d{2}", m.group(0))]
                anos_validos = [a for a in anos if 1975 <= a < ano_atual]
                if anos_validos:
                    return anos_validos[0]
    except Exception:
        pass
    return None


def _lucro_5_anos(ticker):
    """Rentabilidade/lucro anual dos últimos ~5 anos."""
    try:
        acao = yf.Ticker(f"{ticker}.SA")
        fin = acao.financials
        if fin is None or fin.empty:
            return None
        indice = None
        for candidato in ("Net Income", "Net Income Common Stockholders"):
            if candidato in fin.index:
                indice = candidato
                break
        if not indice:
            return None
        serie = fin.loc[indice]
        valores = []
        for v in serie.head(6):
            try:
                f = float(v)
                if pd.isna(f):
                    continue
                valores.append(f)
            except (TypeError, ValueError):
                continue
        if len(valores) < 3:
            return None
        ok = all(v > 0 for v in valores[:5])
        anos = len(valores[:5])
        return {"anos": anos, "valores": valores[:5], "passou": ok}
    except Exception:
        return None


def _divida_patrimonio(ticker):
    try:
        info = yf.Ticker(f"{ticker}.SA").info
    except Exception:
        return None
    divida = info.get("totalDebt")
    patrimonio = info.get("totalStockholderEquity") or info.get("stockholdersEquity")
    if divida is not None and patrimonio:
        return {"passou": divida < patrimonio, "divida": divida, "patrimonio": patrimonio}
    d_to_e = info.get("debtToEquity")
    if d_to_e is not None:
        return {"passou": d_to_e < 100, "divida": d_to_e, "patrimonio": d_to_e * patrimonio if patrimonio else None}
    return None


def _crescimento_10_anos(ticker):
    """Crescimento comparando lucro atual vs período mais antigo disponível."""
    try:
        acao = yf.Ticker(f"{ticker}.SA")
        fin = acao.financials
        if fin is None or fin.empty:
            return None
        indice = None
        for candidato in ("Net Income", "Net Income Common Stockholders"):
            if candidato in fin.index:
                indice = candidato
                break
        if not indice:
            return None
        serie = fin.loc[indice]
        valores = []
        for v in serie:
            try:
                f = float(v)
                if pd.isna(f):
                    continue
                valores.append(f)
            except (TypeError, ValueError):
                continue
        if len(valores) < 2:
            return None
        atual = valores[0]
        antigo = valores[-1]
        return {
            "passou": atual > antigo,
            "atual": atual,
            "antigo": antigo,
            "anos": len(valores),
        }
    except Exception:
        return None


def classificar_setor(nome, setor_extra=""):
    """Classifica o setor do ativo a partir do nome e dos dados extra
    (setor_atuacao/subsetor da fiis.com.br, segmento ANBIMA e Investidor10)."""
    texto = f"{nome} {setor_extra}".lower()
    papeis = ["fundo de papel", "papéis", "papel", "recebí", "recebi", "crédito",
              "credito", "cri ", "cra", "debênture", "debenture", "fidc",
              "direitos creditórios"]
    shopping = ["shopping", "shoppings", "center", "retail", "varejo"]
    logistica = ["logístic", "logistic", "galpão", "galpao", "industriais e logísticos",
                 "distribution", "indústria", "industrial"]
    empresarial = ["escritório", "escritorio", "corporativo", "empresarial", "laud",
                   "office", "torre", "comercial", "hotel", "hospital"]

    if "fof" in texto or "fundo de fundos" in texto:
        return "Fundo de Fundos"
    if any(p in texto for p in papeis):
        return "Papel"
    if any(p in texto for p in shopping):
        return "Shopping"
    if any(p in texto for p in logistica):
        return "Logística/Galpão"
    if any(p in texto for p in empresarial):
        return "Empresarial"
    return "Outro/Híbrido"


def _buscar_fiis_com(ticker):
    """Busca setor, segmento e data de início na fiis.com.br."""
    ticker = ticker.upper().replace(".SA", "").strip()
    if ticker in _fiis_cache:
        return _fiis_cache[ticker]
    url = f"https://fiis.com.br/{ticker.lower()}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            _fiis_cache[ticker] = None
            return None
        texto = resp.text

        def grab(p):
            m = re.search(p, texto)
            return m.group(1) if m else None

        dados = {
            "nome_pregao": grab(r'"nome_pregao":"([^"]+)"'),
            "tipo_anbima": grab(r'"tipo_anbima":"([^"]+)"'),
            "segmento_ambima": grab(r'"segmento_ambima":"([^"]+)"'),
            "setor_atuacao": grab(r'"setor_atuacao":"([^"]+)"'),
            "subsetor_atuacao": grab(r'"subsetor_atuacao":"([^"]+)"'),
            "begindate": grab(r'"begindate":"([^"]+)"'),
        }
        _fiis_cache[ticker] = dados
        return dados
    except Exception:
        _fiis_cache[ticker] = None
        return None


def _buscar_base(ticker, tipo):
    """Coleta dados base via Yahoo Finance + Investidor10 (melhor esforço)."""
    dados = {"ticker": ticker, "tipo": tipo}
    try:
        acao = yf.Ticker(f"{ticker}.SA")
        info = acao.info
        hist = acao.history(period="5d")
        if hist is not None and not hist.empty:
            dados["preco"] = float(hist["Close"].iloc[-1])
            dados["volume"] = int(hist["Volume"].iloc[-1])
        dados["nome"] = info.get("longName") or info.get("shortName") or ticker
        dy_raw = info.get("dividendYield") or 0
        dados["dy"] = dy_raw * 100 if dy_raw < 1 else dy_raw
        dados["p_vp"] = info.get("priceToBook") or 0
        dados["setor"] = info.get("sector") or ""
        dados["patrimonio"] = info.get("totalAssets") or 0
    except Exception:
        dados["preco"] = dados.get("preco")
        dados["nome"] = ticker
        dados["setor"] = ""

    if tipo == "fii":
        dados_inv = _buscar_investidor10(ticker)
        if dados_inv:
            dados["vacancia"] = dados_inv.get("vacancia")
            dados["setor_inv"] = dados_inv.get("setor")
            dados["nome"] = dados_inv.get("nome") or dados.get("nome")
        dados_fiis = _buscar_fiis_com(ticker)
        if dados_fiis:
            dados["setor_fiis"] = " ".join([
                dados_fiis.get("setor_atuacao") or "",
                dados_fiis.get("subsetor_atuacao") or "",
                dados_fiis.get("segmento_ambima") or "",
                dados_fiis.get("tipo_anbima") or "",
            ]).strip()
            dados["nome"] = dados_fiis.get("nome_pregao") or dados.get("nome")
    return dados


def _buscar_investidor10(ticker):
    """Busca vacância e segmento no Investidor10."""
    url = f"https://investidor10.com.br/fiis/{ticker.lower()}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        texto = resp.text
        dados = {}
        vac = re.search(r"vac[^0-9]{0,20}([\d,.]+)\s*%", texto, re.IGNORECASE)
        if vac:
            dados["vacancia"] = float(vac.group(1).replace(".", "").replace(",", "."))
        seg = re.search(r"do segmento\s+(Híbrido|Papel|Tijolo|Logístico|FOF)", texto, re.IGNORECASE)
        if seg:
            dados["setor"] = seg.group(1)
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", texto, re.IGNORECASE)
        if h1:
            dados["nome"] = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        else:
            dados["nome"] = None
        return dados
    except Exception:
        return None


def avaliar_fii(ticker):
    """Avalia um FII conforme critérios do gestor."""
    dados = _buscar_base(ticker, "fii")
    criterios = []

    preco = dados.get("preco")
    if preco is None:
        preco = 0

    dy_m = _dy_mensal(ticker, preco)
    if dy_m is not None:
        criterios.append({
            "crit": "DY Mensal 12m (0,60–1,50%)",
            "valor": f"{dy_m:.2f}% ao mês",
            "ok": 0.60 <= dy_m <= 1.50,
            "obs": f"DY total 12m: ~{dy_m*12:.1f}% a.a.",
        })
    else:
        criterios.append({
            "crit": "DY Mensal 12m (0,60–1,50%)",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem histórico de dividendos no Yahoo Finance",
        })

    vac = dados.get("vacancia")
    if vac is not None:
        criterios.append({
            "crit": "Vacância ≤ 10%",
            "valor": f"{vac:.1f}%",
            "ok": vac <= 10,
            "obs": "" if vac <= 10 else "Acima do limite",
        })
    else:
        criterios.append({
            "crit": "Vacância ≤ 10%",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem dados (Investidor10 indisponível ou fundo de papel)",
        })

    p_vp = dados.get("p_vp")
    if p_vp:
        criterios.append({
            "crit": "P/VP entre 0,70 e 1,10",
            "valor": f"{p_vp:.2f}",
            "ok": 0.70 <= p_vp <= 1.10,
            "obs": "" if 0.70 <= p_vp <= 1.10 else "Fora da faixa",
        })
    else:
        criterios.append({
            "crit": "P/VP entre 0,70 e 1,10",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem dados",
        })

    liq_passou, liq_valor, liq_media = checar_liquidez(ticker, "fii")
    if liq_passou is not None:
        criterios.append({
            "crit": "Liquidez acima da média",
            "valor": f"R$ {liq_valor:,.0f}/dia",
            "ok": liq_passou,
            "obs": f"Média do mercado: R$ {liq_media:,.0f}/dia",
        })
    else:
        criterios.append({
            "crit": "Liquidez acima da média",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem dados de volume",
        })

    ano = _ano_listagem(ticker, "fii")
    if ano:
        idade = datetime.now().year - ano
        criterios.append({
            "crit": "Mais de 10 anos de bolsa",
            "valor": f"{idade} anos (desde {ano})",
            "ok": idade >= 10,
            "obs": "Exceção: se comprado por outro fundo",
        })
    else:
        criterios.append({
            "crit": "Mais de 10 anos de bolsa",
            "valor": "N/D",
            "ok": None,
            "obs": "Data de listagem não encontrada",
        })

    dados["setor_final"] = classificar_setor(
        dados.get("nome", ""),
        f"{dados.get('setor_fiis') or ''} {dados.get('setor_inv') or ''} {dados.get('setor') or ''}".strip(),
    )
    dados["preco_display"] = preco
    dados["dy_mensal"] = dy_m

    return {"dados": dados, "criterios": criterios, "tipo": "FII"}


def avaliar_acao(ticker):
    """Avalia uma ação conforme critérios do gestor."""
    dados = _buscar_base(ticker, "acao")
    criterios = []

    lucro = _lucro_5_anos(ticker)
    if lucro:
        criterios.append({
            "crit": "Sem prejuízo nos últimos 5 anos",
            "valor": f"{lucro['anos']} anos sem prejuízo" if lucro["passou"] else "Prejuízo no período",
            "ok": lucro["passou"],
            "obs": "Lucro verificado no histórico disponível",
        })
    else:
        criterios.append({
            "crit": "Sem prejuízo nos últimos 5 anos",
            "valor": "N/D",
            "ok": None,
            "obs": "Demonstrativo financeiro não disponível",
        })

    liq_passou, liq_valor, liq_media = checar_liquidez(ticker, "acao")
    if liq_passou is not None:
        criterios.append({
            "crit": "Ter liquidez",
            "valor": f"R$ {liq_valor:,.0f}/dia",
            "ok": liq_passou,
            "obs": f"Referência: R$ {liq_media:,.0f}/dia",
        })
    else:
        criterios.append({
            "crit": "Ter liquidez",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem dados de volume",
        })

    p_vp = dados.get("p_vp")
    if p_vp:
        criterios.append({
            "crit": "P/VP acima de 0,60",
            "valor": f"{p_vp:.2f}",
            "ok": p_vp >= 0.60,
            "obs": "" if p_vp >= 0.60 else "Abaixo do mínimo",
        })
    else:
        criterios.append({
            "crit": "P/VP acima de 0,60",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem dados",
        })

    ano = _ano_listagem(ticker, "acao")
    if ano:
        idade = datetime.now().year - ano
        criterios.append({
            "crit": "Mais de 10 anos de bolsa",
            "valor": f"{idade} anos (desde {ano})",
            "ok": idade >= 10,
            "obs": "",
        })
    else:
        criterios.append({
            "crit": "Mais de 10 anos de bolsa",
            "valor": "N/D",
            "ok": None,
            "obs": "Data de listagem não encontrada",
        })

    divida = _divida_patrimonio(ticker)
    if divida:
        if divida["patrimonio"] is not None:
            texto_divida = f"dívida R$ {divida['divida']:,.0f} vs PL R$ {divida['patrimonio']:,.0f}"
        else:
            texto_divida = f"índice dívida/PL {divida['divida']:.0f}%"
        criterios.append({
            "crit": "Dívida < Patrimônio",
            "valor": texto_divida,
            "ok": divida["passou"],
            "obs": "" if divida["passou"] else "Dívida maior que o patrimônio",
        })
    else:
        criterios.append({
            "crit": "Dívida < Patrimônio",
            "valor": "N/D",
            "ok": None,
            "obs": "Balanço não disponível",
        })

    cresc = _crescimento_10_anos(ticker)
    if cresc:
        criterios.append({
            "crit": "Crescimento nos últimos 10 anos",
            "valor": f"{cresc['anos']} anos de histórico",
            "ok": cresc["passou"],
            "obs": "Comparando lucro atual vs período mais antigo disponível",
        })
    else:
        criterios.append({
            "crit": "Crescimento nos últimos 10 anos",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem histórico suficiente",
        })

    dados["setor_final"] = dados.get("setor") or "Ação"
    dados["preco_display"] = dados.get("preco") or 0

    return {"dados": dados, "criterios": criterios, "tipo": "Ação"}


def avaliar_ativo(ticker):
    """Detecta automaticamente o tipo e avalia o ativo."""
    ticker = ticker.upper().replace(".SA", "").strip()
    if re.search(r"\d", ticker) and (ticker.endswith("11") or ticker.endswith("12")):
        return avaliar_fii(ticker)
    return avaliar_acao(ticker)


def avaliar_diversificacao(avaliacoes):
    """Verifica a mescla de setores na carteira (galpão, shopping, empresarial, papéis)."""
    setores = {}
    for av in avaliacoes:
        if av["tipo"] != "FII":
            continue
        setor = av["dados"].get("setor_final", "Outro/Híbrido")
        setores[setor] = setores.get(setor, 0) + 1

    principais = ["Logística/Galpão", "Shopping", "Empresarial", "Papel"]
    presentes = [s for s in principais if setores.get(s, 0) > 0]
    passou = len(presentes) >= 3
    return {
        "passou": passou,
        "presentes": presentes,
        "principais": principais,
        "setores": setores,
    }