@echo off
title DLAB CRM Inmobiliaria
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo.
echo  ====================================
echo   DLAB CRM Inmobiliaria
echo   http://127.0.0.1:5000
echo   Presiona CTRL+C para detener
echo  ====================================
echo.
python run_local.py
pause
