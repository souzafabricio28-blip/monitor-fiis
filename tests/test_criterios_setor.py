from criterios import classificar_setor, eh_fii
from seed_local import POSICOES_LOCAIS, garantir_carteira_local, garantir_plano_local


def test_knri11_e_empresarial_pelo_catalogo():
    assert classificar_setor("Kinea Renda Imobiliária", ticker="KNRI11") == "Empresarial"
    assert classificar_setor("", ticker="KNCR11") == "Papel"
    assert classificar_setor("", ticker="XPML11") == "Shopping"
    assert classificar_setor("", ticker="BTLG11") == "Logística/Galpão"


def test_heuristica_sem_ticker_ainda_funciona():
    assert classificar_setor("Fundo de Papel CRI") == "Papel"
    assert classificar_setor("Shopping Iguatemi") == "Shopping"
    assert classificar_setor("Fundo desconhecido") == "Outro/Híbrido"


def test_seed_local_so_em_sqlite_vazio(tmp_path, monkeypatch):
    import db as db_module
    from db import DatabaseManager

    monkeypatch.setattr(db_module, "USE_POSTGRES", False)
    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    db = DatabaseManager(str(tmp_path / "seed.db"))
    assert garantir_carteira_local(db) == len(POSICOES_LOCAIS)
    assert len(db.obter_carteira()) == len(POSICOES_LOCAIS)
    assert garantir_carteira_local(db) == 0
    mxrf = db.obter_carteira().set_index("ticker").loc["MXRF11"]
    assert int(mxrf["quantidade"]) == 48
    assert "ITSA4" in set(db.obter_carteira()["ticker"].str.upper())
    assert "RURA11" not in set(db.obter_carteira()["ticker"].str.upper())
    assert garantir_plano_local(db) > 0
    plano = db.obter_plano_rebalanceamento()
    assert not plano.empty
    assert "VRTM11" in set(plano["ticker"])
    assert "VISC11" in set(plano["ticker"])
    assert garantir_plano_local(db) == 0


def test_petr4_nao_e_fii():
    assert eh_fii("MXRF11")
    assert eh_fii("KNRI11")
    assert eh_fii("RZTR11")
    assert not eh_fii("PETR4")
    assert not eh_fii("VALE3")
    assert not eh_fii("TAEE11")
    assert not eh_fii("BPAC11")


def test_classe_ativo_separa_fundo_e_acao():
    from criterios import classe_ativo

    assert classe_ativo("MXRF11") == "fundo"
    assert classe_ativo("KNRI11") == "fundo"
    assert classe_ativo("HGLG12") == "fundo"
    assert classe_ativo("mxrf11.sa") == "fundo"
    assert classe_ativo("PETR4") == "acao"
    assert classe_ativo("VALE3") == "acao"
    assert classe_ativo("TAEE11") == "acao"
    assert classe_ativo("") == "acao"


def test_lista_gestor_separa_taee11_como_acao():
    from criterios import classificar_setor
    from lista_gestor import ACOES_GESTOR, FUNDOS_GESTOR

    assert "TAEE11" in ACOES_GESTOR
    assert "TAEE11" not in FUNDOS_GESTOR
    assert FUNDOS_GESTOR.count("BBAS3") == 0
    assert ACOES_GESTOR.count("BBAS3") == 1
    assert classificar_setor("", ticker="RZTR11") == "Outro/Híbrido"
    assert classificar_setor("", ticker="HGLG11") == "Logística/Galpão"
    assert classificar_setor("", ticker="HSML11") == "Shopping"


def test_diversificacao_mostra_setores_faltando():
    from criterios import avaliar_diversificacao_setores

    so_papel = avaliar_diversificacao_setores(["Papel", "Papel", "Ação", "N/D"])
    assert so_papel["presentes"] == ["Papel"]
    assert so_papel["faltando"] == ["Logística/Galpão", "Shopping", "Empresarial"]
    assert so_papel["passou"] is False

    completa = avaliar_diversificacao_setores(
        ["Papel", "Shopping", "Empresarial", "Logística/Galpão"]
    )
    assert completa["passou"] is True
    assert completa["faltando"] == []


def test_diversificacao_lista_gestor():
    from criterios import avaliar_diversificacao_setores, classificar_setor
    from lista_gestor import FUNDOS_GESTOR

    setores = [classificar_setor("", ticker=t) for t in FUNDOS_GESTOR]
    div = avaliar_diversificacao_setores(setores)
    assert "Logística/Galpão" in div["presentes"]
    assert "Shopping" in div["presentes"]
    assert "Papel" in div["presentes"]
    assert "Empresarial" in div["faltando"]
    assert div["passou"] is True
