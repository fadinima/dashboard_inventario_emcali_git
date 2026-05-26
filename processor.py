import os
import pythoncom
import win32com.client as win32


def generar_archivo_limpio(ruta_xlsb):
    """
    Abre el XLSB usando Excel REAL,
    recalcula formulas SAP y genera
    un XLSX limpio para la dashboard.
    """

    print("=== INICIANDO LIMPIEZA XLSB ===")

    # NECESARIO para Flask + Windows + Excel COM
    pythoncom.CoInitialize()

    excel = None
    wb = None

    try:
        # Abrir Excel real
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        print("Excel iniciado")

        ruta_xlsb = os.path.abspath(ruta_xlsb)

        # Abrir archivo SAP
        wb = excel.Workbooks.Open(ruta_xlsb)

        print("Archivo abierto")

        # Recalcular TODO (formulas SAP)
        excel.CalculateFullRebuild()

        print("Formulas recalculadas")

        # Crear nombre archivo limpio
        carpeta = os.path.dirname(ruta_xlsb)
        nombre = os.path.splitext(os.path.basename(ruta_xlsb))[0]

        ruta_limpia = os.path.join(
            carpeta,
            f"{nombre}_LIMPIO.xlsx"
        )

        # Guardar como XLSX limpio
        wb.SaveAs(ruta_limpia, FileFormat=51)  # 51 = XLSX

        print("Archivo limpio generado:", ruta_limpia)

        wb.Close(False)
        excel.Quit()

        return ruta_limpia

    except Exception as e:
        print("ERROR:", e)
        raise e

    finally:
        try:
            if wb:
                wb.Close(False)
        except:
            pass

        try:
            if excel:
                excel.Quit()
        except:
            pass

        pythoncom.CoUninitialize()