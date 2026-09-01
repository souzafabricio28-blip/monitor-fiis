from fontes_extras import (
    FONTES_PARALELAS,
    aplicar_fontes_extras,
    consenso_numerico,
    eh_fii,
    montar_comparativo_fontes,
    parse_brapi,
    parse_fundamentus,
    parse_fundsexplorer,
    parse_google_finance,
    parse_maisretorno_next,
)


FUNDAMENTUS_PETR4 = """
<table><tr><td>Papel</td><td>PETR4</td><td>Cotação</td><td>43,55</td></tr>
<tr><td>Setor</td><td>Petróleo</td><td>Vol $ méd (2m)</td><td>1.607.350.000</td></tr></table>
<table><tr><td>P/L</td><td>4,21</td><td>P/VP</td><td>1,17</td></tr>
<tr><td>Div. Yield</td><td>8,4%</td><td>ROE</td><td>27,7%</td></tr></table>
<table><tr><td>Patrim. Líq</td><td>480.950.000.000</td></tr></table>
"""

FUNDS_EXPLORER_MXRF = """
<div class="quotation"><div class="quotation__grid__box alta">R$ 9,30 Cotação atual 9,24 0,65%</div></div>
<div class="indicators">
Liquidez Média Diária | 16,0 M | Último Rendimento | R$ | 0,10 |
Dividend Yield | 12,85 | % | últ. 12 meses | Patrimônio Líquido | R$ | 5,3 B |
Valor Patrimonial | R$ | 9,26 | por cota | P/VP | 1,00
</div>
<script>{"vacancia":"","dividendos_12_meses":1.195}</script>
"""

MAIS_RETORNO_NEXT = """
<html><script id="__NEXT_DATA__">{"props":{"pageProps":{"headers":{
"ticker":"MXRF11","mkt_cap":567206273,"actuation_segment":"Papéis","cnpj":"97521225000125"
}}}}</script></html>
"""


def test_eh_fii_respeita_unit():
    assert eh_fii("MXRF11") is True
    assert eh_fii("TAEE11") is False
    assert eh_fii("PETR4") is False


def test_parse_fundamentus_petr4():
    d = parse_fundamentus(FUNDAMENTUS_PETR4)
    assert d["preco"] == 43.55
    assert d["p_vp"] == 1.17
    assert d["dy"] == 8.4
    assert d["p_l"] == 4.21
    assert d["setor"] == "Petróleo"
    assert d["patrimonio"] == 480950000000


def test_parse_fundsexplorer_mxrf():
    d = parse_fundsexplorer(FUNDS_EXPLORER_MXRF)
    assert d["preco"] == 9.3
    assert d["dy"] == 12.85
    assert d["p_vp"] == 1.0
    assert d["vp_cota"] == 9.26
    assert d["ultimo_rendimento"] == 0.10
    assert d["vacancia"] is None


def test_parse_brapi_json():
    d = parse_brapi(
        {
            "results": [
                {
                    "regularMarketPrice": 43.55,
                    "priceEarnings": 4.2,
                    "regularMarketVolume": 1000,
                    "longName": "Petrobras",
                }
            ]
        }
    )
    assert d["preco"] == 43.55
    assert d["p_l"] == 4.2
    assert d["erro"] is None


def test_parse_brapi_erro_token():
    d = parse_brapi({"error": True, "message": "MISSING_TOKEN"})
    assert d["preco"] is None
    assert "MISSING" in (d["erro"] or "")


def test_parse_maisretorno_setor():
    d = parse_maisretorno_next(MAIS_RETORNO_NEXT)
    assert d["setor"] == "Papéis"
    assert d["patrimonio"] == 567206273


def test_parse_google_data_last_price():
    d = parse_google_finance('<div data-last-price="43.55"></div>')
    assert d["preco"] == 43.55


def test_parse_google_pdsbrc_reais():
    html = (
        '<span jsname="Pdsbrc" class=""><span>R$&nbsp;13,57</span></span>'
        '<span jsname="Pdsbrc"><span>1.117,69</span></span>'
    )
    d = parse_google_finance(html)
    assert d["preco"] == 13.57


def test_consenso_descarta_outlier():
    out = consenso_numerico(
        [
            ("Yahoo Finance", 1.35),
            ("Investidor10", 13.57),
            ("Google Finance", 13.55),
        ]
    )
    assert out["n"] == 2
    assert abs(out["valor"] - 13.56) < 0.02
    assert "Yahoo Finance" not in out["fontes"]
    assert "Investidor10" in out["fontes"]
    assert "Google Finance" in out["fontes"]


