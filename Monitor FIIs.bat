@echo off
title Monitor de FIIs - Investimentos
color 0A

cd /d "C:\Users\souza\Desktop\INVESTIMENTOS"

REM Iniciar Streamlit em segundo plano
start /min "" python -m streamlit run app.py --server.headless=true --server.port=8501 --server.address=0.0.0.0 --browser.gatherUsageStats=false

REM Esperar o servidor iniciar
timeout /t 4 /nobreak >nul

REM Abrir no Brave
start brave "http://localhost:8501"
