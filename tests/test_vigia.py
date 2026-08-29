from vigia import checar_saude, montar_relatorio, resumir_com_ia


def test_montar_relatorio_site_fora_e_queda():
    texto = montar_relatorio(
        {"ok": False, "url": "http://x/_stcore/health", "detalhe": "timeout"},
        {
            "erro": None,
            "posicoes": 2,
            "quedas": [{"ticker": "PETR4", "pct": -12}],
            "watchlist": [],
            "proventos": 0,
            "investido": 1000.0,
            "patrimonio": 900.0,
            "sem_cotacao": [],
        },
    )
    assert "FORA" in texto
    assert "PETR4" in texto
    assert "Proventos" in texto


def test_relatorio_carteira_vazia():
    texto = montar_relatorio({"ok": True, "url": "http://x/h"}, {"erro": "Carteira vazia"})
    assert "Carteira vazia" in texto


def test_checar_saude_ok(monkeypatch):
    class _Resp:
        status_code = 200

    monkeypatch.setattr("vigia.requests.get", lambda *a, **k: _Resp())
    out = checar_saude("https://exemplo.test")
    assert out["ok"] is True


def test_sem_chave_ia_nao_chama_rede(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chamadas = []
    monkeypatch.setattr("vigia.requests.post", lambda *a, **k: chamadas.append(1))
    assert resumir_com_ia("relatorio") is None
    assert chamadas == []


def test_enviar_whatsapp_sem_chave_nao_dispara(monkeypatch):
    monkeypatch.delenv("WHATSAPP_APIKEY", raising=False)
    monkeypatch.delenv("CALLMEBOT_APIKEY", raising=False)
    from vigia import enviar_whatsapp_vigia

    chamadas = []
    monkeypatch.setattr(
        "whatsapp_notifier.enviar_alerta",
        lambda *a, **k: chamadas.append(1) or True,
    )
    assert enviar_whatsapp_vigia("resumo") is False
    assert chamadas == []
