@echo off
echo Carpeta: %~dp0
echo.
echo Total de lineas en app.py:
powershell -command "(Get-Content '%~dp0app.py').Count"
echo.
echo Buscando 'VERSION 6' en app.py:
powershell -command "Select-String -Path '%~dp0app.py' -Pattern 'VERSION 6' | Select-Object -First 1"
echo.
echo Buscando 'v6' en app.py:
powershell -command "Select-String -Path '%~dp0app.py' -Pattern 'v6-local\|v6<' | Select-Object -First 1"
echo.
echo Linea 1080:
powershell -command "Get-Content '%~dp0app.py' | Select-Object -Index 1079"
echo.
pause
