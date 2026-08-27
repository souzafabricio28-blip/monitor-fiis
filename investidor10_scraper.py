"""
Web Scraping de FIIs do Investidor10
Busca dados fundamentalistas de fundos imobiliários
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import csv
from datetime import datetime


class Investidor10Scraper:
    def __init__(self):
        self.base_url = "https://investidor10.com.br/fiis/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def buscar_dados_fii(self, ticker: str) -> dict:
        """
        Busca dados de um FII específico no Investidor10

        Args:
            ticker: Código do FII (ex: MXRF11)

        Returns:
            dict com os dados do FII
        """
        ticker = ticker.upper().replace(".SA", "")
        url = f"{self.base_url}{ticker.lower()}/"

        try:
            print(f"Buscando dados de {ticker}...")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            texto_completo = soup.get_text()

            dados = {
                "ticker": ticker,
                "url": url,
                "data_consulta": datetime.now().strftime("%d/%m/%Y %H:%M"),
            }

            # Buscar nome do fundo (h1)
            h1 = soup.find("h1")
            if h1:
                dados["nome"] = h1.get_text(strip=True)

            # Buscar preço usando regex no texto
            preco_match = re.search(rf"{ticker}\s*Cota..o.*?R\$\s*([\d.,]+)", texto_completo, re.IGNORECASE | re.DOTALL)
            if preco_match:
                dados["preco"] = self._extrair_valor(preco_match.group(1))
            
            # Tentar另一种方式 buscar preço
            if dados.get("preco", 0) == 0:
                preco_match2 = re.search(r"COTA..O.*?R\$\s*([\d.,]+)", texto_completo, re.IGNORECASE | re.DOTALL)
                if preco_match2:
                    dados["preco"] = self._extrair_valor(preco_match2.group(1))

            # Buscar DY (Dividend Yield)
            dy_match = re.search(rf"{ticker}\s*DY\s*\(12M\)\s*:\s*([\d.,]+)%", texto_completo, re.IGNORECASE)
            if dy_match:
                dados["dy"] = self._extrair_percentual(dy_match.group(1))
            
            # Tentar outra forma de DY
            if dados.get("dy", 0) == 0:
                dy_match2 = re.search(r"Dividend.*?Yield.*?([\d.,]+)%", texto_completo, re.IGNORECASE | re.DOTALL)
                if dy_match2:
                    dados["dy"] = self._extrair_percentual(dy_match2.group(1))

            # Buscar P/VP
            pvp_match = re.search(rf"{ticker}\s*P/VP\s*:\s*([\d.,]+)", texto_completo, re.IGNORECASE)
            if pvp_match:
                dados["p_vp"] = self._extrair_valor(pvp_match.group(1))

            # Buscar Patrimônio
            pl_match = re.search(r"patrim.nio.*?R\$\s*([\d.,]+)", texto_completo, re.IGNORECASE)
            if pl_match:
                dados["patrimonio"] = self._extrair_valor(pl_match.group(1))

            # Buscar vacância
            vac_match = re.search(r"vac.ncia.*?([\d.,]+)%", texto_completo, re.IGNORECASE)
            if vac_match:
                dados["vacancia"] = self._extrair_percentual(vac_match.group(1))

            # Buscar setor
            setor_match = re.search(r"segmento\s+(\w+)", texto_completo, re.IGNORECASE)
            if setor_match:
                dados["setor"] = setor_match.group(1)

            # Buscar tipo do fundo
            tipo_match = re.search(r"tipo.*?(Fundo de \w+)", texto_completo, re.IGNORECASE)
            if tipo_match:
                dados["tipo"] = tipo_match.group(1)

            # Buscar liquidez
            liq_match = re.search(r"liquidez.*?R\$\s*([\d.,]+)", texto_completo, re.IGNORECASE)
            if liq_match:
                dados["liquidez"] = self._extrair_valor(liq_match.group(1))

            print(f"  Dados de {ticker} coletados com sucesso!")
            return dados

        except requests.exceptions.RequestException as e:
            print(f"  Erro ao buscar {ticker}: {e}")
            return {"ticker": ticker, "erro": str(e)}

    def _extrair_valor(self, texto: str) -> float:
        """Extrai valor numérico de texto"""
        try:
            # Remove caracteres não numéricos exceto vírgula e ponto
            texto = texto.replace("R$", "").strip()
            # Remove pontos de milhar e substitui vírgula por ponto
            texto = texto.replace(".", "").replace(",", ".")
            # Remove qualquer caractere que não seja número ou ponto
            texto = "".join(c for c in texto if c.isdigit() or c in ".-")
            return float(texto) if texto else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _extrair_percentual(self, texto: str) -> float:
        """Extrai percentual de texto"""
        try:
            texto = texto.replace("%", "").replace(",", ".").strip()
            return float(texto) if texto else 0.0
        except (ValueError, TypeError):
            return 0.0

    def buscar_lista_fiis(self, lista_tickers: list) -> list:
        """
        Busca dados de uma lista de FIIs

        Args:
            lista_tickers: Lista de códigos de FIIs

        Returns:
            Lista de dicts com dados dos FIIs
        """
        resultados = []

        for ticker in lista_tickers:
            dados = self.buscar_dados_fii(ticker)
            resultados.append(dados)

        return resultados

    def salvar_csv(self, dados: list, nome_arquivo: str = "fiis_dados.csv"):
        """Salva dados em formato CSV"""
        if not dados:
            print("Nenhum dado para salvar!")
            return

        # Chaves do primeiro item como cabeçalho
        chaves = dados[0].keys()

        with open(nome_arquivo, "w", newline="", encoding="utf-8-sig") as arquivo:
            writer = csv.DictWriter(arquivo, fieldnames=chaves)
            writer.writeheader()
            writer.writerows(dados)

        print(f"  Dados salvos em: {nome_arquivo}")

    def salvar_json(self, dados: list, nome_arquivo: str = "fiis_dados.json"):
        """Salva dados em formato JSON"""
        with open(nome_arquivo, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)

        print(f"  Dados salvos em: {nome_arquivo}")

    def imprimir_tabela(self, dados: list):
        """Imprime dados formatados em tabela"""
        if not dados:
            print("Nenhum dado para exibir!")
            return

        print("\n" + "=" * 60)
        print("DADOS DOS FIIs - INVESTIDOR10")
        print("=" * 60)

        for fii in dados:
            if "erro" in fii:
                print(f"\n  {fii['ticker']}: {fii['erro']}")
                continue

            print(f"\n{'-' * 50}")
            print(f"Ticker: {fii.get('ticker', 'N/A')}")
            print(f"Nome: {fii.get('nome', 'N/A')}")
            print(f"Preco: R$ {fii.get('preco', 0):.2f}")
            print(f"Dividend Yield: {fii.get('dy', 0):.2f}%")
            print(f"P/VP: {fii.get('p_vp', 0):.2f}")
            print(f"Patrimonio: R$ {fii.get('patrimonio', 0):,.2f}")
            print(f"Vacancia: {fii.get('vacancia', 0):.2f}%")
            print(f"Liquidez: R$ {fii.get('liquidez', 0):,.2f}")
            print(f"Setor: {fii.get('setor', 'N/A')}")
            print(f"Tipo: {fii.get('tipo', 'N/A')}")

        print(f"\n{'=' * 60}")
        print(f"Consulta: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print("=" * 60)


def main():
    """Funcao principal"""
    print("\n" + "=" * 60)
    print("INVESTIDOR10 WEB SCRAPING - DADOS DE FIIs")
    print("=" * 60)

    scraper = Investidor10Scraper()

    # FIIs de exemplo
    fiis_padrao = ["mxrf11", "kncr11", "cpts11", "mcci11", "rbrr11"]

    print("\nFIIs disponiveis para consulta:")
    print("1. MXRF11 (Master Cash)")
    print("2. KNCR11 (Kinea Renda Imob.)")
    print("3. CPTS11 (Capital Securitizadora)")
    print("4. MCCI11 (Maua Capital)")
    print("5. RBRR11 (RBR Properties)")
    print("6. Personalizado")

    opcao = input("\nEscolha uma opcao (1-6): ").strip()

    if opcao == "6":
        tickers_input = input("Digite os tickers separados por virgula: ").strip()
        fiis = [t.strip() for t in tickers_input.split(",")]
    elif opcao in ["1", "2", "3", "4", "5"]:
        fiis = [fiis_padrao[int(opcao) - 1]]
    else:
        fiis = fiis_padrao

    print(f"\nBuscando dados de: {', '.join(fiis).upper()}")

    # Buscar dados
    dados = scraper.buscar_lista_fiis(fiis)

    # Exibir resultados
    scraper.imprimir_tabela(dados)

    # Salvar arquivos
    salvar = input("\nDeseja salvar os dados? (s/n): ").strip().lower()

    if salvar == "s":
        formato = input("Formato (csv/json/ambos): ").strip().lower()

        if formato in ["csv", "ambos"]:
            scraper.salvar_csv(dados)

        if formato in ["json", "ambos"]:
            scraper.salvar_json(dados)

    print("\n  Processo finalizado!")


if __name__ == "__main__":
    main()
