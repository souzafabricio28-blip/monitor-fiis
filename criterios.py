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
from datetime import datetime, timedelta, timezone

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
_pvp_cache = {}


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
    # Anos de listagem curados (CVM, relatórios do fundo, fiis.com.br).
    # Preferidos ao scraping: dado ausente permanece N/D, nunca 0.
    "MXRF11": 2011,
    "KNCR11": 2012,
    "KNHY11": 2018,
    "CPTS11": 2014,
    "MCCI11": 2018,
    "IRDM11": 2017,
    "KNSC11": 2020,
    "VGIR11": 2018,
    "BTCI11": 2008,
    "HGLG11": 2010,
    "BTLG11": 2010,
    "VILG11": 2019,
    "GGRC11": 2014,
    "XPLG11": 2018,
    "XPML11": 2017,
    "VISC11": 2013,
    "HSML11": 2018,
    "MALL11": 2018,
    "KNRI11": 2010,
    "HGRE11": 2010,
    "RCRB11": 2010,
    "RBRR11": 2018,
    "TRXF11": 2018,
    "HFOF11": 2018,
    "MANA11": 2022,
    "SNEL11": 2022,
    "VGHF11": 2021,
    "PETR4": 1997,
    "VALE3": 2000,
    "ITUB4": 2002,
    "WEGE3": 1982,
    "ABEV3": 2013,
    "BBAS3": 2006,
    "ITSA3": 1977,
    "TAEE11": 2006,
    "SAPR4": 1994,
    "KLBN4": 1986,
    "RZTR11": 2020,
}

# Fundo atual herda a idade de bolsa da origem (troca de nome / incorporação).
# O ticker novo no Yahoo parece "jovem"; o gestor conta o veículo original.
_CONTINUIDADE_INCORPORACAO = {
    "XPLG11": "Ticker desde 2018; continuidade/incorporação de veículo anterior. Idade de bolsa pela origem (>= 10 anos), não só pelo IPO do ticker.",
    "HSML11": "Ticker desde 2018; continuidade/incorporação. Idade de bolsa pela origem (>= 10 anos), não só pelo IPO do ticker.",
    "RZTR11": "Ticker desde 2020; continuidade/incorporação. Idade de bolsa pela origem (>= 10 anos), não só pelo IPO do ticker.",
    "BTLG11": "CNPJ desde 2010; incorporou VVPR11 e BLCP11 em 2022.",
}


def _ano_listagem_yahoo(ticker):
    """Ano da primeira negociação no Yahoo (firstTradeDateEpochUtc)."""
    try:
        info = yf.Ticker(f"{ticker}.SA").info or {}
        epoch = info.get("firstTradeDateEpochUtc")
        if not epoch:
            return None
        ano = datetime.fromtimestamp(int(epoch), tz=timezone.utc).year
        ano_atual = datetime.now().year
        if 1975 <= ano <= ano_atual:
            return ano
    except Exception:
        return None
    return None


def parse_pvp_fundamentus(html: str):
    """Extrai P/VP da página do Fundamentus. Ausente permanece None, nunca 0."""
    if not html:
        return None
    texto = re.sub(r"<[^>]+>", "|", html)
    texto = texto.replace("&nbsp;", " ")
    m = re.search(r"P/VP\|+\s*([\d]+,[\d]+)", texto, re.IGNORECASE)
    if not m:
        m = re.search(r"P/VP[^\d]{0,120}(\d+,\d+)", texto, re.IGNORECASE)
    if not m:
        return None
    try:
        valor = float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None
    if valor <= 0:
        return None
    return valor


def _pvp_fundamentus(ticker: str):
    ticker = (ticker or "").upper().replace(".SA", "").strip()
    if ticker in _pvp_cache:
        return _pvp_cache[ticker]
    url = f"https://fundamentus.com.br/detalhes.php?papel={ticker}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            _pvp_cache[ticker] = None
            return None
        valor = parse_pvp_fundamentus(resp.text)
        _pvp_cache[ticker] = valor
        return valor
    except Exception:
        _pvp_cache[ticker] = None
        return None


