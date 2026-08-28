"""
Envio de credenciais por e-mail (recuperação de senha do dashboard).

Variáveis de ambiente:
  SMTP_SERVER      (padrão: smtp.gmail.com)
  SMTP_PORT        (padrão: 587)
  SMTP_USER        e-mail remetente (login SMTP)
  SMTP_PASSWORD    senha de app do provedor
  RECOVERY_EMAIL   e-mail cadastrado que pode receber a senha
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailRecoveryError(Exception):
    pass


def _env(chave: str, padrao: str = "") -> str:
    return (os.environ.get(chave) or padrao).strip()


def recovery_habilitado() -> bool:
    return bool(_env("SMTP_USER") and _env("SMTP_PASSWORD") and _env("RECOVERY_EMAIL"))


def email_autorizado(email_informado: str) -> bool:
    cadastrado = _env("RECOVERY_EMAIL").lower()
    informado = email_informado.strip().lower()
    return bool(cadastrado and informado and informado == cadastrado)


def enviar_credenciais(email_destino: str, usuario: str, senha: str) -> None:
    if not recovery_habilitado():
        raise EmailRecoveryError("Recuperação por e-mail não configurada.")

    servidor = _env("SMTP_SERVER", "smtp.gmail.com")
    porta = int(_env("SMTP_PORT", "587") or "587")
    remetente = _env("SMTP_USER")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Monitor de FIIs — suas credenciais de acesso"
    msg["From"] = remetente
    msg["To"] = email_destino

    texto = f"""Monitor de FIIs — recuperação de senha

Usuário: {usuario}
Senha: {senha}

Se você não solicitou este e-mail, ignore a mensagem e troque a senha do painel.
"""
    html = f"""<html><body style="font-family:sans-serif;color:#111;">
<h2 style="color:#667eea;">Monitor de FIIs</h2>
<p>Recuperação de senha solicitada:</p>
<p><strong>Usuário:</strong> {usuario}<br>
<strong>Senha:</strong> {senha}</p>
<p style="color:#666;font-size:0.9em;">Se você não solicitou, ignore este e-mail.</p>
</body></html>"""

    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(servidor, porta, timeout=30) as server:
            server.starttls()
            server.login(remetente, _env("SMTP_PASSWORD"))
            server.sendmail(remetente, [email_destino], msg.as_string())
    except Exception as exc:
        raise EmailRecoveryError(f"Falha ao enviar e-mail: {exc}") from exc
