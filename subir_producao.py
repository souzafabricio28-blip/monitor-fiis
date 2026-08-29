"""Sobe o app para GitHub (master) e dispara o Render.

Uso: python subir_producao.py
Lê GH_TOKEN, RENDER_DEPLOY_HOOK e/ou RENDER_API_KEY do .env (nunca no Git).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
GITHUB_REPO = "souzafabricio28-blip/monitor-fiis"
GITHUB_BRANCH = "master"
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


def _caminho_proibido(rel: str) -> bool:
    partes = Path(rel).parts
    nome = Path(rel).name
    return nome == ".env" or ".env" in partes


def arquivos_rastreados(raiz: Path) -> list[str]:
    """Só arquivos versionados — .env e banco local ficam de fora."""
    bruto = subprocess.check_output(
        ["git", "-C", str(raiz), "ls-files"],
        text=True,
    )
    return [
        linha.strip()
        for linha in bruto.splitlines()
        if linha.strip() and not _caminho_proibido(linha.strip())
    ]


def arquivos_para_github(raiz: Path) -> list[str]:
    """PAT classic sem escopo workflow não pode criar/alterar Actions."""
    return [
        c
        for c in arquivos_rastreados(raiz)
        if not c.startswith(".github/workflows/")
    ]


def copiar_arvore(origem: Path, destino: Path, caminhos: list[str]) -> None:
    for rel in caminhos:
        if _caminho_proibido(rel):
            continue
        src = origem / rel
        if not src.is_file():
            continue
        dst = destino / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def garantir_commit_local(raiz: Path) -> None:
    status = subprocess.check_output(
        ["git", "-C", str(raiz), "status", "--porcelain"],
        text=True,
    )
    if status.strip():
        raise RuntimeError(
            "Há alterações sem commit. Faça git add/commit antes de python subir_producao.py."
        )


def publicar_github(token: str, mensagem: str) -> str:
    destino = Path(tempfile.mkdtemp(prefix="monitor-fiis-gh-"))
    autenticado = f"https://x-access-token:{token}@github.com/{GITHUB_REPO}.git"
    publico = f"https://github.com/{GITHUB_REPO}.git"
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                GITHUB_BRANCH,
                "--single-branch",
                autenticado,
                str(destino),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(destino), "remote", "set-url", "origin", publico],
            check=True,
        )
        copiar_arvore(ROOT, destino, arquivos_para_github(ROOT))
        subprocess.run(["git", "-C", str(destino), "add", "-A"], check=True)
        staged = subprocess.check_output(
            ["git", "-C", str(destino), "diff", "--cached", "--name-only"],
            text=True,
        )
        if any(_caminho_proibido(linha) for linha in staged.splitlines()):
            raise RuntimeError("Recusa: .env não pode ir para o GitHub.")
        if not staged.strip():
            sha = subprocess.check_output(
                ["git", "-C", str(destino), "rev-parse", "--short", "HEAD"],
                text=True,
            ).strip()
            print(f"GitHub {GITHUB_BRANCH} já está atualizado ({sha}).")
            return sha
        subprocess.run(
            ["git", "-C", str(destino), "config", "user.email", "cursoragent@cursor.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destino), "config", "user.name", "Cursor Agent"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destino), "commit", "-m", mensagem],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destino), "remote", "set-url", "origin", autenticado],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destino), "push", "origin", GITHUB_BRANCH],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destino), "remote", "set-url", "origin", publico],
            check=True,
        )
        sha = subprocess.check_output(
            ["git", "-C", str(destino), "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
        print(f"GitHub: push {sha} em {GITHUB_BRANCH}.")
        return sha
    finally:
        shutil.rmtree(destino, ignore_errors=True)


def disparar_render(env: dict[str, str]) -> None:
    hook = (env.get("RENDER_DEPLOY_HOOK") or "").strip()
    if hook:
        resp = requests.post(hook, timeout=30)
        resp.raise_for_status()
        print("Render: deploy disparado pelo hook.")
        return
    api_key = (env.get("RENDER_API_KEY") or "").strip()
    if api_key:
        from publicar_render import (
            _aguardar_deploy,
            _buscar_servico,
            _disparar_deploy,
        )

        service_id = _buscar_servico(api_key)
        deploy_id = _disparar_deploy(api_key, service_id)
        print(f"Render: deploy {deploy_id}")
        if deploy_id != "ok":
            _aguardar_deploy(api_key, service_id, deploy_id)
        return
    print(
        "GitHub atualizado, mas o Render não disparou: falta RENDER_DEPLOY_HOOK "
        "ou RENDER_API_KEY no .env.\n"
        "No Render: monitor-fiis → Settings → Deploy Hook → copiar URL para o .env."
    )


def main() -> int:
    env = _carregar_env()
    token = (env.get("GH_TOKEN") or "").strip()
    if not token:
        print("Falta GH_TOKEN no .env.")
        return 1
    mensagem = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Publicar Monitor de FIIs no ar."
    )
    try:
        garantir_commit_local(ROOT)
        publicar_github(token, mensagem)
        disparar_render(env)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc))
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        print("Git falhou:", err[:800])
        return 1
    except requests.HTTPError as exc:
        print("Render HTTP", exc.response.status_code, exc.response.text[:400])
        return 1
    print(f"Site: {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
