"""
Integração do Investidor10 no Monitor de FIIs
Adiciona funcionalidade de web scraping ao sistema principal
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime


class Investidor10API:
    """Classe para integrar dados do Investidor10"""

    def __init__(self):
        self.base_url = "https://investidor10.com.br/fiis/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def buscar_fii(self, ticker: str) -> dict:
        """
        Busca dados de um FII no Investidor10

        Args:
            ticker: Código do FII (ex: MXRF11)

        Returns:
            dict com os dados do FII
        """
        ticker = ticker.upper().replace(".SA", "")
        url = f"{self.base_url}{ticker.lower()}/"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            dados = {
                "ticker": ticker,
                "fonte": "Investidor10",
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            }

            # Buscar preço
            preco_tag = soup.find("div", class_="indicator-card--value")
            if preco_tag:
                dados["preco"] = self._parse preco(preco_tag.get_text())

            # Buscar indicadores
            cards = soup.find_all("div", class_="indicator-card")
            for card in cards:
                titulo = card.find("div", class_="indicator-card--title")
                valor = card.find("div", class_="indicator-card--value")

                if titulo and valor:
                    t = titulo.get_text(strip=True).lower()
                    v = valor.get_text(strip=True)

                    if "dividend yield" in t:
                        dados["dy"] = self._parse_percentual(v)
                    elif "p/apovp" in t or "p/vp" in t:
                        dados["p_vp"] = self._parse_valor(v)
                    elif "patrimônio" in t:
                        dados["patrimonio"] = self._parse_valor(v)
                    elif "vacância" in t:
                        dados["vacancia"] = self._parse_percentual(v)

            # Buscar setor
            setor_tag = soup.find("a", href=lambda x: x and "/setor/" in x if x else False)
            if setor_tag:
                dados["setor"] = setor_tag.get_text(strip=True)

            # Buscar nome
            nome_tag = soup.find("h1")
            if nome_tag:
                dados["nome"] = nome_tag.get_text(strip=True)

            return dados

        except Exception as e:
            return {"ticker": ticker, "erro": str(e)}

    def _parse_valor(self, texto: str) -> float:
        try:
            texto = texto.replace("R$", "").replace(".", "").replace(",", ".").strip()
            texto = "".join(c for c in texto if c.isdigit() or c in ".-")
            return float(texto) if texto else 0.0
        except:
            return 0.0

    def _parse_percentual(self, texto: str) -> float:
        try:
            texto = texto.replace("%", "").replace(",", ".").strip()
            return float(texto) if texto else 0.0
        except:
            return 0.0


def integrar_ao_monitor():
    """Função para integrar ao fii_monitor.py"""

    print("\n=== INVESTIDOR10 - DADOS ATUALIZADOS ===\n")

    api = Investidor10API()

    # Buscar MXRF11 (o FII do usuário)
    ticker = "MXRF11"
    print(f"Buscando dados de {ticker} no Investidor10...")

    dados = api.buscar_fii(ticker)

    if "erro" in dados:
        print(f"Erro: {dados['erro']}")
        return

    # Exibir dados
    print(f"\n{'='*50}")
    print(f"DADOS COMPLETOS - {ticker}")
    print(f"{'='*50}")
    print(f"Nome: {dados.get('nome', 'N/A')}")
    print(f"Preço Atual: R$ {dados.get('preco', 0):.2f}")
    print(f"Dividend Yield: {dados.get('dy', 0):.2f}%")
    print(f"P/VP: {dados.get('p_vp', 0):.2f}")
    print(f"Patrimônio: R$ {dados.get('patrimonio', 0):,.2f}")
    print(f"Vacância: {dados.get('vacancia', 0):.2f}%")
    print(f"Setor: {dados.get('setor', 'N/A')}")
    print(f"{'='*50}")
    print(f"Fonte: {dados.get('fonte', 'N/A')}")
    print(f"Consulta: {dados.get('data', 'N/A')}")

    # Calcular rendimento com dados atualizados
    if dados.get("preco", 0) > 0 and dados.get("dy", 0) > 0:
        investimento = 240  # R$ 240 do usuário
        cotas = int(investimento / dados["preco"])
        dy_mensal = dados["dy"] / 12 / 100
        rendimento_mensal = investimento * dy_mensal

        print(f"\n{'='*50}")
        print(f"SEU RENDIMENTO ESTIMADO (R$ 240)")
        print(f"{'='*50}")
        print(f"Cotas possíveis: {cotas}")
        print(f"Investimento total: R$ {cotas * dados['preco']:.2f}")
        print(f"Rendimento mensal: R$ {rendimento_mensal:.2f}")
        print(f"Rendimento anual: R$ {rendimento_mensal * 12:.2f}")
        print(f"{'='*50}")

    return dados


if __name__ == "__main__":
    integrar_ao_monitor()
