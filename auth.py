"""
Autenticação do dashboard (dados sensíveis de negócio).

Credenciais somente por variáveis de ambiente / Streamlit secrets:
  AUTH_USER      (opcional, padrão: admin)
  AUTH_PASSWORD  (obrigatório em produção com Neon/Postgres)
"""

from __future__ import annotations

import hmac
import os
import time
from typing import Optional

import streamlit as st

MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 120
SESSAO_SEGUNDOS = 8 * 60 * 60
SENHA_MINIMA = 12


def _credenciais() -> tuple[str, Optional[str]]:
    user = (
        os.environ.get("AUTH_USER")
        or _secret("AUTH_USER")
        or "admin"
    ).strip()
    password = os.environ.get("AUTH_PASSWORD") or _secret("AUTH_PASSWORD")
    if password:
        password = str(password).strip()
    return user, password or None


def _secret(chave: str) -> Optional[str]:
    try:
        return st.secrets.get(chave)  # type: ignore[attr-defined]
    except Exception:
        return None


def auth_obrigatorio() -> bool:
    """Em produção ou com Postgres/Neon, autenticação é obrigatória."""
    db_url = os.environ.get("DATABASE_URL") or ""
    ambiente = (os.environ.get("APP_ENV") or "").lower()
    return bool(
        db_url.startswith(("postgresql://", "postgres://"))
        or ambiente == "production"
        or os.environ.get("RENDER")
        or os.environ.get("RENDER_SERVICE_ID")
    )


def _senha_ok(informada: str, esperada: str) -> bool:
    return hmac.compare_digest(
        informada.encode("utf-8"),
        esperada.encode("utf-8"),
    )


def _usuario_ok(informado: str, esperado: str) -> bool:
    return hmac.compare_digest(informado.strip(), esperado.strip())


def _credenciais_producao_validas(usuario: str, senha: str) -> bool:
    return usuario.lower() != "admin" and len(senha) >= SENHA_MINIMA


def esta_autenticado() -> bool:
    if not st.session_state.get("autenticado"):
        return False
    expira_em = float(st.session_state.get("auth_expira_em") or 0)
    if expira_em <= time.time():
        logout()
        return False
    return True


def logout():
    for chave in (
        "autenticado",
        "auth_user",
        "auth_expira_em",
        "auth_falhas",
        "auth_bloqueio_ate",
    ):
        st.session_state.pop(chave, None)


def exigir_login() -> bool:
    """
    Mostra tela de login se necessário.
    Retorna True se o usuário pode acessar o app.
    """
    user_esperado, senha_esperada = _credenciais()

    if not senha_esperada:
        if auth_obrigatorio():
            st.error(
                "Acesso bloqueado: defina AUTH_PASSWORD no Render "
                "(Environment Variables). Sem isso o painel não abre em produção."
            )
            st.info(
                "No Render → seu serviço → Environment → Add:\n\n"
                "- `AUTH_USER` = seu usuário\n"
                "- `AUTH_PASSWORD` = senha forte"
            )
            st.stop()
            return False
        # Local sem senha: permite desenvolvimento, mas avisa
        st.sidebar.warning("Dev local sem AUTH_PASSWORD — não use assim em produção.")
        return True

    if auth_obrigatorio() and not _credenciais_producao_validas(
        user_esperado, senha_esperada
    ):
        st.error(
            "Acesso bloqueado: em produção, defina AUTH_USER personalizado e "
            f"AUTH_PASSWORD com pelo menos {SENHA_MINIMA} caracteres."
        )
        st.stop()
        return False

    if esta_autenticado():
        return True

    bloqueio = float(st.session_state.get("auth_bloqueio_ate") or 0)
    agora = time.time()
    if bloqueio > agora:
        restante = int(bloqueio - agora)
        st.warning(f"Muitas tentativas. Aguarde {restante}s.")
        st.stop()
        return False

    st.markdown("## Acesso restrito")
    st.caption("Painel com dados de negócio — login obrigatório.")

    with st.form("login_form", clear_on_submit=False):
        usuario = st.text_input("Usuário", autocomplete="username")
        senha = st.text_input("Senha", type="password", autocomplete="current-password")
        entrar = st.form_submit_button("Entrar", type="primary", width="stretch")

    if entrar:
        falhas = int(st.session_state.get("auth_falhas") or 0)
        if _usuario_ok(usuario, user_esperado) and _senha_ok(senha, senha_esperada):
            st.session_state["autenticado"] = True
            st.session_state["auth_user"] = user_esperado
            st.session_state["auth_expira_em"] = agora + SESSAO_SEGUNDOS
            st.session_state["auth_falhas"] = 0
            st.session_state.pop("auth_bloqueio_ate", None)
            st.rerun()
        else:
            falhas += 1
            st.session_state["auth_falhas"] = falhas
            if falhas >= MAX_TENTATIVAS:
                st.session_state["auth_bloqueio_ate"] = agora + BLOQUEIO_SEGUNDOS
                st.session_state["auth_falhas"] = 0
                st.error("Acesso temporariamente bloqueado.")
            else:
                st.error(f"Usuário ou senha inválidos ({falhas}/{MAX_TENTATIVAS}).")

    st.stop()
    return False
