from whatsapp_notifier import (
    NUMERO_PADRAO,
    normalizar_telefone,
    enviar_mensagem,
    telefone_destino,
    whatsapp_configurado,
)


def test_normaliza_celular_br():
    assert normalizar_telefone("11973674455") == NUMERO_PADRAO
    assert normalizar_telefone("(11) 97367-4455") == NUMERO_PADRAO
    assert normalizar_telefone("+55 11 97367-4455") == NUMERO_PADRAO
    assert telefone_destino() == NUMERO_PADRAO


def test_telefone_env_override(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE", "11973674455")
    assert telefone_destino() == NUMERO_PADRAO


def test_whatsapp_configurado_exige_chave(monkeypatch):
    monkeypatch.delenv("WHATSAPP_APIKEY", raising=False)
    monkeypatch.delenv("CALLMEBOT_APIKEY", raising=False)
    assert whatsapp_configurado() is False
    monkeypatch.setenv("WHATSAPP_APIKEY", "x")
    assert whatsapp_configurado() is True


def test_enviar_whatsapp_sem_chave_nao_chama_rede(monkeypatch):
    monkeypatch.delenv("WHATSAPP_APIKEY", raising=False)
    monkeypatch.delenv("CALLMEBOT_APIKEY", raising=False)
    chamadas = []
    monkeypatch.setattr("whatsapp_notifier.requests.get", lambda *a, **k: chamadas.append(1))
    assert enviar_mensagem("oi") is False
    assert chamadas == []


def test_enviar_whatsapp_com_chave(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APIKEY", "abc")
    class _Resp:
        status_code = 200
        text = "Message queued"

    def _get(url, timeout=25):
        assert "5511973674455" in url
        assert "apikey=abc" in url
        return _Resp()

    monkeypatch.setattr("whatsapp_notifier.requests.get", _get)
    assert enviar_mensagem("alerta teste") is True
