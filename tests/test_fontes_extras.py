from fontes_extras import (
    aplicar_fontes_extras,
    eh_fii,
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
<div class="quotation"><div class="quotation__grid__box alta">R$ 9,30 Cotação atual</div></div>
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
