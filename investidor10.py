"""
Scraper único do Investidor10 (FIIs).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


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


class Investidor10API:
    """Busca dados fundamentalistas de FIIs no Investidor10."""

    def __init__(self):
        self.base_url = "https://investidor10.com.br/fiis/"
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
        ticker = ticker.upper().replace(".SA", "").strip()
        url = f"{self.base_url}{ticker.lower()}/"

        try:
            response = self.session.get(url, timeout=8)
            response.raise_for_status()
            return self.parse_html(ticker, response.text, url)
        except Exception as e:
            return {"ticker": ticker, "erro": str(e)}

    def parse_html(self, ticker: str, html: str, url: str = "") -> Dict:
        """Analisa HTML isoladamente para permitir testes sem rede."""
        ticker = ticker.upper().replace(".SA", "").strip()
        soup = BeautifulSoup(html, "html.parser")
        texto = soup.get_text(" ", strip=True)
        dados = {
            "ticker": ticker,
            "fonte": "Investidor10",
            "coletado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
            "url": url or f"{self.base_url}{ticker.lower()}/",
        }

        h1 = soup.find("h1")
        if h1:
            dados["nome"] = h1.get_text(strip=True)

        preco_match = re.search(
            rf"{ticker}\s*Cota..o.*?R\$\s*([\d.,]+)",
            texto,
            re.IGNORECASE | re.DOTALL,
        )
        if not preco_match:
            preco_match = re.search(
                r"COTA..O.*?R\$\s*([\d.,]+)",
                texto,
                re.IGNORECASE | re.DOTALL,
            )
        if preco_match:
            dados["preco"] = extrair_valor_br(preco_match.group(1))

        dy_match = re.search(
            rf"{ticker}\s*DY\s*\(12M\)\s*:?\s*([\d.,]+)%",
            texto,
            re.IGNORECASE,
        ) or re.search(r"DY\s*\(12M\)\s*:?\s*([\d.,]+)%", texto, re.IGNORECASE)
        if dy_match:
            dados["dy"] = extrair_percentual(dy_match.group(1))

        pvp_match = re.search(
            rf"{ticker}\s*P/VP\s*:?\s*([\d.,]+)", texto, re.IGNORECASE
        ) or re.search(r"P/VP\s*:?\s*([\d.,]+)", texto, re.IGNORECASE)
        if pvp_match:
            dados["p_vp"] = extrair_valor_br(pvp_match.group(1))

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

        vac_match = re.search(r"vac.ncia.*?([\d.,]+)%", texto, re.IGNORECASE)
        if vac_match:
            dados["vacancia"] = extrair_percentual(vac_match.group(1))

        setor_match = re.search(
            r"do segmento\s+(Híbrido|Papel|Tijolo|Logístico|FOF|Shopping|Lajes)",
            texto,
            re.IGNORECASE,
        )
        if setor_match:
            dados["setor"] = setor_match.group(1)

        tipo_match = re.search(
            r"(Fundo de\s+(Papel|Tijolo|Logístico|Híbrido))",
            texto,
            re.IGNORECASE,
        )
        if tipo_match:
            dados["tipo"] = tipo_match.group(1)
        return dados

    def buscar_lista(self, tickers: List[str]) -> List[Dict]:
        return [self.buscar_fii(t) for t in tickers]


# Alias para compatibilidade com main.py / scraper antigo
Investidor10Scraper = Investidor10API
