"""
Scraper único do Investidor10 (FIIs e ações).
Página pública: cards de cotação + tabela de informações. Sem login/PRO.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup

from lista_gestor import TICKERS_ACAO_MESMO_COM_11

_BASE = "https://investidor10.com.br"


def extrair_valor_br(texto: str) -> Optional[float]:
    """Converte número BR (1.234,56 ou 5,25); ausente permanece N/D."""
    try:
        texto = str(texto).replace("R$", "").strip()
        texto = "".join(c for c in texto if c.isdigit() or c in ".,-")
        if not texto or texto in {".", ",", "-", ".-"}:
            return None
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        return float(texto)
    except (ValueError, TypeError):
        return None


def extrair_percentual(texto: str) -> Optional[float]:
    return extrair_valor_br(str(texto).replace("%", ""))


def extrair_inteiro_br(texto: str) -> Optional[int]:
    """608.340 ou 45.601.734 (ponto de milhar)."""
    bruto = "".join(c for c in str(texto) if c.isdigit() or c == ".")
    if not bruto:
        return None
    if "," in str(texto):
        valor = extrair_valor_br(texto)
        return int(valor) if valor is not None else None
    try:
        return int(bruto.replace(".", ""))
    except ValueError:
        return None


def extrair_valor_compacto(texto: str) -> Optional[float]:
    """R$ 17,30 M / 7,59 Bilhões / 45,60 Milhões."""
    if not texto or not str(texto).strip():
        return None
    t = str(texto).strip()
    low = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    mult = 1.0
    if "bilh" in low or re.search(r"\bb\b", low) or re.search(r"\sB\s*$", t):
        mult = 1_000_000_000
    elif "milh" in low or re.search(r"\sM\b", t) or re.search(r"\bm\b", low):
        mult = 1_000_000
    numero = re.search(r"-?[\d.]+,[\d]+|-?[\d]+(?:\.[\d]{3})+", t)
    if not numero:
        numero = re.search(r"-?[\d.,]+", t)
    if not numero:
        return None
    valor = extrair_valor_br(numero.group(0))
    if valor is None:
        return None
    return valor * mult


def formatar_compacto(valor: Optional[float], prefixo: str = "R$ ") -> str:
    if valor is None:
        return "N/D"
    abs_v = abs(valor)
    if abs_v >= 1_000_000_000:
        n = valor / 1_000_000_000
        return f"{prefixo}{n:,.2f} B".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs_v >= 1_000_000:
        n = valor / 1_000_000
        return f"{prefixo}{n:,.2f} M".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefixo}{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_pct(valor: Optional[float], casas: int = 2) -> str:
    if valor is None:
        return "N/D"
    return f"{valor:.{casas}f}%".replace(".", ",")


def formatar_numero(valor: Optional[float], casas: int = 2) -> str:
    if valor is None:
        return "N/D"
    return f"{valor:.{casas}f}".replace(".", ",")


def classe_investidor10(ticker: str) -> str:
    t = ticker.upper().replace(".SA", "").strip()
    if t in TICKERS_ACAO_MESMO_COM_11:
        return "acao"
    if t.endswith("11") or t.endswith("12"):
        return "fii"
    return "acao"


def url_ativo(ticker: str) -> str:
    t = ticker.lower().replace(".sa", "").strip()
    pasta = "fiis" if classe_investidor10(ticker) == "fii" else "acoes"
    return f"{_BASE}/{pasta}/{t}/"


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = t.encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


class Investidor10API:
    """Busca dados fundamentalistas no Investidor10."""

    def __init__(self):
        self.base_url = f"{_BASE}/fiis/"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def buscar_fii(self, ticker: str) -> Dict:
        return self.buscar_ativo(ticker)

    def buscar_ativo(self, ticker: str) -> Dict:
        ticker = ticker.upper().replace(".SA", "").strip()
        url = url_ativo(ticker)
        try:
            response = self.session.get(url, timeout=12)
            response.raise_for_status()
            return self.parse_html(ticker, response.text, url)
        except Exception as e:
            return {"ticker": ticker, "erro": str(e), "url": url}

    def parse_html(self, ticker: str, html: str, url: str = "") -> Dict:
        ticker = ticker.upper().replace(".SA", "").strip()
        soup = BeautifulSoup(html, "html.parser")
        dados: Dict = {
            "ticker": ticker,
            "fonte": "Investidor10",
            "classe": classe_investidor10(ticker),
            "coletado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
            "url": url or url_ativo(ticker),
        }

        h1 = soup.find("h1")
        if h1:
            dados["nome"] = h1.get_text(strip=True)

        self._parse_cards(soup, dados)
        self._parse_celulas(soup, dados)
        self._parse_yields(soup, dados)
        self._fallbacks_texto(soup, dados)
        return dados

    def _parse_cards(self, soup: BeautifulSoup, dados: Dict) -> None:
        for card in soup.select("div._card"):
            texto_card = card.get_text(" ", strip=True).lower()
            if "carteira investidor" in texto_card:
                continue
            header = card.select_one("._card-header span[title], ._card-header span, ._card-header")
            titulo = ""
            if header:
                titulo = header.get("title") or header.get_text(" ", strip=True)
            titulo_n = _norm(titulo)
            body = card.select_one("._card-body") or card
            badge = body.select_one(".daily-variation-badge") if body else None
            valor_el = body.select_one("span.value, ._card-body > span, ._card-body div > span")
            valor_txt = valor_el.get_text(" ", strip=True) if valor_el else body.get_text(" ", strip=True)

            if "cotacao" in titulo_n:
                dados["preco"] = extrair_valor_br(valor_txt)
                if badge:
                    dados["variacao_dia"] = extrair_percentual(badge.get_text(" ", strip=True))
            elif "dividend yield" in titulo_n or titulo_n in {"dy", "dy (12m)"} or "dy (12m)" in titulo_n:
                dados["dy"] = extrair_percentual(valor_txt)
            elif titulo_n in {"p/vp", "p vp"} or titulo_n.endswith("p/vp"):
                dados["p_vp"] = extrair_valor_br(valor_txt)
            elif "liquidez" in titulo_n:
                dados["liquidez_diaria"] = extrair_valor_compacto(valor_txt)
            elif "variacao (12m)" in titulo_n or "variacao 12m" in titulo_n:
                dados["variacao_12m"] = extrair_percentual(valor_txt)
            elif titulo_n in {"p/l", "p l"} or titulo_n.endswith("p/l"):
                dados["p_l"] = extrair_valor_br(valor_txt)

    def _parse_celulas(self, soup: BeautifulSoup, dados: Dict) -> None:
        for cell in soup.select("div.cell"):
            nome_el = cell.select_one(".name")
            valor_el = cell.select_one(".value")
            if not nome_el or not valor_el:
                continue
            nome = _norm(nome_el.get_text(" ", strip=True))
            valor_txt = valor_el.get_text(" ", strip=True)
            if not nome or not valor_txt:
                continue
            if nome == "vacancia" and dados.get("vacancia") is None:
                dados["vacancia"] = extrair_percentual(valor_txt)
            elif "cotista" in nome and dados.get("cotistas") is None:
                dados["cotistas"] = extrair_inteiro_br(valor_txt)
            elif nome in {"cotas emitidas", "numero de cotas"} and dados.get("cotas_emitidas") is None:
                compacto = extrair_valor_compacto(valor_txt)
                inteiro = extrair_inteiro_br(valor_txt)
                if "milh" in _norm(valor_txt) and compacto is not None:
                    dados["cotas_emitidas"] = int(compacto)
                elif inteiro is not None:
                    dados["cotas_emitidas"] = inteiro
            elif "patrimonial p" in nome and "cota" in nome:
                dados["vp_cota"] = extrair_valor_br(valor_txt)
            elif nome == "valor patrimonial" and dados.get("patrimonio") is None:
                dados["patrimonio"] = extrair_valor_compacto(valor_txt)
            elif "taxa de administracao" in nome:
                dados["taxa_administracao"] = extrair_percentual(valor_txt)
            elif "tipo de gestao" in nome or nome == "gestao":
                dados["gestao"] = valor_txt.strip()
            elif "tipo de fundo" in nome:
                dados["tipo"] = valor_txt.strip()
            elif nome == "segmento":
                dados["setor"] = valor_txt.strip()
            elif "ultimo rendimento" in nome:
                dados["ultimo_rendimento"] = extrair_valor_br(valor_txt)
            elif nome == "razao social":
                dados["razao_social"] = valor_txt.strip()
            elif nome == "cnpj":
                dados["cnpj"] = valor_txt.strip()
            elif nome == "mandato":
                dados["mandato"] = valor_txt.strip()

    def _parse_yields(self, soup: BeautifulSoup, dados: Dict) -> None:
        for item in soup.select(".content--info--item"):
            txt = item.get_text(" ", strip=True)
            n = _norm(txt)
            nums = re.findall(r"[\d.,]+%?", txt)
            if "yield 1 mes" in n and nums:
                dados["yield_1m"] = extrair_percentual(nums[0])
            elif "yield 3 meses" in n and nums:
                dados["yield_3m"] = extrair_percentual(nums[0])
            elif "yield 6 meses" in n and nums:
                dados["yield_6m"] = extrair_percentual(nums[0])
            elif "yield 12 meses" in n and nums:
                if dados.get("dy") is None:
                    dados["dy"] = extrair_percentual(nums[0])

    def _fallbacks_texto(self, soup: BeautifulSoup, dados: Dict) -> None:
        texto = soup.get_text(" ", strip=True)
        if dados.get("preco") is None:
            preco_match = re.search(
                rf"{dados['ticker']}\s*Cota..o.*?R\$\s*([\d.,]+)",
                texto,
                re.IGNORECASE | re.DOTALL,
            ) or re.search(r"COTA..O.*?R\$\s*([\d.,]+)", texto, re.IGNORECASE | re.DOTALL)
            if preco_match:
                dados["preco"] = extrair_valor_br(preco_match.group(1))
        if dados.get("dy") is None:
            dy_match = re.search(
                r"DY\s*\(?12M\)?\s*:?\s*([\d.,]+)%", texto, re.IGNORECASE
            )
            if dy_match:
                dados["dy"] = extrair_percentual(dy_match.group(1))
        if dados.get("p_vp") is None:
            pvp_match = re.search(r"P/VP\s*:?\s*([\d.,]+)", texto, re.IGNORECASE)
            if pvp_match:
                dados["p_vp"] = extrair_valor_br(pvp_match.group(1))
        if dados.get("patrimonio") is None:
            pl_match = re.search(
                r"patrim.nio\s+de\s+R\$\s*([\d.,]+)\s*(Bilh|Milh)",
                texto,
                re.IGNORECASE,
            )
            if pl_match:
                valor = extrair_valor_br(pl_match.group(1))
                if valor is not None:
                    unidade = pl_match.group(2).lower()
                    dados["patrimonio"] = valor * (
                        1_000_000_000 if "bilh" in unidade else 1_000_000
                    )
        if dados.get("vacancia") is None:
            vac_match = re.search(r"vac.ncia.*?([\d.,]+)%", texto, re.IGNORECASE)
            if vac_match:
                dados["vacancia"] = extrair_percentual(vac_match.group(1))
        if dados.get("setor") is None:
            setor_match = re.search(
                r"do segmento\s+(Híbrido|Papel|Tijolo|Logístico|FOF|Shopping|Lajes)",
                texto,
                re.IGNORECASE,
            )
            if setor_match:
                dados["setor"] = setor_match.group(1)
        if dados.get("tipo") is None:
            tipo_match = re.search(
                r"(Fundo de\s+(Papel|Tijolo|Logístico|Híbrido))",
                texto,
                re.IGNORECASE,
            )
            if tipo_match:
                dados["tipo"] = tipo_match.group(1)

    def buscar_lista(self, tickers: List[str]) -> List[Dict]:
        return [self.buscar_ativo(t) for t in tickers]


Investidor10Scraper = Investidor10API

CAMPOS_I10 = (
    "preco",
    "dy",
    "p_vp",
    "p_l",
    "vacancia",
    "patrimonio",
    "setor",
    "tipo",
    "liquidez_diaria",
    "variacao_dia",
    "variacao_12m",
    "cotistas",
    "cotas_emitidas",
    "vp_cota",
    "taxa_administracao",
    "gestao",
    "ultimo_rendimento",
    "razao_social",
    "cnpj",
    "mandato",
    "yield_1m",
    "yield_3m",
    "yield_6m",
)
