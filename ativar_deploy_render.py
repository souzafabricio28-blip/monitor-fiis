"""Publica o workflow de deploy e dispara o Render uma vez.

Lê GH_TOKEN e RENDER_DEPLOY_HOOK do .env (nunca imprime valores).
Uso: python ativar_deploy_render.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
REPO = "souzafabricio28-blip/monitor-fiis"
BRANCH = "master"
WORKFLOW_PATH = ".github/workflows/deploy-render.yml"
SITE = "https://monitor-fiis-6dk7.onrender.com"


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
    for chave in ("GH_TOKEN", "RENDER_DEPLOY_HOOK", "RENDER_API_KEY"):
        if os.environ.get(chave):
            dados[chave] = os.environ[chave].strip()
    return dados


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _publicar_workflow(token: str, conteudo: str) -> None:
    api = f"https://api.github.com/repos/{REPO}/contents/{WORKFLOW_PATH}"
    resp = requests.get(api, headers=_headers(token), params={"ref": BRANCH}, timeout=30)
    sha = None
    if resp.status_code == 200:
        sha = resp.json().get("sha")
    elif resp.status_code != 404:
        resp.raise_for_status()

    corpo = {
        "message": "Adicionar deploy automatico no Render via Actions.",
        "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        corpo["sha"] = sha
        corpo["message"] = "Atualizar deploy automatico no Render via Actions."

    put = requests.put(api, headers=_headers(token), json=corpo, timeout=30)
    if put.status_code in (201, 200):
        print(f"GitHub: {WORKFLOW_PATH} publicado em {BRANCH}.")
        return
    print("GitHub HTTP", put.status_code, put.text[:400])
    put.raise_for_status()


def _gravar_secret(token: str, nome: str, valor: str) -> None:
    """Cria/atualiza secret do Actions (precisa PyNaCl)."""
    try:
        from nacl import encoding, public
    except ImportError:
        print(
            "Aviso: pacote pynacl ausente — nao deu para gravar o secret no GitHub.\n"
            f"Crie manualmente: Settings → Secrets → Actions → {nome}"
        )
        return

    key_resp = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers=_headers(token),
        timeout=30,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()
    public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(public_key).encrypt(valor.encode("utf-8"))
    encrypted = base64.b64encode(sealed).decode("utf-8")

    put = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{nome}",
        headers=_headers(token),
        json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
        timeout=30,
    )
    put.raise_for_status()
    print(f"GitHub: secret {nome} gravado.")


def _disparar_hook(hook: str) -> None:
    resp = requests.post(hook, timeout=30)
    resp.raise_for_status()
    print("Render: deploy disparado pelo hook.")


def main() -> int:
    env = _carregar_env()
    token = (env.get("GH_TOKEN") or "").strip()
    hook = (env.get("RENDER_DEPLOY_HOOK") or "").strip()

    if not token:
        print("Falta GH_TOKEN no .env.")
        return 1

    workflow = ROOT / WORKFLOW_PATH
    if not workflow.is_file():
        print(f"Arquivo ausente: {WORKFLOW_PATH}")
        return 1

    try:
        _publicar_workflow(token, workflow.read_text(encoding="utf-8"))
    except requests.HTTPError as exc:
        print("Falha ao publicar workflow:", exc.response.status_code, exc.response.text[:400])
        return 1

    if not hook:
        print()
        print("Falta RENDER_DEPLOY_HOOK no .env — o workflow ja esta no GitHub,")
        print("mas o Actions so dispara o Render depois deste secret.")
        print()
        print("1. Render → monitor-fiis → Settings → Deploy Hook → Copy")
        print("2. Cole no .env: RENDER_DEPLOY_HOOK=https://...")
        print("3. Rode de novo: python ativar_deploy_render.py")
        print("   (ou grave o mesmo valor em GitHub Secrets → RENDER_DEPLOY_HOOK)")
        return 2

    try:
        _gravar_secret(token, "RENDER_DEPLOY_HOOK", hook)
    except requests.HTTPError as exc:
        print(
            "Nao deu para gravar secret no GitHub:",
            exc.response.status_code,
            exc.response.text[:300],
        )
        print("Grave manualmente RENDER_DEPLOY_HOOK em Settings → Secrets → Actions.")

    try:
        _disparar_hook(hook)
    except requests.HTTPError as exc:
        print("Render HTTP", exc.response.status_code, exc.response.text[:400])
        return 1

    print(f"Site: {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
