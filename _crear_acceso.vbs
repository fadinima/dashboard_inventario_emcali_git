Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = oWS.SpecialFolders("Desktop") & "\Dashboard EMCALI.url"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "http://192.168.1.54:5000/dashboard_uga"
oLink.Save
MsgBox "Acceso directo creado en el escritorio.", 64, "EMCALI Dashboard"
