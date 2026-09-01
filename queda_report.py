"""
Queda ≥ 10%: detecta, busca manchetes e monta PDF resumido.

Não inventa causa. Sem notícia recente o motivo fica N/D.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus

import requests
import yfinance as yf
from fpdf import FPDF
from fpdf.enums import XPos, YPos

logger = logging.getLogger(__name__)

LIMITE_QUEDA_PCT = 10.0
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def variacao_pct(atual, base) -> Optional[float]:
    """Variação percentual. Cotação ou base ausente permanece N/D (não vira 0)."""
    if atual is None or base is None:
        return None
    try:
        a = float(atual)
        b = float(base)
    except (TypeError, ValueError):
        return None
    if b == 0:
        return None
    return (a - b) / b * 100


def gatilhos_de_queda(
    preco_atual,
    preco_compra=None,
    preco_anterior=None,
    maxima_periodo=None,
    limite: float = LIMITE_QUEDA_PCT,
) -> Dict:
    """Marca queda ≥ limite contra compra, fechamento anterior e máxima do período."""
    vs_compra = variacao_pct(preco_atual, preco_compra)
    vs_anterior = variacao_pct(preco_atual, preco_anterior)
    vs_maxima = variacao_pct(preco_atual, maxima_periodo)
    disparos = []
    if vs_compra is not None and vs_compra <= -limite:
        disparos.append("preço de compra")
    if vs_anterior is not None and vs_anterior <= -limite:
        disparos.append("fechamento anterior")
    if vs_maxima is not None and vs_maxima <= -limite:
        disparos.append("máxima recente")
    pior = None
    for valor in (vs_compra, vs_anterior, vs_maxima):
        if valor is None:
            continue
        if pior is None or valor < pior:
            pior = valor
    return {
        "atingiu": bool(disparos),
        "disparos": disparos,
        "vs_compra": vs_compra,
        "vs_anterior": vs_anterior,
        "vs_maxima": vs_maxima,
        "pior_pct": pior,
        "preco_atual": preco_atual,
        "preco_compra": preco_compra,
        "preco_anterior": preco_anterior,
        "maxima_periodo": maxima_periodo,
    }


def _limpar_titulo(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = texto.replace(" - Google News", "").replace(" – Google News", "")
    return texto


def _noticias_yahoo(ticker: str, limite: int) -> List[dict]:
    itens: List[dict] = []
    try:
        acao = yf.Ticker(f"{ticker}.SA")
        bruto = None
        if hasattr(acao, "get_news"):
            bruto = acao.get_news()
        if not bruto:
            bruto = getattr(acao, "news", None) or []
        for item in bruto:
            if not isinstance(item, dict):
                continue
            conteudo = item.get("content") if isinstance(item.get("content"), dict) else item
            titulo = _limpar_titulo(
                str(conteudo.get("title") or item.get("title") or "")
            )
            if not titulo:
                continue
            link = ""
            click = conteudo.get("clickThroughUrl") or item.get("link") or {}
            if isinstance(click, dict):
                link = click.get("url") or ""
            else:
                link = str(click or "")
            fonte = (
                (conteudo.get("provider") or {}).get("displayName")
                if isinstance(conteudo.get("provider"), dict)
                else item.get("publisher") or "Yahoo Finance"
            )
            itens.append(
                {
                    "titulo": titulo,
                    "fonte": fonte or "Yahoo Finance",
                    "link": link,
                    "origem": "Yahoo Finance",
                }
            )
            if len(itens) >= limite:
                break
    except Exception as exc:
        logger.warning("Falha nas notícias Yahoo de %s: %s", ticker, exc)
    return itens


def _noticias_google(ticker: str, limite: int) -> List[dict]:
    query = f"{ticker} B3 OR {ticker} FII OR {ticker} ação"
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )
    itens: List[dict] = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        raiz = ET.fromstring(resp.content)
        for item in raiz.findall(".//item"):
            titulo = _limpar_titulo(item.findtext("title") or "")
            if not titulo:
                continue
            fonte = item.findtext("source") or "Google News"
            itens.append(
                {
                    "titulo": titulo,
                    "fonte": fonte,
                    "link": item.findtext("link") or "",
                    "origem": "Google News",
                }
            )
            if len(itens) >= limite:
                break
    except Exception as exc:
        logger.warning("Falha no RSS Google News de %s: %s", ticker, exc)
    return itens


def _parse_infomoney_posts(posts, limite: int) -> List[dict]:
    """Converte o JSON do WP do InfoMoney em manchetes. Sem inventar texto."""
    itens: List[dict] = []
    if not isinstance(posts, list):
        return itens
    for post in posts:
        if not isinstance(post, dict):
            continue
        titulo_raw = post.get("title") or {}
        if isinstance(titulo_raw, dict):
            titulo = html.unescape(
                re.sub(r"<[^>]+>", "", str(titulo_raw.get("rendered") or ""))
            )
        else:
            titulo = str(titulo_raw)
        titulo = _limpar_titulo(titulo)
        if not titulo:
            continue
        excerpt_raw = post.get("excerpt") or {}
        if isinstance(excerpt_raw, dict):
            excerpt = html.unescape(
                re.sub(r"<[^>]+>", " ", str(excerpt_raw.get("rendered") or ""))
            )
        else:
            excerpt = str(excerpt_raw or "")
        excerpt = re.sub(r"\s+", " ", excerpt).strip()
        link = str(post.get("link") or "").strip()
        if not link:
            continue
        itens.append(
            {
                "titulo": titulo[:220],
                "fonte": "InfoMoney",
                "link": link,
                "origem": "InfoMoney",
                "resumo": excerpt[:400],
            }
        )
        if len(itens) >= limite:
            break
    return itens


def _noticias_infomoney(ticker: str, limite: int) -> List[dict]:
    url = (
        "https://www.infomoney.com.br/wp-json/wp/v2/posts"
        f"?search={quote_plus(ticker)}&per_page={limite}&_fields=link,title,excerpt,date"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        return _parse_infomoney_posts(resp.json(), limite)
    except Exception as exc:
        logger.warning("Falha nas notícias InfoMoney de %s: %s", ticker, exc)
        return []


def buscar_noticias(ticker: str, limite: int = 8) -> List[dict]:
    """Manchetes recentes (InfoMoney + Yahoo + Google News). Sem inventar texto."""
    ticker = (ticker or "").upper().replace(".SA", "").strip()
    vistos = set()
    juntos: List[dict] = []
    for bloco in (
        _noticias_infomoney(ticker, limite),
        _noticias_yahoo(ticker, limite),
        _noticias_google(ticker, limite),
    ):
        for item in bloco:
            chave = item["titulo"].casefold()
            if chave in vistos:
                continue
            vistos.add(chave)
            juntos.append(item)
            if len(juntos) >= limite:
                return juntos
    return juntos


def montar_resumo(ticker: str, queda: Dict, noticias: Iterable[dict]) -> Dict:
    """Texto curto: o que caiu e o que as notícias dizem. Motivo ausente = N/D."""
    noticias = list(noticias or [])
    pior = queda.get("pior_pct")
    disparos = queda.get("disparos") or []
    if queda.get("atingiu"):
        abertura = (
            f"{ticker} registrou queda de {pior:.1f}% "
            f"(limite {LIMITE_QUEDA_PCT:.0f}%) frente a: {', '.join(disparos)}."
        )
    else:
        abertura = (
            f"{ticker} não atingiu queda de {LIMITE_QUEDA_PCT:.0f}% "
            "nos parâmetros disponíveis."
        )
    if noticias:
        bullets = [f"- {n['titulo']} ({n.get('fonte') or 'N/D'})" for n in noticias[:6]]
        motivo = (
            "Manchetes recentes (associação temporal, não prova de causa):\n"
            + "\n".join(bullets)
        )
        motivo_curto = noticias[0]["titulo"]
    else:
        motivo = (
            "N/D — não há manchetes recentes o bastante para explicar a queda. "
            "O sistema não inventa o motivo."
        )
        motivo_curto = "N/D"
    return {
        "ticker": ticker,
        "abertura": abertura,
        "motivo": motivo,
        "motivo_curto": motivo_curto,
        "noticias": noticias,
        "queda": queda,
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def _pdf_txt(texto: str) -> str:
    if texto is None:
        return "N/D"
    convertido = (
        str(texto)
        .replace("—", "-")
        .replace("–", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )
    return convertido.encode("latin-1", "replace").decode("latin-1")


def _quebrar_tokens_longos(texto: str, max_len: int = 70) -> str:
    """Evita token sem espaço (URL, ticker colado) estourar a largura do PDF."""
    partes = []
    for token in str(texto or "").split(" "):
        if len(token) <= max_len:
            partes.append(token)
            continue
        partes.append(" ".join(token[i : i + max_len] for i in range(0, len(token), max_len)))
    return " ".join(partes)


def _bloco(pdf: FPDF, texto: str, h: float = 5) -> None:
    """multi_cell a partir da margem esquerda (fpdf2 deixa o cursor à direita)."""
    pdf.set_x(pdf.l_margin)
    largura = pdf.w - pdf.l_margin - pdf.r_margin
    if largura < 20:
        pdf.add_page()
        pdf.set_x(pdf.l_margin)
        largura = pdf.w - pdf.l_margin - pdf.r_margin
    corpo = _pdf_txt(_quebrar_tokens_longos(texto or "N/D")) or "N/D"
    pdf.multi_cell(largura, h, corpo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin)


class QuedaPDF(FPDF):
    def header(self):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(102, 126, 234)
        self.cell(
            self.epw,
            10,
            "Relatorio de queda (>= 10%)",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_font("Helvetica", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(
            self.epw,
            8,
            f"Monitor de FIIs · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.ln(4)
        self.set_x(self.l_margin)

    def footer(self):
        self.set_y(-15)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(
            self.epw,
            8,
            "Manchetes sao correlacao temporal, nao prova de causa. Sem noticia = N/D.",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.TOP,
        )


def gerar_pdf_queda_bytes(resumo: Dict) -> bytes:
    pdf = QuedaPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    queda = resumo.get("queda") or {}

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.set_x(pdf.l_margin)
    pdf.cell(
        pdf.epw,
        12,
        _pdf_txt(resumo.get("ticker") or ""),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(50, 50, 50)
    _bloco(pdf, resumo.get("abertura") or "", 6)
    pdf.ln(3)

    linhas = [
        ("Preco atual", _fmt_preco(queda.get("preco_atual"))),
        ("Preco de compra", _fmt_preco(queda.get("preco_compra"))),
        ("Fechamento anterior", _fmt_preco(queda.get("preco_anterior"))),
        ("Maxima recente", _fmt_preco(queda.get("maxima_periodo"))),
        ("vs compra", _fmt_pct(queda.get("vs_compra"))),
        ("vs fechamento anterior", _fmt_pct(queda.get("vs_anterior"))),
        ("vs maxima recente", _fmt_pct(queda.get("vs_maxima"))),
    ]
    pdf.set_font("Helvetica", "", 10)
    for rotulo, valor in linhas:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 6, _pdf_txt(rotulo) + ":", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(
            pdf.epw - 55,
            6,
            _pdf_txt(valor),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(
        pdf.epw,
        8,
        "Por que caiu (noticias)",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_font("Helvetica", "", 10)
    _bloco(pdf, resumo.get("motivo") or "N/D", 6)

    noticias = resumo.get("noticias") or []
    if noticias:
        pdf.ln(3)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(pdf.epw, 7, "Fontes", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        for item in noticias:
            linha = f"* {item.get('fonte')}: {item.get('titulo')}"
            _bloco(pdf, linha, 5)

    raw = pdf.output()
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return bytes(raw)


def _fmt_preco(valor) -> str:
    return "N/D" if valor is None else f"R$ {float(valor):.2f}"


def _fmt_pct(valor) -> str:
    return "N/D" if valor is None else f"{float(valor):+.2f}%"


def analisar_posicao_queda(ticker: str, posicao: Dict, historico=None) -> Dict:
    """Une cotação da posição + máxima do histórico (se houver)."""
    maxima = None
    anterior = posicao.get("preco_anterior")
    if historico is not None and getattr(historico, "empty", True) is False:
        try:
            if "Close" in historico.columns:
                maxima = float(historico["Close"].max())
                if anterior is None and len(historico["Close"]) >= 2:
                    anterior = float(historico["Close"].iloc[-2])
        except Exception:
            pass
    queda = gatilhos_de_queda(
        posicao.get("preco_atual"),
        preco_compra=posicao.get("preco_compra"),
        preco_anterior=anterior,
        maxima_periodo=maxima,
    )
    queda["ticker"] = ticker
    return queda


def relatorio_queda(ticker: str, posicao: Dict, historico=None) -> Dict:
    queda = analisar_posicao_queda(ticker, posicao, historico=historico)
    noticias = buscar_noticias(ticker) if queda.get("atingiu") else []
    resumo = montar_resumo(ticker, queda, noticias)
    try:
        resumo["pdf"] = gerar_pdf_queda_bytes(resumo)
    except Exception as exc:
        logger.exception("Falha ao gerar PDF de queda de %s", ticker)
        resumo["pdf"] = None
        resumo["pdf_erro"] = str(exc)
    return resumo


CHAVE_QUEDAS = "quedas_10_enviadas"


def verificar_quedas_carteira(db, posicoes: Iterable[dict], enviar_whatsapp: bool = False) -> List[dict]:
    """Gera relatórios só para quem bateu -10%. WhatsApp opcional, sem apikey no banco."""
    from market_data import buscar_historico
    from whatsapp_notifier import WhatsAppNotifier, whatsapp_configurado

    relatorios = []
    estado = db.get_config(CHAVE_QUEDAS) or {}
    if not isinstance(estado, dict):
        estado = {}
    novo_estado = dict(estado)

    for posicao in posicoes:
        ticker = str(posicao.get("ticker") or "").upper()
        if not ticker:
            continue
        hist = None
        try:
            hist = buscar_historico(ticker, "1mo")
        except Exception:
            hist = None
        queda = analisar_posicao_queda(ticker, posicao, historico=hist)
        if not queda.get("atingiu"):
            novo_estado.pop(ticker, None)
            continue
        noticias = buscar_noticias(ticker)
        resumo = montar_resumo(ticker, queda, noticias)
        try:
            resumo["pdf"] = gerar_pdf_queda_bytes(resumo)
        except Exception as exc:
            logger.exception("Falha ao gerar PDF de queda de %s", ticker)
            resumo["pdf"] = None
            resumo["pdf_erro"] = str(exc)
        relatorios.append(resumo)

        chave_dia = datetime.now().strftime("%Y-%m-%d")
        previa = estado.get(ticker) or {}
        ja_enviou = previa.get("dia") == chave_dia
        if enviar_whatsapp and not ja_enviou and whatsapp_configurado(db):
            enviado = WhatsAppNotifier().enviar_alerta(
                f"Queda >= 10% — {ticker}",
                (
                    f"{resumo['abertura']}\n\n"
                    f"Manchete: {resumo['motivo_curto']}"
                ),
                "aviso",
            )
            if enviado:
                novo_estado[ticker] = {"dia": chave_dia, "pior_pct": queda.get("pior_pct")}
        elif ja_enviou:
            novo_estado[ticker] = previa

    db.set_config(CHAVE_QUEDAS, novo_estado)
    return relatorios
