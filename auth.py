"""
Autenticação do dashboard (dados sensíveis de negócio).

Credenciais somente por variáveis de ambiente / Streamlit secrets:
  AUTH_USER      (opcional, padrão: admin)
  AUTH_PASSWORD  (obrigatório em produção com Neon/Postgres)
  AUTH_PASSWORD_ALT  (opcional — segunda senha de acesso)
"""

from __future__ import annotations

import hmac
import os
import time
from typing import Optional

import streamlit as st

from email_recovery import (
    EmailRecoveryError,
    email_autorizado,
    enviar_credenciais,
    recovery_habilitado,
)

MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 120
SESSAO_SEGUNDOS = 8 * 60 * 60
SENHA_MINIMA = 12
RECUPERACAO_COOLDOWN = 300


def _coluna_central():
    """Coluna central sem CSS. Esconder a sidebar no DOM derruba o React."""
    st.sidebar.caption("Monitor de FIIs · acesso restrito")
    _esq, centro, _dir = st.columns([1, 1.3, 1])
    return centro


def _render_recuperacao_senha(user_esperado: str, senhas_esperadas: list[str], agora: float) -> None:
    with _coluna_central():
        with st.container(border=True):
            st.badge("Recuperar acesso", icon=":material/mail:", color="primary")
            st.header("Recuperar senha")
            st.caption("Enviaremos usuário e senha para o e-mail cadastrado.")

            ultimo_envio = float(st.session_state.get("recovery_ultimo_envio") or 0)
            if ultimo_envio and agora - ultimo_envio < RECUPERACAO_COOLDOWN:
                restante = int(RECUPERACAO_COOLDOWN - (agora - ultimo_envio))
                st.info(f"Aguarde {restante}s para solicitar novamente.")

            with st.form("recovery_form", clear_on_submit=True):
                email = st.text_input(
                    "Seu e-mail cadastrado",
                    autocomplete="email",
                    placeholder="seu@email.com",
                )
                enviar = st.form_submit_button("Enviar senha por e-mail", type="primary")

            if enviar:
                if ultimo_envio and agora - ultimo_envio < RECUPERACAO_COOLDOWN:
                    st.warning("Aguarde antes de solicitar outro e-mail.")
                elif email_autorizado(email):
                    try:
                        enviar_credenciais(
                            email.strip(),
                            user_esperado,
                            senhas_esperadas[0] if senhas_esperadas else "",
                        )
                        st.session_state["recovery_ultimo_envio"] = agora
                        st.success("E-mail enviado! Verifique sua caixa de entrada e spam.")
                    except EmailRecoveryError as exc:
                        st.error(str(exc))
                else:
                    st.session_state["recovery_ultimo_envio"] = agora
                    st.success(
                        "Se o e-mail estiver cadastrado, você receberá as credenciais em instantes."
                    )

            if st.button("Voltar ao login", key="voltar_login"):
                st.session_state.pop("mostrar_recuperacao_senha", None)
                st.rerun()


def _render_tela_login(user_esperado: str, senhas_esperadas: list[str], agora: float) -> None:
    if st.session_state.get("mostrar_recuperacao_senha"):
        _render_recuperacao_senha(user_esperado, senhas_esperadas, agora)
        return

    with _coluna_central():
        with st.container(border=True):
            st.badge("Acesso restrito", icon=":material/lock:", color="primary")
            st.header("Monitor de FIIs")
            st.caption("Entre para ver a carteira e os critérios do gestor.")

            with st.form("login_form", clear_on_submit=False):
                usuario = st.text_input("Usuário", autocomplete="username", placeholder="Seu usuário")
                senha = st.text_input(
                    "Senha",
                    type="password",
                    autocomplete="current-password",
                    placeholder="••••••••",
                )
                entrar = st.form_submit_button("Entrar", type="primary")

            if entrar:
                falhas = int(st.session_state.get("auth_falhas") or 0)
                if _usuario_ok(usuario, user_esperado) and _senha_ok(senha, senhas_esperadas):
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

            if recovery_habilitado():
                if st.button("Esqueci minha senha", key="abrir_recuperacao"):
                    st.session_state["mostrar_recuperacao_senha"] = True
                    st.rerun()


def _credenciais() -> tuple[str, list[str]]:
    user = (
        os.environ.get("AUTH_USER")
        or _secret("AUTH_USER")
        or "admin"
    ).strip()
    return user, _senhas_esperadas()


def _senhas_esperadas() -> list[str]:
    senhas: list[str] = []
    for chave in ("AUTH_PASSWORD", "AUTH_PASSWORD_ALT"):
        valor = os.environ.get(chave) or _secret(chave)
        if not valor:
            continue
        senha = str(valor).strip()
        if senha and senha not in senhas:
            senhas.append(senha)
    return senhas


def _secret(chave: str) -> Optional[str]:
    try:
        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return None
        valor = secrets.get(chave) if hasattr(secrets, "get") else None
        if valor is None:
            return None
        texto = str(valor).strip()
        return texto or None
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
        or os.environ.get("RENDER_EXTERNAL_URL")
    )


def _senha_ok(informada: str, esperadas: str | list[str]) -> bool:
    if isinstance(esperadas, str):
        candidatas = [esperadas]
    else:
        candidatas = list(esperadas)
    informada_b = informada.encode("utf-8")
    return any(
        hmac.compare_digest(informada_b, esperada.encode("utf-8"))
        for esperada in candidatas
        if esperada
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
    user_esperado, senhas_esperadas = _credenciais()

    if auth_obrigatorio() and senhas_esperadas and not _credenciais_producao_validas(
        user_esperado, senhas_esperadas[0]
    ):
        st.error(
            "Acesso bloqueado: em produção, defina AUTH_USER personalizado e "
            f"AUTH_PASSWORD com pelo menos {SENHA_MINIMA} caracteres."
        )
        st.stop()
        return False

    if not senhas_esperadas:
        if auth_obrigatorio():
            st.sidebar.caption("Monitor de FIIs · acesso restrito")
            st.error(
                "Login indisponível: configure AUTH_PASSWORD no Render "
                "(Environment → Add Environment Variable)."
            )
            st.info(
                "No Render → monitor-fiis → **Environment**, adicione:\n\n"
                "- `AUTH_USER` = usuário personalizado (não use admin)\n"
                "- `AUTH_PASSWORD` = senha forte com 12 caracteres ou mais\n\n"
                "Depois: **Manual Deploy** → Deploy latest commit."
            )
            st.stop()
            return False
        # Local sem senha: permite desenvolvimento, mas avisa
        st.sidebar.caption("Modo local sem senha — não use em produção.")
        return True

    if esta_autenticado():
        return True

    bloqueio = float(st.session_state.get("auth_bloqueio_ate") or 0)
    agora = time.time()
    if bloqueio > agora:
        restante = int(bloqueio - agora)
        st.sidebar.caption("Monitor de FIIs · acesso restrito")
        st.warning(f"Muitas tentativas. Aguarde {restante}s.")
        st.stop()
        return False

    _render_tela_login(user_esperado, senhas_esperadas, agora)

    st.stop()
    return False
