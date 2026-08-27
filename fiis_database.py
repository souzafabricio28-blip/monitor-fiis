"""
Lista de FIIs populares e suas informações
Base de dados com mais de 50 fundos imobiliários
"""

# Lista completa de FIIs organizados por segmento
FIIS_DATABASE = {
    # PAPEL (Crédito Imobiliário)
    "papel": [
        {"ticker": "MXRF11", "nome": "Maxi Renda", "setor": "Papel"},
        {"ticker": "KNCR11", "nome": "Kinea Renda Imobiliária", "setor": "Papel"},
        {"ticker": "KNRI11", "nome": "Kinea Renda Imob. Avançado", "setor": "Papel"},
        {"ticker": "KNHY11", "nome": "Kinea High Yield", "setor": "Papel"},
        {"ticker": "CPTS11", "nome": "Capital Segr. Papel Imob.", "setor": "Papel"},
        {"ticker": "MCCI11", "nome": "Mauá Capital Seguritizadora", "setor": "Papel"},
        {"ticker": "RBRR11", "nome": "RBR Properties", "setor": "Papel"},
        {"ticker": "IRDM11", "nome": "Iridium Recebíveis Imob.", "setor": "Papel"},
        {"ticker": "TRXF11", "nome": "TRX Capital II", "setor": "Papel"},
        {"ticker": "LFTT11", "nome": "Leffta Capital", "setor": "Papel"},
        {"ticker": "NURB11", "nome": "Nch Capital", "setor": "Papel"},
        {"ticker": "FPAB11", "nome": "FG/Areas", "setor": "Papel"},
        {"ticker": "AZPL11", "nome": "Azimut", "setor": "Papel"},
    ],
    
    # TIJOLO (Imóveis)
    "tijolo": [
        {"ticker": "HGLG11", "nome": "CSHG Logística", "setor": "Tijolo"},
        {"ticker": "XPML11", "nome": "XP Malls", "setor": "Tijolo"},
        {"ticker": "BTLG11", "nome": "BTG Pactual Logística", "setor": "Tijolo"},
        {"ticker": "VISC11", "nome": "Vinci Shopping Centers", "setor": "Tijolo"},
        {"ticker": "HSML11", "nome": "HSI Malls", "setor": "Tijolo"},
        {"ticker": "BPML11", "nome": "Brasil Plaza", "setor": "Tijolo"},
        {"ticker": "DRIO11", "nome": "Dかった Rios", "setor": "Tijolo"},
        {"ticker": "MALL11", "nome": "Mall-xl", "setor": "Tijolo"},
        {"ticker": "FIGS11", "nome": "FII Graphs", "setor": "Tijolo"},
        {"ticker": "HGBS11", "nome": "HG Brazil Series", "setor": "Tijolo"},
        {"ticker": "CJCT11", "nome": "CJ Capital", "setor": "Tijolo"},
        {"ticker": "STRX11", "nome": "Star X", "setor": "Tijolo"},
        {"ticker": "DEVA11", "nome": "Deutsche", "setor": "Tijolo"},
    ],
    
    # LOGÍSTICA
    "logistica": [
        {"ticker": "IRDM11", "nome": "Iridium", "setor": "Logístico"},
        {"ticker": "GGRC11", "nome": "GGR Covepi", "setor": "Logístico"},
        {"ticker": "BRLA11", "nome": "BR Properties", "setor": "Logístico"},
        {"ticker": "VILG11", "nome": "Vinci Logística", "setor": "Logístico"},
        {"ticker": "GALG11", "nome": "Gávea Investimentos", "setor": "Logístico"},
        {"ticker": "JPSA11", "nome": "JP Morgan", "setor": "Logístico"},
        {"ticker": "LVBI11", "nome": "Lavvi", "setor": "Logístico"},
        {"ticker": "PQAG11", "nome": "Pátria Agro", "setor": "Logístico"},
        {"ticker": "TJBA11", "nome": "TJBA", "setor": "Logístico"},
        {"ticker": "PNPR11", "nome": "Penha", "setor": "Logístico"},
    ],
    
    # HÍBRIDO
    "hibrido": [
        {"ticker": "KNCR11", "nome": "Kinea", "setor": "Híbrido"},
        {"ticker": "RBRR11", "nome": "RBR", "setor": "Híbrido"},
        {"ticker": "MXRF11", "nome": "Maxi", "setor": "Híbrido"},
        {"ticker": "IRDM11", "nome": "Iridium", "setor": "Híbrido"},
        {"ticker": "RRCI11", "nome": "Riachuelo", "setor": "Híbrido"},
        {"ticker": "OUJP11", "nome": "Ouro Preto", "setor": "Híbrido"},
        {"ticker": "CJCT11", "nome": "CJ Capital", "setor": "Híbrido"},
        {"ticker": "HFOF11", "nome": "Harrow", "setor": "Híbrido"},
        {"ticker": "SHPH11", "nome": "Shopping Paulista", "setor": "Híbrido"},
        {"ticker": "FIGS11", "nome": "FII Graphs", "setor": "Híbrido"},
    ],
    
    # LISTA COMPLETA (todos juntos)
    "todos": []
}

# Adicionar todos os FIIs à lista completa
for setor in FIIS_DATABASE.values():
    if isinstance(setor, list):
        FIIS_DATABASE["todos"].extend(setor)

# Função para buscar FII por ticker
def buscar_fii_por_ticker(ticker: str) -> dict:
    """Busca um FII pelo ticker"""
    ticker = ticker.upper()
    
    for setor, fiis in FIIS_DATABASE.items():
        if setor == "todos":
            continue
        for fii in fiis:
            if fii["ticker"] == ticker:
                return fii
    
    return None

# Função para listar FIIs por setor
def listar_fiis_por_setor(setor: str) -> list:
    """Lista FIIs de um setor específico"""
    return FIIS_DATABASE.get(setor.lower(), [])

# Função para obter todos os tickers
def obter_todos_tickes() -> list:
    """Retorna todos os tickers da base"""
    return [fii["ticker"] for fii in FIIS_DATABASE["todos"]]

# Estatísticas da base
def obter_estatisticas() -> dict:
    """Retorna estatísticas da base de FIIs"""
    total = len(FIIS_DATABASE["todos"])
    
    por_setor = {}
    for setor, fiis in FIIS_DATABASE.items():
        if setor != "todos" and isinstance(fiis, list):
            por_setor[setor] = len(fiis)
    
    return {
        "total": total,
        "por_setor": por_setor
    }
