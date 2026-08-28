"""
Gera .env local e instruções de acesso remoto (Render + Neon).
Uso: python configurar_acesso.py
"""

from __future__ import annotations

import secrets
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
ACESSO_PATH = ROOT / "ACESSO_MONITOR.txt"


def gerar_senha(tamanho: int = 20) -> str:
    chars = string.ascii_letters + string.digits + "!@#%"
    return "".join(secrets.choice(chars) for _ in range(tamanho))


def main():
    usuario = "souza_fiis"
    senha = gerar_senha()
    env = f"""APP_ENV=production
AUTH_USER={usuario}
AUTH_PASSWORD={senha}

# Cole a URL do Neon abaixo para sincronizar dados na nuvem
# DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require
SQLITE_PATH=fii_data.db
"""
    ENV_PATH.write_text(env, encoding="utf-8")
    ACESSO_PATH.write_text(
        f"""MONITOR DE FIIs — CREDENCIAIS
Usuário: {usuario}
Senha:   {senha}

Configure os mesmos valores no Render (Environment Variables).
""",
        encoding="utf-8",
    )
    print(f"Arquivo criado: {ENV_PATH}")
    print(f"Instruções: {ACESSO_PATH}")
    print(f"Usuário: {usuario}")
    print(f"Senha: {senha}")


if __name__ == "__main__":
    main()
