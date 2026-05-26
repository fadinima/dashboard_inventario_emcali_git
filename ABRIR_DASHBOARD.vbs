
' ============================================================
' EMCALI — Dashboard Cobertura Inventarios
' Este script arranca la app sin mostrar ventana negra
' y abre el navegador automáticamente
' ============================================================

Dim carpeta, python, url, shell

' Carpeta donde está este archivo
carpeta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' URL del dashboard
url = "http://127.0.0.1:5000/dashboard_uga/acceso"

Set shell = CreateObject("WScript.Shell")

' Verificar si ya está corriendo (intentar abrir navegador directo)
' Arrancar Python en segundo plano sin ventana negra
shell.Run "python """ & carpeta & "\app.py""", 0, False

' Esperar 3 segundos para que Flask arranque
WScript.Sleep 3000

' Abrir el navegador
shell.Run url

Set shell = Nothing
