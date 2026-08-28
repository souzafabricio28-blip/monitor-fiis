"""
Exportação de dados para Excel
Permite exportar dados de FIIs para planilhas Excel
"""

import pandas as pd
from datetime import datetime
import os


def _fmt(valor, prefixo="", sufixo=""):
    return "N/D" if valor is None else f"{prefixo}{float(valor):.2f}{sufixo}"


class FiiExcelExport:
    """Classe para exportar dados de FIIs para Excel"""
    
    def __init__(self):
        self.writer = None
    
    def exportar_carteira(self, dados: dict, nome_arquivo: str = None):
        """Exporta dados da carteira para Excel"""
        
        if nome_arquivo is None:
            nome_arquivo = f"carteira_fii_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
            # Aba 1: Resumo
            df_resumo = self._criar_df_resumo(dados)
            df_resumo.to_excel(writer, sheet_name='Resumo', index=False)
            
            # Aba 2: Detalhes
            df_detalhes = self._criar_df_detalhes(dados)
            df_detalhes.to_excel(writer, sheet_name='Detalhes', index=False)
            
            # Aba 3: Dividendos
            df_dividendos = self._criar_df_dividendos(dados)
            df_dividendos.to_excel(writer, sheet_name='Dividendos', index=False)
            
            # Ajustar largura das colunas
            for sheet in writer.sheets.values():
                for col in sheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in col)
                    sheet.column_dimensions[col[0].column_letter].width = min(max_length + 2, 30)
        
        print(f"Arquivo Excel salvo: {nome_arquivo}")
        return nome_arquivo
    
    def _criar_df_resumo(self, dados: dict) -> pd.DataFrame:
        """Cria DataFrame de resumo"""
        resumo = {
            "Métrica": [
                "Total Investido",
                "Valor Atual",
                "Ganho de Capital",
                "Projeção Mensal",
                "Proventos Registrados",
                "DY Médio",
                "Data da Análise"
            ],
            "Valor": [
                _fmt(dados.get('total_investido'), "R$ "),
                _fmt(dados.get('valor_atual', dados.get('total_atual')), "R$ "),
                _fmt(dados.get('lucro'), "R$ "),
                _fmt(dados.get('projecao_renda_mensal'), "R$ "),
                _fmt(dados.get('proventos_registrados'), "R$ "),
                _fmt(dados.get('dy_medio'), sufixo="%"),
                datetime.now().strftime("%d/%m/%Y %H:%M")
            ]
        }
        
        return pd.DataFrame(resumo)
    
    def _criar_df_detalhes(self, dados: dict) -> pd.DataFrame:
        """Cria DataFrame de detalhes"""
        fiis = dados.get('fiis', [])
        
        if not fiis:
            return pd.DataFrame(columns=[
                'Ticker', 'Quantidade', 'Preço Compra', 'Preço Atual',
                'Valor Investido', 'Valor Atual', 'Lucro', 'Lucro %',
                'DY', 'Rendimento Mensal'
            ])
        
        rows = []
        for fii in fiis:
            lucro = fii.get('lucro', fii.get('lucro_prejuizo', 0))
            lucro_pct = fii.get('lucro_pct', fii.get('lucro_prejuizo_pct', 0))
            dy = fii.get('dy', fii.get('dy_anual', 0))
            rows.append({
                'Ticker': fii.get('ticker', ''),
                'Quantidade': fii.get('quantidade', 0),
                'Preço Compra': _fmt(fii.get('preco_compra'), "R$ "),
                'Preço Atual': _fmt(fii.get('preco_atual'), "R$ "),
                'Valor Investido': _fmt(fii.get('valor_investido'), "R$ "),
                'Valor Atual': _fmt(fii.get('valor_atual'), "R$ "),
                'Ganho de Capital': _fmt(lucro, "R$ "),
                'Lucro %': _fmt(lucro_pct, sufixo="%"),
                'DY': _fmt(dy, sufixo="%"),
                'Projeção Mensal': _fmt(fii.get('projecao_renda_mensal'), "R$ "),
                'Proventos Registrados': _fmt(fii.get('proventos_registrados'), "R$ "),
                'Fonte': fii.get('fonte', 'N/D'),
                'Confiança': fii.get('confianca', 'N/D'),
                'Status Dados': fii.get('status_dados', 'N/D'),
            })
        
        return pd.DataFrame(rows)
    
    def _criar_df_dividendos(self, dados: dict) -> pd.DataFrame:
        """Cria DataFrame de dividendos"""
        # Por enquanto retorna vazio
        return pd.DataFrame(columns=['Ticker', 'Data', 'Valor por Cota', 'Total'])
    
    def exportar_comparacao(self, fiis_data: list, nome_arquivo: str = None):
        """Exporta comparação de FIIs"""
        
        if nome_arquivo is None:
            nome_arquivo = f"comparacao_fiis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        df = pd.DataFrame(fiis_data)
        
        with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Comparação', index=False)
            
            # Ajustar largura das colunas
            for sheet in writer.sheets.values():
                for col in sheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in col)
                    sheet.column_dimensions[col[0].column_letter].width = min(max_length + 2, 30)
        
        print(f"Arquivo de comparação salvo: {nome_arquivo}")
        return nome_arquivo
    
    def exportar_historico(self, historico: list, nome_arquivo: str = None):
        """Exporta histórico de cotações"""
        
        if nome_arquivo is None:
            nome_arquivo = f"historico_fii_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        df = pd.DataFrame(historico)
        
        with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Histórico', index=False)
            
            # Ajustar largura das colunas
            for sheet in writer.sheets.values():
                for col in sheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in col)
                    sheet.column_dimensions[col[0].column_letter].width = min(max_length + 2, 30)
        
        print(f"✅ Arquivo de histórico salvo: {nome_arquivo}")
        return nome_arquivo


# Função para usar no fii_monitor.py
def exportar_para_excel(dados: dict, nome_arquivo: str = None):
    """Função auxiliar para exportar para Excel"""
    exporter = FiiExcelExport()
    return exporter.exportar_carteira(dados, nome_arquivo)
