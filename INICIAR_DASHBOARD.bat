@echo off
chcp 65001 >nul
title EMCALI - Dashboard Inventarios

echo.
echo  ====================================================
echo       EMCALI - DASHBOARD COBERTURA INVENTARIOS
echo  ====================================================
echo.

:: Paso 1: Verificar Python
echo  [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no esta instalado.
    echo  Instale Python desde https://www.python.org/downloads/
    echo  Marque la casilla "Add Python to PATH"
    pause
    exit /b
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo  [OK] %PYVER%

:: Paso 2: Verificar app.py
echo  [2/5] Verificando archivos...
if not exist "%~dp0app.py" (
    echo  [ERROR] No se encontro app.py en %~dp0
    pause
    exit /b
)
echo  [OK] app.py encontrado

:: Paso 3: Limpiar cache de Python
echo  [3/5] Limpiando cache...
if exist "%~dp0__pycache__" (
    rmdir /s /q "%~dp0__pycache__"
    echo  [OK] Cache eliminado
) else (
    echo  [OK] Sin cache previo
)

:: Paso 4: Instalar librerias
echo  [4/5] Instalando librerias...
pip install flask pyxlsb pandas openpyxl --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERROR] No se pudieron instalar las librerias.
    echo  Verifique su conexion a internet.
    pause
    exit /b
)
echo  [OK] Librerias listas

:: Paso 5: Arrancar
echo  [5/5] Iniciando servidor...
echo.

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    set IP=%%a
    goto :got_ip
)
:got_ip
set IP=%IP: =%

echo  ====================================================
echo   SISTEMA LISTO - NO CIERRE ESTA VENTANA
echo.
echo   Local:  http://127.0.0.1:5000/dashboard_uga
echo   Red:    http://%IP%:5000/dashboard_uga
echo.
echo   PIN:    emcali2024
echo  ====================================================
echo.

timeout /t 2 /nobreak >nul
start http://127.0.0.1:5000/dashboard_uga

cd /d "%~dp0"
python app.py

echo.
echo  Sistema detenido. Presione cualquier tecla para cerrar.
pause >nul
