import email_recovery


def test_recovery_habilitado(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    assert email_recovery.recovery_habilitado() is False
    monkeypatch.setenv("SMTP_USER", "a@b.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("RECOVERY_EMAIL", "a@b.com")
    assert email_recovery.recovery_habilitado() is True


def test_email_autorizado(monkeypatch):
    monkeypatch.setenv("RECOVERY_EMAIL", "Fabricio@Email.com")
    assert email_recovery.email_autorizado("fabricio@email.com") is True
    assert email_recovery.email_autorizado("outro@email.com") is False


def test_enviar_credenciais_sem_config(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    try:
        email_recovery.enviar_credenciais("a@b.com", "u", "p")
        assert False, "deveria falhar"
    except email_recovery.EmailRecoveryError:
        pass
