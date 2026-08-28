Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\souza\Desktop\INVESTIMENTOS"
WshShell.Run "python -m streamlit run app.py --server.headless=true --server.port=8501 --server.address=0.0.0.0 --browser.gatherUsageStats=false", 0, False
