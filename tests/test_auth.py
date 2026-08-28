import time

import auth


def test_producao_exige_autenticacao(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert auth.auth_obrigatorio() is True


def test_comparacao_de_senha():
    assert auth._senha_ok("senha-complexa", "senha-complexa")
    assert not auth._senha_ok("errada", "senha-complexa")
    assert auth._credenciais_producao_validas("usuario", "senha-complexa")
    assert not auth._credenciais_producao_validas("admin", "senha-complexa")
    assert not auth._credenciais_producao_validas("usuario", "curta")


def test_sessao_expirada_e_removida(monkeypatch):
    estado = {
        "autenticado": True,
        "auth_user": "usuario",
        "auth_expira_em": time.time() - 1,
    }
    monkeypatch.setattr(auth.st, "session_state", estado)
    assert auth.esta_autenticado() is False
    assert "autenticado" not in estado
