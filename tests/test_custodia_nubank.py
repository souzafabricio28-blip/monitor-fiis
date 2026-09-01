from custodia_nubank import (
    CHAVE_SYNC,
    CUSTODIA_NUBANK_20260901,
    aplicar_extrato_nubank,
    comparar_com_carteira,
    parse_extrato_nubank_texto,
    sincronizar_custodia_nubank,
)
import db as db_module
from db import DatabaseManager


TEXTO_EXEMPLO = """
Extrato de Custódia Custódia em: 01/09/2026
Custódia em Bolsa de Valores
Tipo de Ativo Emissor Quantidade Saldo bruto (R$) Disponível em
Fundo Imobiliário (FII) Maxi Renda (MXRF11) 48,00 442,08 Até 2 dias úteis
Fundo Imobiliário (FII) BTG Pactual Crédito Imobiliário (BTCI11) 10,00 91,10 Até 2 dias úteis
Ação brasileira Petrobras (PETR4) 4,00 187,48 Até 2 dias úteis
Ação brasileira Itaúsa (ITSA4) 2,00 26,32 Até 2 dias úteis
Total 1.310,30
"""


def _db_local(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    return DatabaseManager(str(tmp_path / "custodia.db"))


def test_parse_extrato_nubank_texto():
    parseado = parse_extrato_nubank_texto(TEXTO_EXEMPLO)
    assert parseado["data_custodia"] == "01/09/2026"
    assert parseado["posicoes"]["MXRF11"]["quantidade"] == 48
    assert abs(float(parseado["posicoes"]["MXRF11"]["preco_unitario"]) - 9.21) < 0.01
    assert parseado["posicoes"]["ITSA4"]["quantidade"] == 2


def test_aplicar_extrato_atualiza_quantidade_e_valor(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.registrar_movimentacao("MXRF11", "SALDO_INICIAL", 59, 9.23)
    db.registrar_movimentacao("ITSA3", "SALDO_INICIAL", 2, 26.50)

    parseado = parse_extrato_nubank_texto(TEXTO_EXEMPLO)
    previa = comparar_com_carteira(db, parseado["posicoes"])
    assert "MXRF11" in [a["ticker"] for a in previa["atualizar"]]
    assert "ITSA4" in [a["ticker"] for a in previa["atualizar"]] or "ITSA4" in previa["novos"]

    resultado = aplicar_extrato_nubank(db, parseado, remover_ausentes=False)
    assert resultado["aplicado"] is True

    carteira = {
        str(r["ticker"]).upper(): (
            int(r["quantidade"]),
            float(r["preco_compra"]),
        )
        for _, r in db.obter_carteira().iterrows()
    }
    assert carteira["MXRF11"][0] == 48
    assert abs(carteira["MXRF11"][1] - 9.21) < 0.02
    assert "ITSA3" not in carteira
    assert carteira["ITSA4"][0] == 2
    assert abs(carteira["ITSA4"][1] - 13.16) < 0.02
    assert carteira["PETR4"][0] == 4


def test_sincronizar_custodia_nubank_ajusta_e_realoca(tmp_path, monkeypatch):
    db = _db_local(tmp_path, monkeypatch)
    db.registrar_movimentacao("MXRF11", "SALDO_INICIAL", 59, 9.23)
    db.registrar_movimentacao("PETR4", "SALDO_INICIAL", 5, 42.26)
    db.registrar_movimentacao("ITSA3", "SALDO_INICIAL", 2, 26.50)
    db.registrar_movimentacao("RURA11", "SALDO_INICIAL", 12, 8.14)

    primeiro = sincronizar_custodia_nubank(db)
    assert primeiro["aplicado"] is True

    carteira = {
        str(r["ticker"]).upper(): int(r["quantidade"])
        for _, r in db.obter_carteira().iterrows()
    }
    assert carteira["MXRF11"] == 48
    assert carteira["PETR4"] == 4
    assert "ITSA3" not in carteira
    assert carteira["ITSA4"] == 2
    assert "RURA11" not in carteira
    assert set(carteira) == set(CUSTODIA_NUBANK_20260901)

    segundo = sincronizar_custodia_nubank(db)
    assert segundo["aplicado"] is False
    assert db.get_config(CHAVE_SYNC)
