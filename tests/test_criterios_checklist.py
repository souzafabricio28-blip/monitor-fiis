import pandas as pd

import db as db_module
from criterios import (
    atualizar_criterios_carteira,
    checar_liquidez,
    linha_tabela_criterios,
    montar_tabelas_checklist,
)
from db import DatabaseManager


def _db_local(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    return DatabaseManager(str(tmp_path / "checklist.db"))


def test_linha_fii_mostra_campos_investidor10():
    av = {
        "tipo": "FII",
        "criterios": [{"ok": True}, {"ok": None}],
        "dados": {
            "setor_final": "Papel",
            "vacancia": 2.9,
            "liquidez_diaria": 17_300_000,
            "cotistas": 608340,
            "vp_cota": 166.43,
            "taxa_administracao": 0.6,
            "variacao_12m": 4.81,
        },
    }
    linha = linha_tabela_criterios("MXRF11", av, "fundo")
    assert linha["Vacância"] == "2,90%"
    assert linha["Liquidez"] == "R$ 17,30 M"
    assert linha["Cotistas"] == "608.340"
    assert linha["VP/cota"] == "R$ 166,43"
    assert linha["Taxa adm."] == "0,60%"
    assert linha["Var. 12M"] == "4,81%"
    assert linha["Setor"] == "Papel"


def test_linha_acao_nao_usa_criterios_de_fii():
    linha = linha_tabela_criterios("PETR4", None, "acao")
    assert "Vacância" not in linha
    assert "Cotistas" not in linha
    assert "Taxa adm." not in linha
    assert linha["P/VP"] == "N/D"
    assert linha["Status"] == "AÇÃO"


def test_linha_sem_dado_fica_nd():
    linha = linha_tabela_criterios(
        "HGLG11",
        {"tipo": "FII", "criterios": [], "dados": {"vacancia": float("nan")}},
        "fundo",
    )
    assert linha["Vacância"] == "N/D"
    assert linha["Cotistas"] == "N/D"
    assert linha["Status"] == "N/D"


def test_montar_tabelas_separa_fundos_e_acoes():
    carteira = pd.DataFrame({"ticker": ["MXRF11", "PETR4"]})
    avs = {
        "MXRF11": {
            "tipo": "FII",
            "criterios": [{"ok": True}],
            "dados": {"vacancia": 1.0, "setor_final": "Papel"},
        }
    }
    fundos, acoes, setores = montar_tabelas_checklist(carteira, lambda t: avs.get(t))
    assert [r["Ticker"] for r in fundos] == ["MXRF11"]
    assert "Vacância" in fundos[0]
    assert [r["Ticker"] for r in acoes] == ["PETR4"]
    assert "Vacância" not in acoes[0]
    assert "Papel" in setores


def test_atualizar_criterios_grava_e_deduplica(tmp_path, monkeypatch):
    import criterios

    db = _db_local(tmp_path, monkeypatch)

    def fake_avaliar(ticker, permitir_scrape=False):
        assert permitir_scrape is True
        return {
            "tipo": "FII",
            "criterios": [],
            "dados": {"ticker": ticker, "vacancia": 3.0, "taxa_administracao": 0.5},
        }

    monkeypatch.setattr(criterios, "avaliar_ativo", fake_avaliar)
    out = atualizar_criterios_carteira(db, ["MXRF11", "mxrf11", ""])
    assert out["ok"] == ["MXRF11"]
    assert out["falhas"] == {}
    gravado = db.obter_avaliacao("MXRF11")
    assert gravado["dados"]["vacancia"] == 3.0
    assert gravado["dados"]["taxa_administracao"] == 0.5


def test_checar_liquidez_nan_nao_inventa_zero(monkeypatch):
    import criterios

    monkeypatch.setattr(criterios, "_valor_negociado_diario", lambda t: 2_000_000)
    monkeypatch.setattr(criterios, "_volume_referencia", lambda t: 1_000_000)
    ok, valor, _media = checar_liquidez("MXRF11", "fii", float("nan"))
    assert ok is True
    assert valor == 2_000_000


def test_buscar_base_completa_i10_quando_falta_campo(monkeypatch):
    import criterios

    monkeypatch.setattr(
        criterios, "_buscar_base_yahoo_fii", lambda t: {"ticker": t, "preco": 10}
    )
    monkeypatch.setattr(
        "market_data.buscar_dados_completos",
        lambda *a, **k: {"ticker": "MXRF11"},
    )
    monkeypatch.setattr(
        criterios,
        "_buscar_investidor10",
        lambda t: {
            "vacancia": 2.9,
            "liquidez_diaria": 1_000_000,
            "cotistas": 10,
            "vp_cota": 9.5,
            "taxa_administracao": 0.5,
            "variacao_12m": 4.0,
        },
    )
    monkeypatch.setattr(criterios, "_aplicar_catalogo", lambda t, d: d)
    dados = criterios._buscar_base("MXRF11", "fii", permitir_scrape=True)
    assert dados["vacancia"] == 2.9
    assert dados["liquidez_diaria"] == 1_000_000
    assert dados["cotistas"] == 10
    assert dados["vp_cota"] == 9.5
    assert dados["taxa_administracao"] == 0.5
    assert dados["variacao_12m"] == 4.0
