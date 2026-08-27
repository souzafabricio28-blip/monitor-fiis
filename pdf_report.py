"""
Gerador de relatórios PDF para FIIs
Cria relatórios profissionais em PDF
"""

from fpdf import FPDF
from datetime import datetime
import os


class FiiPDFReport:
    """Classe para gerar relatórios PDF de FIIs"""
    
    def __init__(self):
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=15)
    
    def criar_relatorio(self, dados: dict, nome_arquivo: str = None):
        """Cria um relatório PDF completo"""
        
        if nome_arquivo is None:
            nome_arquivo = f"relatorio_fii_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Adicionar página
        self.pdf.add_page()
        
        # Cabeçalho
        self._adicionar_cabecalho()
        
        # Resumo
        self._adicionar_resumo(dados)
        
        # Detalhes por FII
        self._adicionar_detalhes(dados)
        
        # Gráfico de composição (texto)
        self._adicionar_composicao(dados)
        
        # Rodapé
        self._adicionar_rodape()
        
        # Salvar
        self.pdf.output(nome_arquivo)
        print(f"✅ Relatório salvo: {nome_arquivo}")
        
        return nome_arquivo
    
    def _adicionar_cabecalho(self):
        """Adiciona cabeçalho do relatório"""
        self.pdf.set_font("Arial", "B", 24)
        self.pdf.set_text_color(102, 126, 234)
        self.pdf.cell(0, 20, "Relatorio de FIIs", ln=True, align="C")
        
        self.pdf.set_font("Arial", "", 12)
        self.pdf.set_text_color(100, 100, 100)
        self.pdf.cell(0, 10, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")
        
        self.pdf.ln(10)
        
        # Linha separadora
        self.pdf.set_draw_color(102, 126, 234)
        self.pdf.set_line_width(0.5)
        self.pdf.line(10, self.pdf.get_y(), 200, self.pdf.get_y())
        self.pdf.ln(10)
    
    def _adicionar_resumo(self, dados: dict):
        """Adiciona resumo da carteira"""
        self.pdf.set_font("Arial", "B", 16)
        self.pdf.set_text_color(50, 50, 50)
        self.pdf.cell(0, 10, "Resumo da Carteira", ln=True)
        
        self.pdf.ln(5)
        
        # Métricas
        self.pdf.set_font("Arial", "", 12)
        self.pdf.set_text_color(80, 80, 80)
        
        metricas = [
            ("Total Investido", f"R$ {dados.get('total_investido', 0):.2f}"),
            ("Valor Atual", f"R$ {dados.get('valor_atual', 0):.2f}"),
            ("Lucro/Prejuízo", f"R$ {dados.get('lucro', 0):.2f}"),
            ("Rendimento Mensal", f"R$ {dados.get('rendimento_mensal', 0):.2f}"),
            ("Rendimento Anual", f"R$ {dados.get('rendimento_anual', 0):.2f}"),
        ]
        
        for titulo, valor in metricas:
            self.pdf.set_font("Arial", "B", 11)
            self.pdf.cell(60, 8, titulo + ":", 0, 0)
            self.pdf.set_font("Arial", "", 11)
            self.pdf.cell(0, 8, valor, ln=True)
        
        self.pdf.ln(10)
    
    def _adicionar_detalhes(self, dados: dict):
        """Adiciona detalhes de cada FII"""
        self.pdf.set_font("Arial", "B", 16)
        self.pdf.set_text_color(50, 50, 50)
        self.pdf.cell(0, 10, "Detalhes por FII", ln=True)
        
        self.pdf.ln(5)
        
        fiis = dados.get('fiis', [])
        
        if not fiis:
            self.pdf.set_font("Arial", "", 12)
            self.pdf.set_text_color(150, 150, 150)
            self.pdf.cell(0, 10, "Nenhum FII na carteira", ln=True)
            return
        
        for fii in fiis:
            # Cabeçalho do FII
            self.pdf.set_fill_color(102, 126, 234)
            self.pdf.set_text_color(255, 255, 255)
            self.pdf.set_font("Arial", "B", 12)
            self.pdf.cell(0, 10, f"  {fii.get('ticker', 'N/A')}", ln=True, fill=True)
            
            # Dados do FII
            self.pdf.set_text_color(80, 80, 80)
            self.pdf.set_font("Arial", "", 10)
            
            dados_fii = [
                ("Quantidade", f"{fii.get('quantidade', 0)} cotas"),
                ("Preço Compra", f"R$ {fii.get('preco_compra', 0):.2f}"),
                ("Preço Atual", f"R$ {fii.get('preco_atual', 0):.2f}"),
                ("Valor Investido", f"R$ {fii.get('valor_investido', 0):.2f}"),
                ("Valor Atual", f"R$ {fii.get('valor_atual', 0):.2f}"),
                ("Lucro/Prejuízo", f"R$ {fii.get('lucro', 0):.2f} ({fii.get('lucro_pct', 0):.2f}%)"),
                ("DY Anual", f"{fii.get('dy', 0):.2f}%"),
                ("Rendimento Mensal", f"R$ {fii.get('rendimento_mensal', 0):.2f}"),
            ]
            
            for titulo, valor in dados_fii:
                self.pdf.set_font("Arial", "B", 10)
                self.pdf.cell(50, 6, titulo + ":", 0, 0)
                self.pdf.set_font("Arial", "", 10)
                self.pdf.cell(0, 6, valor, ln=True)
            
            self.pdf.ln(5)
    
    def _adicionar_composicao(self, dados: dict):
        """Adiciona composição da carteira"""
        self.pdf.set_font("Arial", "B", 16)
        self.pdf.set_text_color(50, 50, 50)
        self.pdf.cell(0, 10, "Composição da Carteira", ln=True)
        
        self.pdf.ln(5)
        
        fiis = dados.get('fiis', [])
        total = dados.get('valor_atual', 0)
        
        if not fiis or total == 0:
            return
        
        self.pdf.set_font("Arial", "", 10)
        self.pdf.set_text_color(80, 80, 80)
        
        for fii in fiis:
            valor = fii.get('valor_atual', 0)
            percentual = (valor / total * 100) if total > 0 else 0
            
            # Barra de progresso visual
            self.pdf.set_font("Arial", "B", 10)
            self.pdf.cell(30, 6, fii.get('ticker', ''), 0, 0)
            
            self.pdf.set_font("Arial", "", 10)
            self.pdf.cell(30, 6, f"R$ {valor:.2f}", 0, 0)
            
            self.pdf.cell(20, 6, f"{percentual:.1f}%", 0, 0)
            
            # Barra visual
            barra_largura = 80
            barra_altura = 5
            x_inicio = self.pdf.get_x() + 5
            y_inicio = self.pdf.get_y() + 1
            
            self.pdf.set_fill_color(200, 200, 200)
            self.pdf.rect(x_inicio, y_inicio, barra_largura, barra_altura, "F")
            
            self.pdf.set_fill_color(102, 126, 234)
            self.pdf.rect(x_inicio, y_inicio, barra_largura * percentual / 100, barra_altura, "F")
            
            self.pdf.ln(8)
    
    def _adicionar_rodape(self):
        """Adiciona rodapé do relatório"""
        self.pdf.ln(20)
        
        # Linha separadora
        self.pdf.set_draw_color(200, 200, 200)
        self.pdf.set_line_width(0.3)
        self.pdf.line(10, self.pdf.get_y(), 200, self.pdf.get_y())
        
        self.pdf.ln(5)
        
        self.pdf.set_font("Arial", "", 8)
        self.pdf.set_text_color(150, 150, 150)
        self.pdf.cell(0, 5, "Relatório gerado automaticamente pelo Monitor de FIIs", ln=True, align="C")
        self.pdf.cell(0, 5, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")


# Função para usar no fii_monitor.py
def gerar_relatorio_pdf(dados: dict, nome_arquivo: str = None):
    """Função auxiliar para gerar relatório PDF"""
    report = FiiPDFReport()
    return report.criar_relatorio(dados, nome_arquivo)