def test_aplicar_nao_zera_nem_sobrescreve_yahoo():
    dados = {"preco_atual": 10.0, "dy": None, "qualidade": {}, "divergencias": []}
    chamadas = []

    def registrar(dest, indicador, valor, fonte, confianca="media", status="ok"):
        dest[indicador] = valor
        chamadas.append((indicador, valor, fonte))

    usadas = aplicar_fontes_extras(
        dados,
        [
            {
                "fonte": "Fundamentus",
                "preco": 8.0,
                "dy": 12.0,
                "p_vp": 1.01,
                "p_l": None,
                "vacancia": None,
                "patrimonio": None,
                "setor": None,
                "liquidez_diaria": None,
                "ultimo_rendimento": None,
                "vp_cota": None,
                "erro": None,
                "url": "https://fundamentus.com.br",
            }
        ],
        registrar=registrar,
        divergencia_pct=lambda a, b: abs(a - b) / a * 100,
        limite=10.0,
    )
    assert dados["preco_atual"] == 10.0
    assert dados["dy"] == 12.0
    assert dados["p_vp"] == 1.01
    assert "Fundamentus" in usadas
    assert any("preco_atual" in x for x in dados["divergencias"])
    comparativo = dados["comparativo_fontes"]
    fund = next(l for l in comparativo if l["fonte"] == "Fundamentus")
    assert fund["preco"] == 8.0
    assert fund["dy"] == 12.0
    yahoo = next(l for l in comparativo if l["fonte"] == "Yahoo Finance")
    assert yahoo["preco"] is None  # qualidade não registrou Yahoo neste teste


def test_aplicar_preenche_preco_nan_do_yahoo():
    dados = {"preco_atual": float("nan"), "preco": float("nan"), "qualidade": {}, "divergencias": []}

    def registrar(dest, indicador, valor, fonte, confianca="media", status="ok"):
        dest[indicador] = valor

    usadas = aplicar_fontes_extras(
        dados,
        [
            {
                "fonte": "Funds Explorer",
                "preco": 9.3,
                "dy": None,
                "p_vp": None,
                "p_l": None,
                "vacancia": None,
                "patrimonio": None,
                "setor": None,
                "liquidez_diaria": None,
                "ultimo_rendimento": None,
                "vp_cota": None,
                "erro": None,
                "url": "https://www.fundsexplorer.com.br/funds/mxrf11",
            }
        ],
        registrar=registrar,
        divergencia_pct=lambda a, b: None,
        limite=10.0,
    )
    assert dados["preco_atual"] == 9.3
    assert dados["preco"] == 9.3
    assert "Funds Explorer" in usadas


def test_google_finance_entra_no_pool_paralelo():
    nomes = [fn.__name__ for fn in FONTES_PARALELAS]
    assert "buscar_google_finance" in nomes
    assert "buscar_fundamentus" in nomes


def test_ptax_usa_cache(monkeypatch):
    import fontes_extras

    fontes_extras._PTAX_CACHE["ts"] = 0.0
    fontes_extras._PTAX_CACHE["dados"] = None
    chamadas = []

    class _Resp:
        status_code = 200

        def json(self):
            return {"value": [{"cotacaoVenda": 5.4321}]}

    def fake_get(url, *, accept_json=False):
        chamadas.append(url)
        return _Resp()

    monkeypatch.setattr(fontes_extras, "_get", fake_get)
    a = fontes_extras.buscar_ptax()
    b = fontes_extras.buscar_ptax()
    assert a["usd_brl"] == 5.4321
    assert b["usd_brl"] == 5.4321
    assert len(chamadas) == 1
    c = fontes_extras.buscar_ptax(forcar=True)
    assert c["usd_brl"] == 5.4321
    assert len(chamadas) == 2


def test_comparativo_reconhece_yahoo_proventos():
    linhas = montar_comparativo_fontes(
        {
            "preco_atual": 9.3,
            "dy": 12.0,
            "p_vp": None,
            "qualidade": {
                "preco_atual": {"fonte": "Yahoo Finance"},
                "dy": {"fonte": "Yahoo Finance (proventos 12m)"},
            },
            "dy_investidor10": 11.5,
        },
        [],
    )
    yahoo = next(l for l in linhas if l["fonte"] == "Yahoo Finance")
    assert yahoo["preco"] == 9.3
    assert yahoo["dy"] == 12.0
    i10 = next(l for l in linhas if l["fonte"] == "Investidor10")
    assert i10["dy"] == 11.5