def escolher_pvp_acao(pvp_yahoo, pvp_fundamentus, book_value=None, preco=None):
    """Yahoo distorce P/B de PN (SAPR4, KLBN4). Fundamentus (VPA da B3) tem prioridade."""
    if pvp_fundamentus:
        try:
            valor = float(pvp_fundamentus)
            if valor > 0:
                return valor, "fundamentus"
        except (TypeError, ValueError):
            pass
    if preco and book_value:
        try:
            book = float(book_value)
            calc = float(preco) / book if book > 0 else None
            if calc and 0.15 <= calc <= 12:
                return calc, "preco/vpa"
        except (TypeError, ValueError):
            pass
    if pvp_yahoo:
        try:
            valor = float(pvp_yahoo)
            if valor > 0:
                return valor, "yahoo"
        except (TypeError, ValueError):
            pass
    return None, None


def _ano_listagem(ticker, tipo, permitir_scrape=False):
    """Ano de listagem: catálogo, depois Yahoo, scrape só como fallback."""
    ticker = ticker.upper().replace(".SA", "").strip()
    if ticker in _ANOS_LISTAGEM:
        return _ANOS_LISTAGEM[ticker]

    ano_yahoo = _ano_listagem_yahoo(ticker)
    if ano_yahoo:
        return ano_yahoo

    if not permitir_scrape:
        return None

    ano_atual = datetime.now().year
    if tipo == "fii":
        dados_fiis = _buscar_fiis_com(ticker)
        if dados_fiis and dados_fiis.get("begindate"):
            try:
                ano = int(dados_fiis["begindate"][:4])
                if 1975 <= ano < ano_atual:
                    return ano
            except (TypeError, ValueError):
                pass

    base = "fiis" if tipo == "fii" else "acoes"
    url = f"https://investidor10.com.br/{base}/{ticker.lower()}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        texto = resp.text
        padroes = [
            r"(?:listad[oa]|desde|listagem|ingressou|iniciou)[^0-9]{0,40}(?:19|20)\d{2}",
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


def classificar_setor(nome, setor_extra="", ticker=""):
    """Classifica o setor do ativo a partir do catálogo curado, do nome e dos dados extra
    (setor_atuacao/subsetor da fiis.com.br, segmento ANBIMA e Investidor10)."""
    ticker = (ticker or "").upper().replace(".SA", "").strip()
    if ticker:
        from fiis_database import buscar_fii_por_ticker

        curado = buscar_fii_por_ticker(ticker)
        if curado and curado.get("setor"):
            return curado["setor"]
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


def _aplicar_catalogo(ticker, dados):
    from fiis_database import buscar_fii_por_ticker

    curado = buscar_fii_por_ticker(ticker)
    if curado:
        dados["nome"] = curado.get("nome") or dados.get("nome") or ticker
        dados["setor"] = curado.get("setor") or dados.get("setor") or ""
    dados["setor_inv"] = dados.get("setor")
    return dados


def _buscar_base_yahoo_fii(ticker):
    """Preço, DY e P/VP via Yahoo + catálogo. Sem scrape."""
    from market_data import buscar_cotacao, calcular_dy

    dados = {
        "ticker": ticker,
        "tipo": "fii",
        "nome": ticker,
        "preco": None,
        "preco_atual": None,
        "dy": None,
        "dy_mensal": None,
        "p_vp": None,
        "vacancia": None,
        "setor": "",
        "setor_fiis": "",
        "volume": None,
    }
    cotacao = buscar_cotacao(ticker)
    if cotacao:
        dados["preco"] = cotacao.get("preco_atual")
        dados["preco_atual"] = cotacao.get("preco_atual")
        dados["volume"] = cotacao.get("volume")
    dy = calcular_dy(ticker, dados.get("preco"))
    if dy:
        dados["dy"] = dy.get("dy_anual")
        dados["dy_mensal"] = dy.get("dy_mensal")
        dados["total_dividendos_12m"] = dy.get("total_dividendos_12m")
    try:
        info = yf.Ticker(f"{ticker}.SA").info or {}
        dados["nome"] = info.get("longName") or info.get("shortName") or ticker
        pvp = info.get("priceToBook")
        if pvp:
            dados["p_vp"] = float(pvp)
    except Exception:
        pass
    return _aplicar_catalogo(ticker, dados)


def _buscar_base(ticker, tipo, permitir_scrape=False):
    """Yahoo + catálogo primeiro; scrape só se faltar dado e for pedido."""
    if tipo == "fii":
        dados = _buscar_base_yahoo_fii(ticker)
        if not permitir_scrape:
            return dados

        from market_data import buscar_dados_completos

        extra = buscar_dados_completos(ticker, incluir_fundamentos=True)
        campos_i10 = (
            "preco",
            "preco_atual",
            "dy",
            "dy_mensal",
            "p_vp",
            "nome",
            "vacancia",
            "setor",
            "tipo",
            "liquidez_diaria",
            "variacao_dia",
            "variacao_12m",
            "cotistas",
            "cotas_emitidas",
            "vp_cota",
            "taxa_administracao",
            "gestao",
            "ultimo_rendimento",
            "patrimonio",
            "p_l",
            "razao_social",
            "cnpj",
            "mandato",
        )
        for campo in campos_i10:
            if dados.get(campo) in (None, "") and extra.get(campo) not in (None, ""):
                dados[campo] = extra.get(campo)
        if extra.get("setor"):
            dados["setor_inv"] = extra.get("setor")
        if dados.get("vacancia") is None:
            inv = _buscar_investidor10(ticker)
            if inv and inv.get("vacancia") is not None:
                dados["vacancia"] = inv["vacancia"]
                dados["setor_inv"] = inv.get("setor") or dados.get("setor_inv")
                for campo in campos_i10:
                    if dados.get(campo) in (None, "") and inv.get(campo) not in (None, ""):
                        dados[campo] = inv[campo]
        return _aplicar_catalogo(ticker, dados)

    dados = {"ticker": ticker, "tipo": tipo}
    try:
        acao = yf.Ticker(f"{ticker}.SA")
        info = acao.info or {}
        hist = acao.history(period="5d")
        if hist is not None and not hist.empty:
            dados["preco"] = float(hist["Close"].iloc[-1])
            dados["volume"] = int(hist["Volume"].iloc[-1])
        dados["nome"] = info.get("longName") or info.get("shortName") or ticker
        dy_raw = info.get("dividendYield") or 0
        dados["dy"] = dy_raw * 100 if dy_raw < 1 else dy_raw
        pvp, fonte_pvp = escolher_pvp_acao(
            pvp_yahoo=info.get("priceToBook"),
            pvp_fundamentus=_pvp_fundamentus(ticker),
            book_value=info.get("bookValue"),
            preco=dados.get("preco"),
        )
        dados["p_vp"] = pvp
        dados["p_vp_fonte"] = fonte_pvp
        dados["setor"] = info.get("sector") or ""
        dados["patrimonio"] = info.get("totalAssets") or 0
    except Exception:
        dados["preco"] = dados.get("preco")
        dados["nome"] = ticker
        dados["setor"] = ""

    if permitir_scrape:
        inv = _buscar_investidor10(ticker)
        if inv:
            if inv.get("p_l") is not None:
                dados["p_l"] = inv["p_l"]
            for campo in ("liquidez_diaria", "variacao_12m", "variacao_dia"):
                if inv.get(campo) is not None:
                    dados[campo] = inv[campo]
            if not dados.get("dy") and inv.get("dy") is not None:
                dados["dy"] = inv["dy"]
            if dados.get("p_vp") is None and inv.get("p_vp") is not None:
                dados["p_vp"] = inv["p_vp"]
    return dados


def _buscar_investidor10(ticker):
    """Vacância, segmento e demais indicadores públicos do Investidor10."""
    try:
        from investidor10 import Investidor10API

        dados = Investidor10API().buscar_ativo(ticker)
        if dados.get("erro"):
            return None
        return dados
    except Exception:
        return None


def _criterio_idade_fii(ticker, ano):
    """≥10 anos no ticker atual, ou continuidade por troca de nome / incorporação."""
    ticker = (ticker or "").upper().replace(".SA", "").strip()
    continuidade = _CONTINUIDADE_INCORPORACAO.get(ticker)
    if ano:
        idade = datetime.now().year - ano
        passou = idade >= 10 or bool(continuidade)
        if continuidade and idade < 10:
            valor = (
                f"{idade} anos no ticker (desde {ano}); origem/incorporação >= 10 anos"
            )
            obs = continuidade
        else:
            valor = f"{idade} anos (desde {ano})"
            obs = continuidade or "Exceção: se comprado por outro fundo"
        return {
            "crit": "Mais de 10 anos de bolsa",
            "valor": valor,
            "ok": passou,
            "obs": obs,
        }
    if continuidade:
        return {
            "crit": "Mais de 10 anos de bolsa",
            "valor": "origem/incorporação >= 10 anos",
            "ok": True,
            "obs": continuidade,
        }
    return {
        "crit": "Mais de 10 anos de bolsa",
        "valor": "N/D",
        "ok": None,
        "obs": "Data de listagem não encontrada",
    }


def avaliar_fii(ticker, permitir_scrape=False):
    """Avalia um FII conforme critérios do gestor."""
    dados = _buscar_base(ticker, "fii", permitir_scrape=permitir_scrape)
    criterios = []

    preco = dados.get("preco")
    if preco is None:
        preco = 0

    dy_m = dados.get("dy_mensal")
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
            "obs": "Sem dados de vacância — N/D, não assumido como 0%",
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

    criterios.append(
        _criterio_idade_fii(
            ticker,
            _ano_listagem(ticker, "fii", permitir_scrape=permitir_scrape),
        )
    )

    dados["setor_final"] = classificar_setor(
        dados.get("nome", ""),
        f"{dados.get('setor_fiis') or ''} {dados.get('setor_inv') or ''} {dados.get('setor') or ''}".strip(),
        ticker=ticker,
    )
    dados["preco_display"] = preco
    dados["dy_mensal"] = dy_m

    return {"dados": dados, "criterios": criterios, "tipo": "FII"}


def avaliar_acao(ticker, permitir_scrape=False):
    """Avalia uma ação conforme critérios do gestor."""
    dados = _buscar_base(ticker, "acao", permitir_scrape=permitir_scrape)
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
    fonte_pvp = dados.get("p_vp_fonte") or ""
    if p_vp:
        criterios.append({
            "crit": "P/VP acima de 0,60",
            "valor": f"{p_vp:.2f}",
            "ok": p_vp >= 0.60,
            "obs": " · ".join(
                part
                for part in (
                    None if p_vp >= 0.60 else "Abaixo do mínimo",
                    f"fonte {fonte_pvp}" if fonte_pvp else None,
                )
                if part
            ),
        })
    else:
        criterios.append({
            "crit": "P/VP acima de 0,60",
            "valor": "N/D",
            "ok": None,
            "obs": "Sem dados",
        })

    ano = _ano_listagem(ticker, "acao", permitir_scrape=permitir_scrape)
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


def eh_fii(ticker: str) -> bool:
    ticker = (ticker or "").upper().replace(".SA", "").strip()
    from lista_gestor import TICKERS_ACAO_MESMO_COM_11

    if ticker in TICKERS_ACAO_MESMO_COM_11:
        return False
    return bool(re.search(r"\d", ticker) and (ticker.endswith("11") or ticker.endswith("12")))


def classe_ativo(ticker: str) -> str:
    """'fundo' para FII/Fiagro 11/12; 'acao' para o restante (ex.: PETR4)."""
    return "fundo" if eh_fii(ticker) else "acao"


def avaliar_ativo(ticker, permitir_scrape=False):
    """Detecta automaticamente o tipo e avalia o ativo.

    Por omissão usa Yahoo + catálogo. Scraping (fiis.com.br / Investidor10)
    só entra quando permitir_scrape=True e ainda falta dado (ex.: vacância).
    """
    ticker = ticker.upper().replace(".SA", "").strip()
    if eh_fii(ticker):
        return avaliar_fii(ticker, permitir_scrape=permitir_scrape)
    return avaliar_acao(ticker, permitir_scrape=permitir_scrape)


SETORES_ALVO = ["Logística/Galpão", "Shopping", "Empresarial", "Papel"]


def avaliar_diversificacao_setores(setores_presentes):
    """Diversificação a partir da lista de setores (catálogo ou avaliação)."""
    setores = {}
    ignorar = {"", "n/d", "ação", "acao", "outro/híbrido", "outro/hibrido"}
    for setor in setores_presentes:
        nome = str(setor or "").strip()
        if not nome or nome.lower() in ignorar:
            continue
        setores[nome] = setores.get(nome, 0) + 1
    presentes = [s for s in SETORES_ALVO if setores.get(s, 0) > 0]
    faltando = [s for s in SETORES_ALVO if s not in presentes]
    return {
        "passou": len(presentes) >= 3,
        "presentes": presentes,
        "faltando": faltando,
        "principais": list(SETORES_ALVO),
        "setores": setores,
    }


def avaliar_diversificacao(avaliacoes):
    """Verifica a mescla de setores na carteira (galpão, shopping, empresarial, papéis)."""
    nomes = []
    for av in avaliacoes:
        if not av or av.get("tipo") != "FII":
            continue
        nomes.append(av.get("dados", {}).get("setor_final", "Outro/Híbrido"))
    return avaliar_diversificacao_setores(nomes)