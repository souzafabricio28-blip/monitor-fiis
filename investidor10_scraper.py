"""
Compatibilidade: reexporta o scraper unificado.
"""

from investidor10 import Investidor10API, Investidor10Scraper, extrair_percentual, extrair_valor_br

__all__ = [
    "Investidor10API",
    "Investidor10Scraper",
    "extrair_valor_br",
    "extrair_percentual",
]
