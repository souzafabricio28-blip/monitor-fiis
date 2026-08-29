"""
Prepara deploy no Render e migra dados locais para o Neon.

Uso: python configurar_render.py
"""

from __future__ import annotations

import getpass
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
RENDER_URL = "https://dashboard.render.com"
SERVICE_URL = "https://monitor-fiis-6dk7.onrender.com"


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


def _atualizar_env(chave: str, valor: str) -> None:
    env = _ler_env()
    env[chave] = valor
    linhas: list[str] = []
    if ENV_PATH.exists():
        for linha in ENV_PATH.read_text(encoding="utf-8").splitlines():
            s = linha.strip()
            if s and not s.startswith("#") and "=" in s:
                k = s.split("=", 1)[0].strip()
                if k == chave:
                    continue
            linhas.append(linha)
    linhas.append(f"{chave}={valor}")
    ENV_PATH.write_text("\n".join(linhas).rstrip() + "\n", encoding="utf-8")


def main():
    print("=" * 55)
    print("  Monitor de FIIs — publicar no Render")
    print("=" * 55)
    print()
    print(f"URL publica: {SERVICE_URL}")
    print()

    env = _ler_env()
    usuario = env.get("AUTH_USER", "Fabricio")
    senha = env.get("AUTH_PASSWORD", "")

    print("1) Abra o painel do Render (login com GitHub)")
    webbrowser.open(RENDER_URL)
    print(f"   {RENDER_URL}")
    print()
    print("2) Abra o servico 'monitor-fiis' (ou crie Web Service)")
    print("   Repo: souzafabricio28-blip/monitor-fiis")
    print("   Branch: master")
    print()
    print("3) Em Environment, adicione estas variaveis:")
    print(f"   AUTH_USER = {usuario}")
    print(f"   AUTH_PASSWORD = {senha or '(sua senha principal, 12+ caracteres)'}")
    print("   AUTH_PASSWORD_ALT = (opcional)")
    print("   APP_ENV = production")
    print("   DATABASE_URL = (connection string do Neon)")
    print()
    print("   Opcional (recuperacao por e-mail):")
    print("   SMTP_USER, SMTP_PASSWORD, RECOVERY_EMAIL")
    print()
    print("4) Manual Deploy -> Deploy latest commit")
    print()

    db_url = env.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        print("-" * 55)
        print("NEON — connection string (postgresql://...)")
        print("Abra: https://console.neon.tech")
        db_url = getpass.getpass("Cole DATABASE_URL aqui (nao aparece): ").strip()
        if db_url.startswith("postgresql"):
            _atualizar_env("DATABASE_URL", db_url)
            print("DATABASE_URL salva no .env")
        else:
            print("DATABASE_URL nao informada — pule a migracao por enquanto.")

    if db_url.startswith("postgresql"):
        print()
        print("Migrando carteira local (fii_data.db) para o Neon...")
        env_run = __import__("os").environ.copy()
        env_run["DATABASE_URL"] = db_url
        env_run["SQLITE_PATH"] = "fii_data.db"
        proc = subprocess.run(
            [sys.executable, "migrate_db.py"],
            cwd=ROOT,
            env=env_run,
        )
        if proc.returncode == 0:
            print("Migracao concluida.")
        else:
            print("Migracao falhou — verifique DATABASE_URL e tente de novo.")

    print()
    print("Quando o deploy terminar, acesse:")
    print(f"  {SERVICE_URL}")
    print(f"  Login: {usuario}")
    print()
    input("Pressione Enter para fechar...")


if __name__ == "__main__":
    main()
