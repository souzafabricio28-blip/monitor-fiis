"""
Agendador de tarefas para atualização automática
Executa tarefas agendadas para monitoramento de FIIs
"""

import schedule
import time
from datetime import datetime
import sys
import os


class FiiScheduler:
    """Classe para agendar tarefas de monitoramento"""
    
    def __init__(self):
        self.tarefas = []
        self.executando = False
    
    def agendar_tarefa(self, horario: str, funcao, descricao: str = ""):
        """
        Agenda uma tarefa para executar em horário específico
        
        Args:
            horario: Horário no formato "HH:MM"
            funcao: Função a ser executada
            descricao: Descrição da tarefa
        """
        self.tarefas.append({
            "horario": horario,
            "funcao": funcao,
            "descricao": descricao
        })
        
        schedule.every().day.at(horario).do(funcao)
        print(f"⏰ Tarefa agendada: {descricao} às {horario}")
    
    def agendar_diariamente(self, horario: str, funcao, descricao: str = ""):
        """Agenda uma tarefa para executar todos os dias"""
        self.agendar_tarefa(horario, funcao, descricao)
    
    def agendar_semanalmente(self, dia: str, horario: str, funcao, descricao: str = ""):
        """
        Agenda uma tarefa para executar semanalmente
        
        Args:
            dia: Dia da semana (segunda, terca, etc.)
            horario: Horário no formato "HH:MM"
        """
        dias_semana = {
            "segunda": schedule.every().monday,
            "terca": schedule.every().tuesday,
            "quarta": schedule.every().wednesday,
            "quinta": schedule.every().thursday,
            "sexta": schedule.every().friday,
            "sabado": schedule.every().saturday,
            "domingo": schedule.every().sunday
        }
        
        if dia.lower() in dias_semana:
            dias_semana[dia.lower()].at(horario).do(funcao)
            print(f"⏰ Tarefa agendada: {descricao} todo(a) {dia} às {horario}")
    
    def iniciar(self):
        """Inicia o agendador"""
        self.executando = True
        print("\n🚀 Agendador iniciado!")
        print("Pressione Ctrl+C para parar\n")
        
        try:
            while self.executando:
                schedule.run_pending()
                time.sleep(60)  # Verifica a cada minuto
        except KeyboardInterrupt:
            print("\n⏹️ Agendador parado pelo usuário")
            self.executando = False
    
    def parar(self):
        """Para o agendador"""
        self.executando = False
        schedule.clear()
        print("⏹️ Agendador parado")
    
    def listar_tarefas(self):
        """Lista todas as tarefas agendadas"""
        print("\n📋 Tarefas Agendadas:")
        print("-" * 40)
        
        for tarefa in self.tarefas:
            print(f"⏰ {tarefa['horario']} - {tarefa['descricao']}")
        
        print("-" * 40)
        print(f"Total: {len(self.tarefas)} tarefas")


# Funções de tarefas para agendar
def tarefa_atualizar_cotacoes():
    """Tarefa: Atualizar cotações de todos os FIIs"""
    print(f"\n🔄 [{datetime.now().strftime('%H:%M')}] Atualizando cotações...")
    
    # Importar aqui para evitar importação circular
    from fii_monitor import FIIMonitor
    
    monitor = FIIMonitor()
    monitor.atualizar_todos()
    
    print(f"✅ [{datetime.now().strftime('%H:%M')}] Atualização concluída!")


def tarefa_verificar_alertas():
    """Tarefa: Verificar e enviar alertas da watchlist (WhatsApp via env)."""
    print(f"\n🔔 [{datetime.now().strftime('%H:%M')}] Verificando alertas...")

    from db import DatabaseManager
    from whatsapp_notifier import verificar_alertas_watchlist

    db = DatabaseManager()
    resultado = verificar_alertas_watchlist(db)
    disparados = resultado.get("disparados") or []
    enviados = resultado.get("enviados") or []
    print(
        f"Watchlist: {len(disparados)} no alvo, "
        f"{len(enviados)} aviso(s) novo(s), "
        f"{len(resultado.get('omitidos_dedup') or [])} já notificado(s)."
    )
    if not resultado.get("whatsapp_ok"):
        print("WhatsApp inativo (falta WHATSAPP_APIKEY ou foi desligado).")

    try:
        from portfolio import analisar_carteira
        from queda_report import verificar_quedas_carteira

        analise = analisar_carteira(db)
        if "erro" not in analise:
            rels = verificar_quedas_carteira(
                db, analise.get("fiis") or [], enviar_whatsapp=True
            )
            print(f"Quedas ≥10%: {len(rels)} relatório(s).")
    except Exception as exc:
        print(f"Relatórios de queda ignorados: {exc}")

    try:
        from fii_monitor import FIIMonitor

        FIIMonitor().verificar_alertas()
    except Exception as exc:
        print(f"Alertas da carteira (CLI) ignorados: {exc}")

    print(f"✅ [{datetime.now().strftime('%H:%M')}] Verificação concluída!")


def tarefa_gerar_relatorio():
    """Tarefa: Gerar relatório diário"""
    print(f"\n📊 [{datetime.now().strftime('%H:%M')}] Gerando relatório...")
    
    from fii_monitor import FIIMonitor
    
    monitor = FIIMonitor()
    monitor.gerar_relatorio()
    
    print(f"✅ [{datetime.now().strftime('%H:%M')}] Relatório gerado!")


def tarefa_vigia():
    """Tarefa: saúde do site + resumo da carteira (WhatsApp se configurado)."""
    print(f"\n🛡️ [{datetime.now().strftime('%H:%M')}] Vigia...")
    from vigia import rodar_vigia

    resultado = rodar_vigia(enviar=True)
    print(resultado.get("texto") or "")
    print(f"✅ [{datetime.now().strftime('%H:%M')}] Vigia ok={resultado['saude'].get('ok')}")


def criar_agendador_padrao():
    """Cria um agendador com configurações padrão"""
    scheduler = FiiScheduler()
    
    # Agendar tarefas
    scheduler.agendar_diariamente("18:00", tarefa_atualizar_cotacoes, "Atualizar cotações")
    scheduler.agendar_diariamente("18:30", tarefa_verificar_alertas, "Verificar alertas")
    scheduler.agendar_diariamente("18:45", tarefa_vigia, "Vigia do app (saúde + carteira)")
    scheduler.agendar_diariamente("19:00", tarefa_gerar_relatorio, "Gerar relatório")
    
    return scheduler


# Função principal para executar o agendador
def executar_agendador():
    """Executa o agendador de tarefas"""
    scheduler = criar_agendador_padrao()
    scheduler.listar_tarefas()
    scheduler.iniciar()


if __name__ == "__main__":
    executar_agendador()
