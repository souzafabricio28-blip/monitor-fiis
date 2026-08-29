from lista_gestor_pdf import gerar_pdf_lista_gestor_bytes, montar_resumo_lista


def test_montar_resumo_marca_incorporacao_nos_fiis_jovens():
    resumo = montar_resumo_lista()
    por_ticker = {f["ticker"]: f for f in resumo["fundos"]}
    for ticker in ("XPLG11", "HSML11", "RZTR11"):
        assert por_ticker[ticker]["idade_ok"] is True
        assert por_ticker[ticker]["anos_ticker"] < 10
    assert por_ticker["HGLG11"]["idade_ok"] is True
    assert por_ticker["MXRF11"]["idade_ok"] is True


def test_pdf_lista_gestor_catalogo_gera_bytes():
    pdf = gerar_pdf_lista_gestor_bytes(montar_resumo_lista())
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1500
