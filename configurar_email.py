"""
Configura recuperação de senha por e-mail no .env local.
Uso: python configurar_email.py
"""

from __future__ import annotations

import getpass
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"

CHAVES_SMTP = {
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "",
    "SMTP_PASSWORD": "",
    "RECOVERY_EMAIL": "",
}


def _ler_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    dados: dict[str, str] = {}
    for linha in ENV_PATH.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        dados[chave.strip()] = valor.strip()
    return dados


def _gravar_env(atual: dict[str, str], smtp: dict[str, str]) -> None:
    linhas: list[str] = []
    chaves_smtp = set(CHAVES_SMTP) | set(smtp)
    vistos: set[str] = set()

    if ENV_PATH.exists():
        for linha in ENV_PATH.read_text(encoding="utf-8").splitlines():
            bruta = linha
            linha_strip = linha.strip()
            if linha_strip and not linha_strip.startswith("#") and "=" in linha_strip:
                chave = linha_strip.split("=", 1)[0].strip()
                if chave in chaves_smtp:
                    continue
                vistos.add(chave)
            linhas.append(bruta)

    merged = {**atual, **smtp}
    for chave in sorted(chaves_smtp):
        if chave in merged and merged[chave]:
            vistos.add(chave)

    outras = [f"{k}={merged[k]}" for k in merged if k not in vistos and k not in chaves_smtp]
    smtp_linhas = [
        "",
        "# Recuperacao de senha por e-mail",
        f"SMTP_SERVER={smtp.get('SMTP_SERVER', 'smtp.gmail.com')}",
        f"SMTP_PORT={smtp.get('SMTP_PORT', '587')}",
        f"SMTP_USER={smtp['SMTP_USER']}",
        f"SMTP_PASSWORD={smtp['SMTP_PASSWORD']}",
        f"RECOVERY_EMAIL={smtp['RECOVERY_EMAIL']}",
    ]

    corpo = "\n".join(linhas).rstrip()
    if corpo:
        corpo += "\n"
    corpo += "\n".join(smtp_linhas) + "\n"
    ENV_PATH.write_text(corpo, encoding="utf-8")


def _email_valido(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def main():
    print("=" * 50)
    print("  Monitor de FIIs — configurar e-mail de recuperacao")
    print("=" * 50)
    print()
    print("Voce precisa de uma SENHA DE APP do Gmail (nao e a senha normal).")
    print("Abra: https://myaccount.google.com/apppasswords")
    print()

    env_atual = _ler_env()
    sugestao = env_atual.get("SMTP_USER") or env_atual.get("RECOVERY_EMAIL") or ""

    email = input(f"Seu Gmail [{sugestao or 'ex: voce@gmail.com'}]: ").strip() or sugestao
    while not _email_valido(email):
        email = input("E-mail invalido. Digite novamente: ").strip()

    senha_app = getpass.getpass("Senha de app do Gmail (nao aparece na tela): ").strip()
    while len(senha_app) < 8:
        senha_app = getpass.getpass("Senha muito curta. Cole a senha de app: ").strip()

    smtp = {
        "SMTP_SERVER": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": email,
        "SMTP_PASSWORD": senha_app.replace(" ", ""),
        "RECOVERY_EMAIL": email,
    }
    _gravar_env(env_atual, smtp)

    print()
    print(f"Arquivo atualizado: {ENV_PATH}")
    print(f"E-mail de recuperacao: {email}")
    print()
    print("Proximo passo:")
    print("  1. Reinicie o Monitor de FIIs (feche e abra de novo)")
    print("  2. Na tela de login, clique em 'Esqueci minha senha'")
    print()
    input("Pressione Enter para fechar...")


if __name__ == "__main__":
    main()
