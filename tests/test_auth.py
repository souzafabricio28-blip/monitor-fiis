import time

import auth


def test_producao_exige_autenticacao(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert auth.auth_obrigatorio() is True


def test_comparacao_de_senha():
    assert auth._senha_ok("senha-complexa", "senha-complexa")
    assert auth._senha_ok("030990", ["forte-123456", "030990"])
    assert not auth._senha_ok("errada", "senha-complexa")
    assert auth._credenciais_producao_validas("usuario", "senha-complexa")
    assert not auth._credenciais_producao_validas("admin", "senha-complexa")
    assert not auth._credenciais_producao_validas("usuario", "curta")


def test_senhas_alternativas(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "senha-principal-forte")
    monkeypatch.setenv("AUTH_PASSWORD_ALT", "030990")
    user, senhas = auth._credenciais()
    assert user == "admin"
    assert senhas == ["senha-principal-forte", "030990"]


def test_producao_sem_senha_bloqueia_sem_formulario(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD_ALT", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "_secret", lambda chave: None)
    avisos = []
    monkeypatch.setattr(auth.st, "error", lambda msg: avisos.append(msg))
    monkeypatch.setattr(auth.st, "info", lambda msg: avisos.append(msg))
    monkeypatch.setattr(auth.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(auth.st, "stop", lambda: None)

    class _Sidebar:
        def caption(self, *a, **k):
            return None

    monkeypatch.setattr(auth.st, "sidebar", _Sidebar())
    assert auth.exigir_login() is False
    assert any("AUTH_PASSWORD" in str(msg) for msg in avisos)
    assert not any("030990" in str(msg) for msg in avisos)


def test_sessao_expirada_e_removida(monkeypatch):
    estado = {
        "autenticado": True,
        "auth_user": "usuario",
        "auth_expira_em": time.time() - 1,
    }
    monkeypatch.setattr(auth.st, "session_state", estado)
    assert auth.esta_autenticado() is False
    assert "autenticado" not in estado


def test_login_nao_injeta_css_nem_esconde_sidebar():
    import inspect

    fonte = inspect.getsource(auth)
    assert "unsafe_allow_html" not in fonte
    assert "display: none" not in fonte
    assert "stMainBlockContainer" not in fonte
