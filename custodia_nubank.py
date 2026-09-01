"""Importação do Extrato de Custódia Nubank (PDF) → carteira."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

# Fallback / testes — extrato 01/09/2026
CUSTODIA_NUBANK_20260901: dict[str, tuple[int, float]] = {
    "KNSC11": (10, 9.00),
    "VGHF11": (10, 5.32),
    "MXRF11": (48, 9.21),
    "CPTS11": (10, 7.40),
    "MANA11": (10, 9.05),
    "BTCI11": (10, 9.11),
    "VRTM11": (10, 6.44),
    "SNEL11": (10, 8.26),
    "GARE11": (10, 8.36),
    "BBAS3": (1, 21.25),
    "KLBN4": (1, 3.77),
    "PETR4": (4, 46.87),
    "ITSA4": (2, 13.16),
}

REALOCAR: dict[str, str] = {
    "ITSA3": "ITSA4",
}

CHAVE_SYNC = "custodia_nubank_20260901"

_RE_CUSTODIA = re.compile(
    r"Cust[oó]dia\s+em:\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
# Ex.: Kinea Securities (KNSC11) 10,00 90,00
_RE_POSICAO = re.compile(
    r"\(([A-Z]{4}\d{1,2})\)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})",
)


def _br_para_float(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def _data_iso(br: str | None) -> str:
    if not br:
        return datetime.now().strftime("%Y-%m-%d")
    dia, mes, ano = br.split("/")
    return f"{ano}-{mes}-{dia}"


def extrair_texto_pdf(conteudo: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Pacote pypdf ausente. Instale com: pip install pypdf"
        ) from exc
    from io import BytesIO

    leitor = PdfReader(BytesIO(conteudo))
    partes: list[str] = []
    for pagina in leitor.pages:
        partes.append(pagina.extract_text() or "")
    return "\n".join(partes)


def parse_extrato_nubank_texto(texto: str) -> dict[str, Any]:
    """Lê o texto do Extrato de Custódia Nu Investimentos."""
    if not texto or not texto.strip():
        raise ValueError("PDF sem texto legível.")

    data_br = None
    m_data = _RE_CUSTODIA.search(texto)
    if m_data:
        data_br = m_data.group(1)

    posicoes: dict[str, dict[str, float | int | str]] = {}
    for m in _RE_POSICAO.finditer(texto):
        ticker = m.group(1).upper()
        quantidade = _br_para_float(m.group(2))
        saldo = _br_para_float(m.group(3))
        if quantidade <= 0:
            continue
        preco = round(saldo / quantidade, 4)
        posicoes[ticker] = {
            "quantidade": int(round(quantidade)),
            "saldo_bruto": round(saldo, 2),
            "preco_unitario": preco,
        }

    if not posicoes:
        raise ValueError(
            "Não encontrei posições no PDF. Use o Extrato de Custódia da Nu Investimentos."
        )

    return {
        "data_custodia": data_br,
        "data_iso": _data_iso(data_br),
        "posicoes": posicoes,
        "total_posicoes": len(posicoes),
    }


def parse_extrato_nubank_pdf(conteudo: bytes) -> dict[str, Any]:
    return parse_extrato_nubank_texto(extrair_texto_pdf(conteudo))


def comparar_com_carteira(
    db: Any, posicoes: dict[str, dict[str, float | int | str]]
) -> dict[str, Any]:
    """Compara extrato × carteira sem gravar."""
    carteira = db.obter_carteira()
    atuais: dict[str, dict[str, float | int]] = {}
    if carteira is not None and not carteira.empty:
        for _, row in carteira.iterrows():
            ticker = str(row["ticker"]).upper()
            atuais[ticker] = {
                "quantidade": int(row["quantidade"]),
                "preco_compra": float(row["preco_compra"]),
            }

    novos: list[str] = []
    atualizar: list[dict[str, Any]] = []
    iguais: list[str] = []
    for ticker, info in sorted(posicoes.items()):
        qtd = int(info["quantidade"])
        preco = float(info["preco_unitario"])
        if ticker not in atuais:
            # legado ITSA3 conta como base de ITSA4
            legado = None
            for origem, destino in REALOCAR.items():
                if destino == ticker and origem in atuais:
                    legado = origem
                    break
            if legado:
                atualizar.append(
                    {
                        "ticker": ticker,
                        "de_qtd": atuais[legado]["quantidade"],
                        "para_qtd": qtd,
                        "de_preco": atuais[legado]["preco_compra"],
                        "para_preco": preco,
                        "via": legado,
                    }
                )
            else:
                novos.append(ticker)
            continue
        atual = atuais[ticker]
        if atual["quantidade"] == qtd and abs(atual["preco_compra"] - preco) < 0.005:
            iguais.append(ticker)
        else:
            atualizar.append(
                {
                    "ticker": ticker,
                    "de_qtd": atual["quantidade"],
                    "para_qtd": qtd,
                    "de_preco": atual["preco_compra"],
                    "para_preco": preco,
                }
            )

    ausentes = sorted(
        t
        for t in atuais
        if t not in posicoes and REALOCAR.get(t) not in posicoes
    )
    return {
        "novos": novos,
        "atualizar": atualizar,
        "iguais": iguais,
        "ausentes_na_custodia": ausentes,
        "carteira_atual": atuais,
    }


def _definir_posicao_extrato(
    db: Any,
    ticker: str,
    quantidade: int,
    preco_unitario: float,
    *,
    data_iso: str,
    observacoes: str,
    idempotency_key: str,
) -> None:
    """Substitui a posição pelo saldo do extrato (qtd + valor unitário)."""
    carteira = db.obter_carteira()
    if carteira is not None and not carteira.empty:
        bate = carteira[carteira["ticker"].astype(str).str.upper() == ticker]
        if not bate.empty:
            db.remover_fii(ticker)
    db.registrar_movimentacao(
        ticker,
        "SALDO_INICIAL",
        int(quantidade),
        float(preco_unitario),
        data_movimentacao=data_iso,
        observacoes=observacoes,
        idempotency_key=idempotency_key,
    )


def aplicar_extrato_nubank(
    db: Any,
    parseado: dict[str, Any],
    *,
    remover_ausentes: bool = False,
    nome_arquivo: str = "",
) -> dict[str, Any]:
    """Aplica o extrato: inclui novos e atualiza quantidade + valor."""
    posicoes: dict[str, dict[str, float | int | str]] = parseado["posicoes"]
    data_iso = parseado.get("data_iso") or datetime.now().strftime("%Y-%m-%d")
    comparacao = comparar_com_carteira(db, posicoes)
    alteracoes: list[str] = []
    digest = hashlib.sha1(
        ("|".join(f"{t}:{posicoes[t]['quantidade']}" for t in sorted(posicoes))).encode()
    ).hexdigest()[:10]
    agora = datetime.now().strftime("%Y%m%d%H%M%S")
    chave = f"custodia_import_{data_iso}_{digest}_{agora}"

    # Remove legados (ITSA3) quando o extrato traz o destino (ITSA4)
    carteira = db.obter_carteira()
    atuais = set()
    if carteira is not None and not carteira.empty:
        atuais = {str(r["ticker"]).upper() for _, r in carteira.iterrows()}
    for origem, destino in REALOCAR.items():
        if origem in atuais and destino in posicoes:
            db.remover_fii(origem)
            alteracoes.append(f"removeu {origem} (substituído por {destino})")

    for ticker, info in sorted(posicoes.items()):
        qtd = int(info["quantidade"])
        preco = float(info["preco_unitario"])
        saldo = float(info["saldo_bruto"])
        _definir_posicao_extrato(
            db,
            ticker,
            qtd,
            preco,
            data_iso=data_iso,
            observacoes=(
                f"Importação extrato Nubank {parseado.get('data_custodia') or data_iso}"
                f" — {qtd} cotas × R$ {preco:.4f} (saldo R$ {saldo:.2f})"
            ),
            idempotency_key=f"{chave}:{ticker}",
        )
        if ticker in comparacao["novos"]:
            alteracoes.append(f"incluiu {ticker}: {qtd} @ R$ {preco:.2f}")
        elif any(a["ticker"] == ticker for a in comparacao["atualizar"]):
            alteracoes.append(f"atualizou {ticker}: {qtd} cotas @ R$ {preco:.2f}")
        else:
            alteracoes.append(f"confirmou {ticker}: {qtd} @ R$ {preco:.2f}")

    if remover_ausentes:
        carteira = db.obter_carteira()
        if carteira is not None and not carteira.empty:
            for _, row in carteira.iterrows():
                ticker = str(row["ticker"]).upper()
                if ticker not in posicoes:
                    db.remover_fii(ticker)
                    alteracoes.append(f"excluiu {ticker} (ausente no extrato)")

    db.set_config(
        "ultima_importacao_custodia",
        {
            "em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_custodia": parseado.get("data_custodia"),
            "arquivo": nome_arquivo,
            "posicoes": len(posicoes),
            "alteracoes": alteracoes,
            "remover_ausentes": remover_ausentes,
        },
    )
    return {
        "aplicado": True,
        "alteracoes": alteracoes,
        "posicoes": len(posicoes),
        "comparacao": comparacao,
        "data_custodia": parseado.get("data_custodia"),
    }


def sincronizar_custodia_nubank(
    db: Any,
    *,
    forcar: bool = False,
    posicoes: dict[str, tuple[int, float]] | None = None,
    chave: str = CHAVE_SYNC,
) -> dict[str, Any]:
    """Compat: aplica o mapa fixo 01/09 (ou posicoes) uma vez."""
    if not forcar and db.get_config(chave):
        return {"aplicado": False, "motivo": "ja_sincronizado"}

    bruto = posicoes or CUSTODIA_NUBANK_20260901
    parseado = {
        "data_custodia": "01/09/2026",
        "data_iso": "2026-09-01",
        "posicoes": {
            t: {
                "quantidade": int(q),
                "preco_unitario": float(p),
                "saldo_bruto": round(int(q) * float(p), 2),
            }
            for t, (q, p) in bruto.items()
        },
    }
    resultado = aplicar_extrato_nubank(
        db, parseado, remover_ausentes=True, nome_arquivo="mapa_fixo_20260901"
    )
    db.set_config(chave, {"sincronizado": True, **resultado})
    return resultado
