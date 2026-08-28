@echo off
cd /d "C:\Users\souza\Desktop\INVESTIMENTOS"
start /min "" pythonw -m streamlit run app.py --server.headless=true
exit
