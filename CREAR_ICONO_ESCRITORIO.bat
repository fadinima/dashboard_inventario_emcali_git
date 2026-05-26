@echo off
chcp 65001 >nul
title EMCALI — Crear Icono en Escritorio

echo.
echo  Creando icono del Dashboard en el escritorio...
echo.

set CARPETA=%~dp0
set ESCRITORIO=%USERPROFILE%\Desktop
set NOMBRE=Dashboard Inventarios EMCALI

:: Crear acceso directo usando PowerShell
powershell -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%ESCRITORIO%\%NOMBRE%.lnk');" ^
  "$s.TargetPath='%CARPETA%ABRIR_DASHBOARD.vbs';" ^
  "$s.WorkingDirectory='%CARPETA%';" ^
  "$s.Description='Dashboard Cobertura Inventarios EMCALI';" ^
  "$s.IconLocation='%SystemRoot%\System32\shell32.dll,14';" ^
  "$s.Save()"

if exist "%ESCRITORIO%\%NOMBRE%.lnk" (
    echo  [OK] Icono creado en el escritorio
    echo.
    echo  Busca el icono:  "%NOMBRE%"
    echo  Da doble clic para abrir el dashboard directamente.
    echo.
) else (
    echo  [ERROR] No se pudo crear el icono automaticamente.
    echo  Hazlo manual:
    echo  1. Clic derecho en ABRIR_DASHBOARD.vbs
    echo  2. Enviar a -- Escritorio (crear acceso directo)
)

echo  Presiona cualquier tecla para cerrar...
pause >nul
