# EMCALI — Crear icono Dashboard en el escritorio
# Ejecutar: clic derecho -> Ejecutar con PowerShell

$carpeta    = Split-Path -Parent $MyInvocation.MyCommand.Path
$escritorio = [Environment]::GetFolderPath("Desktop")
$destino    = "$escritorio\Dashboard Inventarios EMCALI.lnk"
$objetivo   = "$carpeta\ABRIR_DASHBOARD.vbs"

$shell   = New-Object -ComObject WScript.Shell
$acceso  = $shell.CreateShortcut($destino)
$acceso.TargetPath       = $objetivo
$acceso.WorkingDirectory = $carpeta
$acceso.Description      = "Dashboard Cobertura Inventarios EMCALI"
$acceso.IconLocation     = "C:\Windows\System32\shell32.dll,14"
$acceso.Save()

if (Test-Path $destino) {
    Write-Host ""
    Write-Host "  ICONO CREADO EXITOSAMENTE en el escritorio" -ForegroundColor Green
    Write-Host "  Busca: 'Dashboard Inventarios EMCALI'" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "  No se pudo crear. Intenta manualmente:" -ForegroundColor Red
    Write-Host "  Clic derecho en ABRIR_DASHBOARD.vbs -> Enviar a -> Escritorio" -ForegroundColor Yellow
}

Write-Host "  Presiona Enter para cerrar..."
Read-Host
