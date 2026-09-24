@echo off
title DLAB CRM - MODO DESARROLLO
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set FLASK_ENV=development
set FLASK_DEBUG=1
echo.
echo  ====================================
echo   DLAB CRM - MODO DESARROLLO
echo   Debug: ON
echo   http://127.0.0.1:5000
echo   Presiona CTRL+C para detener
echo  ====================================
echo.
python -c "from app import create_app; app = create_app(); app.run(host='127.0.0.1', port=5000, debug=True)"
pause
