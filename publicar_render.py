"""
Publica no Render: copia variaveis do .env local e dispara deploy.

Uso:
  1. Gere API Key em https://dashboard.render.com/u/settings#api-keys
  2. Adicione no .env: RENDER_API_KEY=rnd_...
  3. python publicar_render.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
SERVICE_NAME = "monitor-fiis"
API_BASE = "https://api.render.com/v1"

# Variaveis do .env local que devem ir para o Render
CHAVES_RENDER = (
    "APP_ENV",
    "AUTH_USER",
    "AUTH_PASSWORD",
    "AUTH_PASSWORD_ALT",
    "DATABASE_URL",
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "RECOVERY_EMAIL",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
)


def _carregar_env() -> dict[str, str]:
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH)
    except ImportError:
        pass
    dados: dict[str, str] = {}
    if ENV_PATH.exists():
        for linha in ENV_PATH.read_text(encoding="utf-8").splitlines():
            s = linha.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            chave, valor = s.split("=", 1)
            dados[chave.strip()] = valor.strip()
    for chave in CHAVES_RENDER:
        if os.environ.get(chave):
            dados[chave] = os.environ[chave].strip()
    return dados


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _buscar_servico(api_key: str) -> str:
    cursor = None
    while True:
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            f"{API_BASE}/services",
            headers=_headers(api_key),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        for item in payload:
            svc = item.get("service") or item
            nome = (svc.get("name") or "").lower()
            if nome == SERVICE_NAME:
                return svc["id"]
        cursor = None
        if payload and isinstance(payload[-1], dict):
            cursor = payload[-1].get("cursor")
        if not cursor:
            break
    raise RuntimeError(
        f"Servico '{SERVICE_NAME}' nao encontrado no Render. "
        "Crie o Web Service apontando para o repo monitor-fiis."
    )


def _listar_env(api_key: str, service_id: str) -> dict[str, str]:
    resp = requests.get(
        f"{API_BASE}/services/{service_id}/env-vars",
        headers=_headers(api_key),
        timeout=30,
    )
    resp.raise_for_status()
    atual: dict[str, str] = {}
    for item in resp.json():
        ev = item.get("envVar") or item
        if ev.get("key"):
            atual[ev["key"]] = ev.get("value") or ""
    return atual


def _aplicar_env(api_key: str, service_id: str, env: dict[str, str]) -> None:
    corpo = [{"key": k, "value": v} for k, v in sorted(env.items()) if v]
    resp = requests.put(
        f"{API_BASE}/services/{service_id}/env-vars",
        headers=_headers(api_key),
        json=corpo,
        timeout=60,
    )
    resp.raise_for_status()


def _disparar_deploy(api_key: str, service_id: str) -> str:
    resp = requests.post(
        f"{API_BASE}/services/{service_id}/deploys",
        headers=_headers(api_key),
        json={"clearCache": "do_not_clear"},
        timeout=30,
    )
    resp.raise_for_status()
    deploy = resp.json().get("deploy") or resp.json()
    return deploy.get("id") or "ok"


def _aguardar_deploy(api_key: str, service_id: str, deploy_id: str, timeout: int = 600) -> str:
    inicio = time.time()
    while time.time() - inicio < timeout:
        resp = requests.get(
            f"{API_BASE}/services/{service_id}/deploys/{deploy_id}",
            headers=_headers(api_key),
            timeout=30,
        )
        resp.raise_for_status()
        deploy = resp.json().get("deploy") or resp.json()
        status = deploy.get("status") or "unknown"
        print(f"  Deploy: {status}")
        if status == "live":
            return status
        if status in {"build_failed", "update_failed", "canceled", "pre_deploy_failed"}:
            raise RuntimeError(f"Deploy falhou: {status}")
        time.sleep(15)
    raise TimeoutError("Deploy demorou demais.")


def main() -> int:
    print("=" * 55)
    print("  Publicar Monitor de FIIs no Render")
    print("=" * 55)

    local = _carregar_env()
    api_key = local.get("RENDER_API_KEY") or os.environ.get("RENDER_API_KEY", "").strip()
    if not api_key:
        print()
        print("Falta RENDER_API_KEY no .env")
        print("1. Abra: https://dashboard.render.com/u/settings#api-keys")
        print("2. Create API Key")
        print("3. Adicione no .env: RENDER_API_KEY=rnd_sua_chave")
        print("4. Rode de novo: python publicar_render.py")
        return 1

    try:
        print("\nBuscando servico monitor-fiis...")
        service_id = _buscar_servico(api_key)
        print(f"  ID: {service_id}")

        print("Lendo variaveis atuais no Render...")
        remoto = _listar_env(api_key, service_id)

        print("Mesclando com .env local...")
        for chave in CHAVES_RENDER:
            valor = local.get(chave, "").strip()
            if valor:
                remoto[chave] = valor

        # Garantias minimas
        remoto.setdefault("APP_ENV", "production")
        remoto.setdefault("AUTH_USER", local.get("AUTH_USER", "Fabricio"))
        if not remoto.get("AUTH_PASSWORD") and local.get("AUTH_PASSWORD"):
            remoto["AUTH_PASSWORD"] = local["AUTH_PASSWORD"]
        if not remoto.get("AUTH_PASSWORD_ALT") and local.get("AUTH_PASSWORD_ALT"):
            remoto["AUTH_PASSWORD_ALT"] = local["AUTH_PASSWORD_ALT"]

        # Render injeta automaticamente; nao remover
        remoto.setdefault("PYTHON_VERSION", "3.11.0")

        aplicadas = [k for k in CHAVES_RENDER if remoto.get(k)]
        print(f"  Variaveis a sincronizar: {', '.join(aplicadas) or '(nenhuma)'}")

        if not remoto.get("AUTH_PASSWORD"):
            print("\nAVISO: AUTH_PASSWORD vazio — login nao vai funcionar no Render.")

        print("\nEnviando variaveis para o Render...")
        _aplicar_env(api_key, service_id, remoto)

        print("Disparando deploy...")
        deploy_id = _disparar_deploy(api_key, service_id)
        print(f"  Deploy ID: {deploy_id}")

        if deploy_id != "ok":
            print("\nAguardando deploy (pode levar alguns minutos)...")
            _aguardar_deploy(api_key, service_id, deploy_id)

        print("\nPronto!")
        print("  URL: https://monitor-fiis.onrender.com")
        print(f"  Login: {remoto.get('AUTH_USER', 'Fabricio')}")
        print("  Senhas: forte + 030990")

        if not local.get("DATABASE_URL"):
            print("\nNOTA: DATABASE_URL nao esta no .env.")
            print("  O Render usara SQLite vazio (carteira local nao sobe automaticamente).")
            print("  Para mesma carteira: configure Neon e rode python migrate_db.py")

        return 0
    except requests.HTTPError as exc:
        print(f"\nErro HTTP Render: {exc.response.status_code}")
        print(exc.response.text[:500])
        return 1
    except Exception as exc:
        print(f"\nErro: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
