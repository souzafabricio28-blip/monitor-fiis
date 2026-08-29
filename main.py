"""
Monitor de FIIs - Versão Completa
Sistema completo de monitoramento de fundos imobiliários

Funcionalidades:
- Dashboard web com Streamlit
- Web Scraping do Investidor10
- Alertas por WhatsApp
- Relatórios PDF
- Exportação para Excel
- Agendador automático
- Score de qualidade
- Comparação de FIIs

Autor: Seu Nome
Versão: 2.0.0
"""

import sys
import os
import subprocess
from datetime import datetime

# Adicionar diretório atual ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def instalar_dependencias():
    """Instala todas as dependências necessárias"""
    print("📦 Instalando dependências...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependências instaladas com sucesso!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao instalar dependências: {e}")
        return False


def verificar_dependencias():
    """Verifica se todas as dependências estão instaladas"""
    dependencias = [
        "yfinance", "pandas", "matplotlib", "plotly",
        "jinja2", "requests", "bs4", "schedule",
        "tabulate", "streamlit", "fpdf", "openpyxl"
    ]
    
    faltando = []
    
    for dep in dependencias:
        try:
            __import__(dep)
        except ImportError:
            faltando.append(dep)
    
    return faltando


def menu_principal():
    """Exibe o menu principal"""
    print("\n" + "=" * 60)
    print("🏠 MONITOR DE FIIs - Versão Completa")
    print("=" * 60)
    print(f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    
    print("\n📋 Opções:")
    print("1. 🖥️  Abrir Dashboard Web (Streamlit)")
    print("2. 📊 Executar Monitor Terminal")
    print("3. 🔍 Buscar FII (Investidor10)")
    print("4. ⚖️  Comparar FIIs")
    print("5. 📄 Gerar Relatório PDF")
    print("6. 📊 Exportar para Excel")
    print("7. 🔔 Testar WhatsApp")
    print("8. ⏰ Iniciar Agendador")
    print("9. 📦 Instalar/Atualizar Dependências")
    print("0. 🚪 Sair")
    print("=" * 60)


def opcao_dashboard():
    """Abre o dashboard Streamlit"""
    print("\n🖥️ Iniciando Dashboard Web...")
    print("Acesse: http://localhost:8501")
    
    try:
        subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py"])
        print("✅ Dashboard iniciado!")
    except Exception as e:
        print(f"❌ Erro ao iniciar dashboard: {e}")


def opcao_monitor():
    """Executa o monitor terminal"""
    print("\n📊 Iniciando Monitor Terminal...")
    
    try:
        from fii_monitor import FIIMonitor
        monitor = FIIMonitor()
        monitor.executar()
    except Exception as e:
        print(f"❌ Erro ao iniciar monitor: {e}")


def opcao_buscar_fii():
    """Busca dados de um FII"""
    print("\n🔍 Buscar FII no Investidor10")
    
    ticker = input("Digite o ticker do FII: ").upper()
    
    if not ticker:
        print("Ticker inválido!")
        return
    
    from market_data import buscar_dados_completos

    dados = buscar_dados_completos(ticker)
    
    if "erro" in dados:
        print(f"❌ Erro: {dados['erro']}")
        return
    
    print(f"\n{'='*50}")
    print(f"📊 DADOS - {ticker}")
    print(f"{'='*50}")
    print(f"Nome: {dados.get('nome', 'N/A')}")
    print(f"Preço: {dados.get('preco_atual') if dados.get('preco_atual') is not None else 'N/D'}")
    print(f"Dividend Yield: {dados.get('dy') if dados.get('dy') is not None else 'N/D'}")
    print(f"P/VP: {dados.get('p_vp') if dados.get('p_vp') is not None else 'N/D'}")
    print(f"Patrimônio: {dados.get('patrimonio') if dados.get('patrimonio') is not None else 'N/D'}")
    print(f"Setor: {dados.get('setor', 'N/A')}")
    print(f"Fonte: {dados.get('fonte', 'N/D')} | Confiança: {dados.get('confianca', 'N/D')}")
    print(f"{'='*50}")


def opcao_comparar():
    """Compara múltiplos FIIs"""
    print("\n⚖️ Comparar FIIs")
    
    tickers = input("Digite os tickers separados por vírgula: ").upper()
    
    if not tickers:
        print("Nenhum ticker informado!")
        return
    
    lista_tickers = [t.strip() for t in tickers.split(",")]
    
    from market_data import buscar_dados_completos

    dados = [buscar_dados_completos(t) for t in lista_tickers]
    for fii in dados:
        print(
            f"{fii['ticker']}: preço={fii.get('preco_atual', 'N/D')} "
            f"DY={fii.get('dy', 'N/D')} P/VP={fii.get('p_vp', 'N/D')} "
            f"confiança={fii.get('confianca', 'N/D')}"
        )


def opcao_pdf():
    """Gera relatório PDF"""
    print("\n📄 Gerar Relatório PDF")

    from pdf_report import FiiPDFReport
    from portfolio import analisar_carteira

    analise = analisar_carteira()
    if 'erro' in analise:
        print(f"❌ {analise['erro']}")
        return

    report = FiiPDFReport()
    arquivo = report.criar_relatorio(analise)
    print(f"✅ Relatório salvo: {arquivo}")


def opcao_excel():
    """Exporta dados para Excel"""
    print("\n📊 Exportar para Excel")

    from excel_export import FiiExcelExport
    from portfolio import analisar_carteira

    analise = analisar_carteira()
    if 'erro' in analise:
        print(f"❌ {analise['erro']}")
        return

    exporter = FiiExcelExport()
    arquivo = exporter.exportar_carteira(analise)
    print(f"✅ Arquivo salvo: {arquivo}")


def opcao_whatsapp():
    """Testa notificações WhatsApp usando somente o ambiente."""
    print("\n🔔 Testar WhatsApp (+55 11 97367-4455)")

    from whatsapp_notifier import WhatsAppNotifier, telefone_destino, whatsapp_configurado

    if whatsapp_configurado():
        notifier = WhatsAppNotifier()
        if notifier.testar_conexao():
            print(f"✅ WhatsApp ok para +{telefone_destino()}")
            teste = input("Deseja enviar outra mensagem de teste? (s/n): ").lower()
            if teste == "s":
                notifier.enviar_mensagem("✅ WhatsApp configurado com sucesso!")
                print("✅ Mensagem de teste enviada!")
        else:
            print("❌ Erro ao enviar no WhatsApp (confira WHATSAPP_APIKEY).")
    else:
        print("❌ Defina WHATSAPP_APIKEY no ambiente. Destino: +55 11 97367-4455.")


def opcao_agendador():
    """Inicia o agendador de tarefas"""
    print("\n⏰ Iniciar Agendador")
    print("Este irá executar tarefas automaticamente todos os dias.")
    
    from scheduler import executar_agendador
    
    executar_agendador()


def main():
    """Função principal"""
    print("\n🚀 Monitor de FIIs v2.0.0")
    
    # Verificar dependências
    faltando = verificar_dependencias()
    
    if faltando:
        print(f"\n⚠️ Dependências faltando: {', '.join(faltando)}")
        instalar = input("Deseja instalar agora? (s/n): ").lower()
        
        if instalar == "s":
            instalar_dependencias()
        else:
            print("❌ Execute novamente após instalar as dependências")
            return
    
    # Loop principal
    while True:
        menu_principal()
        
        opcao = input("\nEscolha uma opção: ").strip()
        
        if opcao == "1":
            opcao_dashboard()
        elif opcao == "2":
            opcao_monitor()
        elif opcao == "3":
            opcao_buscar_fii()
        elif opcao == "4":
            opcao_comparar()
        elif opcao == "5":
            opcao_pdf()
        elif opcao == "6":
            opcao_excel()
        elif opcao == "7":
            opcao_whatsapp()
        elif opcao == "8":
            opcao_agendador()
        elif opcao == "9":
            instalar_dependencias()
        elif opcao == "0":
            print("\n👋 Obrigado por usar o Monitor de FIIs!")
            break
        else:
            print("\n❌ Opção inválida!")
        
        input("\nPressione Enter para continuar...")


if __name__ == "__main__":
    main()
