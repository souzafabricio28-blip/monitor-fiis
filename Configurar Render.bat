@echo off
title Publicar no Render - Monitor de FIIs
color 0E
cd /d "C:\Users\souza\Desktop\INVESTIMENTOS"
start "" "https://dashboard.render.com/u/settings#api-keys"
python publicar_render.py
pause
