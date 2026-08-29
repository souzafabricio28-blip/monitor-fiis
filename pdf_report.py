"""
Gerador de relatórios PDF para FIIs.
"""

from io import BytesIO

from fpdf import FPDF
from datetime import datetime
import os


def _moeda(valor):
    return "N/D" if valor is None else f"R$ {float(valor):.2f}"


def _percentual(valor):
    return "N/D" if valor is None else f"{float(valor):.2f}%"


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
        print(f"Relatório salvo: {nome_arquivo}")
        
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
        
        valor_atual = dados.get('valor_atual', dados.get('total_atual', 0))
        lucro = dados.get('lucro')
        metricas = [
            ("Total Investido", _moeda(dados.get('total_investido'))),
            ("Valor Atual (pode ser parcial)", _moeda(valor_atual)),
            ("Ganho de Capital", _moeda(lucro)),
            ("Rentabilidade total (preco + proventos)", _moeda(dados.get("lucro_com_dividendos"))),
            ("Rentabilidade total %", _percentual(dados.get("rentabilidade_com_dividendos"))),
            ("Projecao Mensal", _moeda(dados.get('projecao_renda_mensal'))),
            ("Proventos Registrados", _moeda(dados.get('proventos_registrados'))),
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
            
            lucro = fii.get('lucro', fii.get('lucro_prejuizo', 0))
            lucro_pct = fii.get('lucro_pct', fii.get('lucro_prejuizo_pct', 0))
            dy = fii.get('dy', fii.get('dy_anual', 0))
            dados_fii = [
                ("Quantidade", f"{fii.get('quantidade', 0)} cotas"),
                ("Preco Compra", _moeda(fii.get('preco_compra'))),
                ("Preco Atual", _moeda(fii.get('preco_atual'))),
                ("Valor Investido", _moeda(fii.get('valor_investido'))),
                ("Valor Atual", _moeda(fii.get('valor_atual'))),
                ("Ganho de Capital", f"{_moeda(lucro)} ({_percentual(lucro_pct)})"),
                ("Rentab. total", f"{_moeda(fii.get('lucro_com_dividendos'))} ({_percentual(fii.get('lucro_com_dividendos_pct'))})"),
                ("DY Anual", _percentual(dy)),
                ("Projecao Mensal", _moeda(fii.get('projecao_renda_mensal'))),
                ("Proventos Registrados", _moeda(fii.get('proventos_registrados'))),
                ("Fonte/Confianca", f"{fii.get('fonte', 'N/D')} / {fii.get('confianca', 'N/D')}"),
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
        total = dados.get('valor_atual', dados.get('total_atual', 0))
        
        if not fiis or total == 0:
            return
        
        self.pdf.set_font("Arial", "", 10)
        self.pdf.set_text_color(80, 80, 80)
        
        for fii in fiis:
            valor = fii.get('valor_atual') or 0
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


def gerar_relatorio_pdf(dados: dict, nome_arquivo: str = None):
    """Função auxiliar para gerar relatório PDF"""
    report = FiiPDFReport()
    return report.criar_relatorio(dados, nome_arquivo)


def gerar_relatorio_pdf_bytes(dados: dict) -> bytes:
    """Gera o PDF em memória para download no dashboard."""
    report = FiiPDFReport()
    buf = BytesIO()
    report.pdf.add_page()
    report._adicionar_cabecalho()
    report._adicionar_resumo(dados)
    report._adicionar_detalhes(dados)
    report._adicionar_composicao(dados)
    report._adicionar_rodape()
    raw = report.pdf.output(dest="S")
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return bytes(raw)
