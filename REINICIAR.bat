@echo off
echo Cerrando todos los procesos Python anteriores...
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM python3.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
echo Limpiando cache...
if exist "%~dp0__pycache__" rmdir /s /q "%~dp0__pycache__"
echo Iniciando servidor VERSION 6...
cd /d "%~dp0"
start http://127.0.0.1:5000/dashboard_uga
python app.py
pause
