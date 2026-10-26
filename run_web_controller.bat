@echo off
title Alice Display Controller
cd /d "%~dp0"
echo Starting Alice Display Controller on http://localhost:8080 ...
python web_app.py
pause
