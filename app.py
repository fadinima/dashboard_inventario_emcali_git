"""
Dashboard Cobertura Inventarios EMCALI
pip install flask pyxlsb pandas openpyxl
python app_claude.py  ->  http://TU-IP:5000
PIN por defecto: emcali2024
"""
import os, json, socket, traceback, glob
from datetime import datetime
from flask import Flask, request, redirect, render_template_string, session

PIN_CARGA = "emcali2024"   # PIN fijo de respaldo
PUERTO    = 5000
SECRET    = "emcali_xk9_2024"
PREFIJO   = "dashboard_uga"

# ── Usuarios ──────────────────────────────────
# Roles: admin (carga archivos + gestiona usuarios) | viewer (solo visualiza)
# Preparado para reemplazar por LDAP/Active Directory
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_usuarios.json")

def cargar_usuarios():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    # Usuarios por defecto si no existe el archivo
    default = {
        "admin": {"password": "emcali2024", "rol": "admin", "nombre": "Administrador", "gerencia": "TODAS"},
        "viewer": {"password": "emcali123",  "rol": "viewer","nombre": "Visualizador",  "gerencia": "TODAS"},
    }
    guardar_usuarios(default)
    return default

def guardar_usuarios(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def hash_pwd(pwd):
    import hashlib
    return hashlib.sha256(pwd.encode()).hexdigest()

def verificar_usuario(username, password):
    users = cargar_usuarios()
    u = users.get(username.lower().strip())
    if not u: return None
    pwd_ok = (u["password"] == password) or (u["password"] == hash_pwd(password))
    return u if pwd_ok else None

def usuario_actual():
    return session.get("usuario")

def requiere_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario"):
            return redirect("/dashboard_uga/login")
        return f(*args, **kwargs)
    return decorated

def requiere_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        u = session.get("usuario")
        if not u:
            return redirect("/dashboard_uga/login")
        if u.get("rol") != "admin":
            return "Acceso denegado — solo administradores.", 403
        return f(*args, **kwargs)
    return decorated

app = Flask(__name__)
app.secret_key = SECRET

DIR   = os.path.dirname(os.path.abspath(__file__))
UDIR  = os.path.join(DIR, "_uploads");   os.makedirs(UDIR, exist_ok=True)
HDIR  = os.path.join(DIR, "_historial"); os.makedirs(HDIR, exist_ok=True)
DJSON = os.path.join(DIR, "_data.json")
DIAG  = os.path.join(DIR, "_diag.json")
ERR_F = os.path.join(DIR, "_error.txt")

def guardar_error(msg):
    open(ERR_F, "w", encoding="utf-8").write(msg)

def leer_error():
    if os.path.exists(ERR_F):
        e = open(ERR_F, encoding="utf-8").read(); os.remove(ERR_F); return e
    return ""

def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

# ── PIN Temporal ──────────────────────────────
import random, string
_pin_temporal = {"pin": None, "expira": None}

def generar_pin_temporal():
    """Genera un PIN de 6 dígitos válido por 24 horas."""
    pin = "".join(random.choices(string.digits, k=6))
    from datetime import timedelta
    _pin_temporal["pin"] = pin
    _pin_temporal["expira"] = datetime.now() + timedelta(hours=24)
    return pin

def pin_temporal_activo():
    """Retorna el PIN temporal si está vigente."""
    if _pin_temporal["pin"] and _pin_temporal["expira"]:
        if datetime.now() < _pin_temporal["expira"]:
            return _pin_temporal["pin"]
    return None

def verificar_pin(pin_ingresado):
    """Verifica contra PIN fijo O temporal."""
    if pin_ingresado == PIN_CARGA:
        return True
    pt = pin_temporal_activo()
    if pt and pin_ingresado == pt:
        return True
    return False

# ══════════════════════════════════════════════════
#  HISTORIAL
# ══════════════════════════════════════════════════

def guardar_historial(datos):
    ts  = datetime.now().strftime("%Y%m_%d%H%M%S")
    mes = datetime.now().strftime("%Y-%m")
    periodo = datos.get("periodo","")
    # Clave unica por periodo: si ya existe uno con el mismo periodo, lo reemplaza
    clave = periodo.replace(" ","_").replace("/","_") if periodo else ts
    datos_h = dict(datos); datos_h["_id"] = ts; datos_h["_mes"] = mes
    # Borrar archivos anteriores con el mismo periodo para evitar duplicados
    for viejo in glob.glob(os.path.join(HDIR, f"*{clave}*.json")):
        try: os.remove(viejo)
        except: pass
    nom = f"{clave}_{ts}.json"
    with open(os.path.join(HDIR, nom), "w", encoding="utf-8") as fp:
        json.dump(datos_h, fp, ensure_ascii=False)
    return ts

def listar_historial():
    archivos = sorted(glob.glob(os.path.join(HDIR, "*.json")), reverse=True)
    lista = []
    for a in archivos:
        try:
            with open(a, encoding="utf-8") as fp: d = json.load(fp)
            lista.append({"id":d.get("_id",""),"mes":d.get("_mes",""),
                          "fecha":d.get("fecha",""),"hoja":d.get("hoja_usada",""),
                          "periodo":d.get("periodo",""),"nombre_archivo":d.get("nombre_archivo",""),
                          "stock":d.get("kpis",{}).get("stock",""),
                          "valor":d.get("kpis",{}).get("importe",""),
                          "cob":d.get("kpis",{}).get("cobertura",""),
                          "refs":d.get("kpis",{}).get("referencias","")})
        except: pass
    return lista

def cargar_historial(id_rep):
    archivos = glob.glob(os.path.join(HDIR, f"*{id_rep}*.json"))
    if not archivos: return None
    with open(archivos[0], encoding="utf-8") as fp: return json.load(fp)

def extraer_periodo(filename):
    """Extrae periodo del nombre. Ej: Cierre_30 noviembre -> Cierre 30/11/2025"""
    import re
    meses = {
        "enero":"01","febrero":"02","marzo":"03","abril":"04",
        "mayo":"05","junio":"06","julio":"07","agosto":"08",
        "septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"
    }
    dias_mes = {
        "01":"31","02":"28","03":"31","04":"30","05":"31","06":"30",
        "07":"31","08":"31","09":"30","10":"31","11":"30","12":"31"
    }
    fn = filename.lower()
    anio_m = re.search("20[0-9][0-9]", fn)
    anio = anio_m.group() if anio_m else str(datetime.now().year)
    for m_key, m_num in meses.items():
        if m_key in fn:
            pat = re.search("[0-9]{1,2}" + m_key, fn.replace(" ",""))
            if not pat:
                pat = re.search(m_key + "[0-9]{1,2}", fn.replace(" ",""))
            if pat:
                dia = re.search("[0-9]{1,2}", pat.group()).group().zfill(2)
            else:
                dia = dias_mes[m_num]
            return "Cierre " + dia + "/" + m_num + "/" + anio
    return os.path.splitext(filename)[0].replace("_"," ")

# ══════════════════════════════════════════════════
#  LEER HOJAS
# ══════════════════════════════════════════════════

def leer_todas_las_hojas(path, ext):
    hojas = {}
    if ext == ".xlsb":
        try:
            from pyxlsb import open_workbook
        except ImportError:
            raise RuntimeError("Falta pyxlsb  ->  pip install pyxlsb")
        with open_workbook(path) as wb:
            for sname in wb.sheets:
                with wb.get_sheet(sname) as sh:
                    headers = None; rows = []
                    for row in sh.rows():
                        vals = [c.v for c in row]
                        if not any(v not in (None,"",0) for v in vals): continue
                        if headers is None:
                            if any(isinstance(v,str) and len(str(v).strip())>1 for v in vals):
                                headers=[str(v).strip() if v is not None else "" for v in vals]
                        else:
                            rows.append(dict(zip(headers,vals)))
                    if headers and rows: hojas[sname]=(headers,rows)
    else:
        import pandas as pd
        eng = "openpyxl" if ext in (".xlsx",".xlsm") else None
        xl  = pd.ExcelFile(path,engine=eng) if eng else pd.ExcelFile(path)
        for sname in xl.sheet_names:
            try:
                df = pd.read_excel(xl,sheet_name=sname,header=None)
                hdr_row=None
                for i,row in df.iterrows():
                    vals=[str(v).strip() for v in row if str(v).strip() not in ("","nan","None")]
                    if len(vals)>=3 and sum(1 for v in vals if not _es_numero(v))>=2:
                        hdr_row=i; break
                if hdr_row is None: continue
                headers=[str(v).strip() if str(v).strip() not in ("nan","None") else "" for v in df.iloc[hdr_row]]
                data_df=df.iloc[hdr_row+1:].copy(); data_df.columns=headers; data_df=data_df.fillna("")
                rows=data_df.to_dict("records")
                rows=[r for r in rows if any(str(v).strip() not in ("","nan","None") for v in r.values())]
                if headers and rows: hojas[sname]=(headers,rows)
            except: pass
    return hojas

def fmt_cob(dias):
    """Cobertura ejecutiva rangos EMCALI (historico 1277 dias, min=30d, max=360d)."""
    if not dias or dias <= 0: return "Sin consumo"
    if dias > 540: return ">18 meses sin mov"
    if dias > 360: return f"{int(dias)} dias (12-18m)"
    if dias > 180: return f"{int(dias)} dias (6-12m)"
    if dias > 30:  return f"{int(dias)} dias (normal)"
    return f"{int(dias)} dias (bajo stock)"

def _es_numero(v):
    try: float(str(v).replace(",","").replace("%","")); return True
    except: return False

def leer_resumen(path, ext):
    """Lee hoja Resumen del SAP: edad salida y edad entrada exactas."""
    try:
        if ext == ".xlsb":
            from pyxlsb import open_workbook
            with open_workbook(path) as wb:
                if "Resumen" not in wb.sheets: return None
                with wb.get_sheet("Resumen") as sh:
                    filas = [[c.v for c in row] for row in sh.rows()]
        else:
            import pandas as pd
            eng = "openpyxl" if ext in (".xlsx",".xlsm") else None
            df = pd.read_excel(path, sheet_name="Resumen", header=None, engine=eng)
            filas = df.values.tolist()
        salida = []; entrada = []
        for i, fila in enumerate(filas):
            vals = [v for v in fila if v not in (None, "", 0)]
            if not vals: continue
            first = str(vals[0]).strip().lower()
            tgt = salida if "edad salida" in first else (entrada if "edad entrada" in first else None)
            if tgt is None: continue
            for j in range(i + 1, min(i + 8, len(filas))):
                rv = [v for v in filas[j] if v not in (None, "")]
                if not rv: continue
                lbl = str(rv[0]).strip()
                if "total" in lbl.lower() or "valores" in lbl.lower(): continue
                nums = [float(v) for v in rv[1:] if isinstance(v, (int, float))]
                if nums:
                    tgt.append({"categoria": lbl, "referencias": int(nums[0]) if len(nums)>0 else 0,
                                "stock": int(nums[1]) if len(nums)>1 else 0,
                                "valor": float(nums[2]) if len(nums)>2 else 0.0})
        return {"salida": salida, "entrada": entrada} if (salida or entrada) else None
    except Exception as e:
        print(f"[leer_resumen] {e}")
    return None


# ══════════════════════════════════════════════════
#  DETECTAR COLUMNAS
# ══════════════════════════════════════════════════

CAMPOS = {
    "material":      ["producto","material","matnr","articulo","cod mat","referencia","concatena"],
    "descripcion":   ["descripci","descrip","texto breve","nombre mat"],
    "gerencia":      ["gerencia"],
    "centro":        ["centro","plant","werks"],
    "almacen":       ["almacen"],
    "nombre_centro": ["denominaci","denom centro","nombre centro","nombre unidad","desc centro","nombre almac","nombre plant"],
    "grupo":         ["grupo articul","grupo art","grupo mat","tipo mat","clase mat","cod grupo"],
    "nombre_grupo":  ["nombre grupo articulos","nombre grupo","desc grupo","denominacion grupo","descrip grupo","nombre clase","desc clase","denom grupo","denom art","denominac","texto grupo"],
    "referencias":   ["referencia","ref.","nro ref","num ref","num. ref"],
    "stock":         ["stock","libre utiliz","cantidad","ctd.","qty"],
    "importe":       ["valor total","v/total","importe","valor stock","total stock","importe ml"],
    "salidas":       ["salidas","consumo","cant sal","salida"],
    "val_salidas":   ["valor sal","importe sal","v/salida"],
    "cobertura":     ["cobertura","cob inv","cobert"],
    "dias_inv":      ["dias de inventario","dias inventario","dias inv","dias_inventario"],
    "conca_centro":  ["conca centro almacen","conca centro","centro almacen","concacentro"],
    "rotacion":      ["rotaci","rotation"],
    "participacion": ["participac","particip"],
}

def puntaje_hoja(headers):
    score=0
    for campo,kws in CAMPOS.items():
        for kw in kws:
            if any(kw.lower() in h.lower() for h in headers): score+=1; break
    return score

def detectar_cols(headers):
    def b(*kws):
        for kw in kws:
            for h in headers:
                if isinstance(h, str) and kw.lower() in h.lower(): return h
        return None
    imp_col = b(*CAMPOS["importe"])
    val_sal_col = None
    for kw in CAMPOS["val_salidas"]:
        for h in headers:
            if kw.lower() in h.lower() and h != imp_col: val_sal_col=h; break
        if val_sal_col: break
    # Busqueda especial nombre_grupo — busca columna con nombre Y grupo
    def b_grupo_nombre():
        for h in headers:
            hl = h.lower().strip()
            if "nombre" in hl and "grupo" in hl:
                return h
        # Segunda pasada: columnas que empiecen con "nombre"
        for h in headers:
            hl = h.lower().strip()
            if hl.startswith("nombre") and len(hl) > 6:
                return h
        return None

    return {
        "material":      b(*CAMPOS["material"]),
        "descripcion":   b(*CAMPOS["descripcion"]),
        "gerencia":      b(*CAMPOS["gerencia"]),
        "centro":        b(*CAMPOS["centro"]),
        "nombre_centro": b(*CAMPOS["nombre_centro"]),
        "grupo":         b(*CAMPOS["grupo"]),
        "nombre_grupo":  b_grupo_nombre(),
        "referencias":   b(*CAMPOS["referencias"]),
        "stock":         b(*CAMPOS["stock"]),
        "importe":       imp_col,
        "salidas":       b(*CAMPOS["salidas"]),
        "val_salidas":   val_sal_col,
        "cobertura":     b(*CAMPOS["cobertura"]),
        "dias_inv":      b(*CAMPOS["dias_inv"]),
        "conca_centro":  b(*CAMPOS["conca_centro"]),
        "almacen":       b(*CAMPOS.get("almacen",[])) if CAMPOS.get("almacen") else None,
        "rotacion":      b(*CAMPOS["rotacion"]),
        "participacion": b(*CAMPOS["participacion"]),
    }

def mejor_hoja(hojas):
    mejor=None; mejor_score=0; mejor_nombre=""
    for nombre,(headers,rows) in hojas.items():
        sc=puntaje_hoja(headers)
        if sc>mejor_score: mejor_score=sc; mejor=(headers,rows); mejor_nombre=nombre
    return mejor_nombre, mejor

# ══════════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════════

def sf(v):
    try:
        if v is None or str(v).strip() in ("","nan","None","#N/A","-","0,00"): return 0.0
        s=str(v).replace(",",".").replace("$","").replace(" ","").replace("\xa0","").replace("%","")
        partes=s.split(".")
        if len(partes)>2: s="".join(partes[:-1])+"."+partes[-1]
        return float(s)
    except: return 0.0

def cobd(s,sal,h=1095):
    try: return round(h*float(s)/float(sal),2) if float(sal)>0 else 0.0
    except: return 0.0

def fmt(n):
    if n>=1e12: return "%.1f B"%(n/1e12)
    if n>=1e9:  return "%.1f B"%(n/1e9)
    if n>=1e6:  return "%.1f M"%(n/1e6)
    if n>=1e3:  return "%.1f K"%(n/1e3)
    return "%.0f"%n

def _nom(val, fallback):
    v = str(val).strip()
    return v if v and v.lower() not in ("nan","none","") else fallback

# ══════════════════════════════════════════════════
#  PROCESAR
# ══════════════════════════════════════════════════

def procesar(headers, rows, cols, hoja_nombre, nombre_archivo=''):
    H = 1095
    recs = []
    for r in rows:
        mat   = str(r.get(cols.get("material")      or "_","") or "").strip()
        desc  = str(r.get(cols.get("descripcion")   or "_","") or "").strip()
        ger   = str(r.get(cols.get("gerencia")      or "_","") or "").strip() or "GENERAL"
        # Usar conca centro+almacen como clave real de unidad
        _conca = str(r.get(cols.get("conca_centro") or "_","") or "").strip()
        _cen_code = str(r.get(cols.get("centro") or "_","") or "").strip()
        _alm_code = str(r.get(cols.get("almacen") or "_","") or "").strip() if cols.get("almacen") else ""
        cen = _conca if _conca and _conca != "nan" else (_cen_code + "_" + _alm_code if _alm_code else _cen_code)
        cen = cen.strip().upper() or "SIN CLASIFICAR"
        den   = str(r.get(cols.get("nombre_centro") or "_","") or "").strip()
        grp   = str(r.get(cols.get("grupo")         or "_","") or "").strip().upper() or "SIN GRUPO"
        ngrp  = str(r.get(cols.get("nombre_grupo")  or "_","") or "").strip()
        refs  = sf(r.get(cols.get("referencias") or "_")) or 1  # 1 fila = 1 referencia
        stk   = sf(r.get(cols.get("stock")       or "_"))
        imp   = sf(r.get(cols.get("importe")     or "_"))
        sal   = sf(r.get(cols.get("salidas")     or "_"))
        vsal  = sf(r.get(cols.get("val_salidas") or "_")) if cols.get("val_salidas") else 0.0
        # Preferir dias_inv (SAP exact) over cobertura (calculated)
        cob_v = sf(r.get(cols.get("dias_inv") or "_")) if cols.get("dias_inv") else 0.0
        if cob_v == 0:
            cob_v = sf(r.get(cols.get("cobertura") or "_")) if cols.get("cobertura") else 0.0
        rot   = sf(r.get(cols.get("rotacion")    or "_")) if cols.get("rotacion") else 0.0
        part  = sf(r.get(cols.get("participacion") or "_")) if cols.get("participacion") else 0.0

        cen_low = cen.lower()
        if any(x in cen_low for x in ("result","grand total","subtotal")): continue
        if cen_low in ("","nan","none","sin clasificar") and mat in ("","nan","None"): continue
        if stk==0 and imp==0 and refs==0 and sal==0: continue
        if cob_v==0 and stk>0 and sal>0: cob_v=cobd(stk,sal,H)

        recs.append({"mat":mat,"desc":desc,"ger":ger,"cen":cen,"den":den,
                     "grp":grp,"ngrp":ngrp,"refs":refs,
                     "stk":stk,"imp":imp,"sal":sal,"vsal":vsal,
                     "cob":cob_v,"rot":rot,"part":part})

    if not recs: return None

    total_stk = sum(r["stk"] for r in recs)
    total_imp = sum(r["imp"] for r in recs)
    total_sal = sum(r["sal"] for r in recs)
    total_ref = sum(r["refs"] for r in recs)

    if total_stk==0 and total_ref>0:
        for r in recs: r["stk"]=r["refs"]
        total_stk=total_ref

    cob_global = cobd(total_stk,total_sal,H) if total_sal>0 else (
        sum(r["cob"] for r in recs)/len(recs) if recs else 0)

    kpis = {
        "stock":       fmt(total_stk),
        "importe":     fmt(total_imp),
        "salidas":     fmt(total_sal),
        "referencias": str(len(recs)),
        "cobertura":   "{:,.0f}".format(cob_global),
        "sin_mov":     str(sum(1 for r in recs if r["sal"]==0)),
    }

    # ── Por Centro ────────────────────────────────
    centros = {}
    for r in recs:
        c = r["cen"]
        if c not in centros:
            centros[c]={"stk":0,"imp":0,"sal":0,"refs":0,"cob_sum":0,"n":0,
                        "nombre":_nom(r["den"],c)}
        centros[c]["stk"]+=r["stk"]; centros[c]["imp"]+=r["imp"]
        centros[c]["sal"]+=r["sal"]; centros[c]["refs"]+=r["refs"]
        if r["cob"]>0: centros[c]["cob_sum"]+=r["cob"]; centros[c]["n"]+=1

    # Resolve duplicate nombres: add conca suffix so each entry is unique
    nom_seen = {}
    for k, v in centros.items():
        n = v["nombre"]
        if n not in nom_seen:
            nom_seen[n] = 0
        nom_seen[n] += 1
    nom_count = {n: c for n, c in nom_seen.items() if c > 1}
    for k, v in centros.items():
        if v["nombre"] in nom_count:
            suffix = str(k).replace(".0","").strip()[-5:]
            v["nombre"] = v["nombre"] + f" [{suffix}]"

    cs = sorted(centros.items(), key=lambda x: x[1]["imp"] or x[1]["stk"], reverse=True)
    tabla_c = [{"num":i+1,"nombre":v["nombre"],
                "stock":    "{:,.0f}".format(v["stk"]),
                "importe":  "$ {:,.0f}".format(v["imp"]),
                "salidas":  "{:,.0f}".format(v["sal"]),
                "referencias":"{:,.0f}".format(v["refs"]),
                "cobertura": fmt_cob(H * v["stk"] / v["sal"] if v["sal"] > 0 else 0),
                "cob_dias":  round(H * v["stk"] / v["sal"]) if v["sal"] > 0 else 0}
               for i,(n,v) in enumerate(cs)]

    cl  = [v["nombre"] for _,v in cs[:8]]
    cd  = [round((v["imp"] or v["stk"])/1e6,1) for _,v in cs[:8]]
    sd  = [round(v["stk"]/max(1,total_stk)*100,1) for _,v in cs[:8]]
    en, esm = [], []
    for _,v in cs[:8]:
        sm=round(v["sal"]==0 and 100 or max(0,min(100,100-v["sal"]/max(1,v["stk"])*100)),1)
        esm.append(sm); en.append(round(100-sm,1))

    # ── Por Grupo ─────────────────────────────────
    grps = {}
    for r in recs:
        g   = r["grp"]
        nom = _nom(r["ngrp"], g)
        if g not in grps: grps[g]={"val":0,"nombre":nom}
        grps[g]["val"]+=(r["imp"] or r["stk"])

    gs  = sorted(grps.items(), key=lambda x: x[1]["val"], reverse=True)
    gl  = [v["nombre"] for _,v in gs[:8]]
    gd  = [round(v["val"]/1e6,1) for _,v in gs[:8]]

    # ── Tabla detallada ───────────────────────────
    top  = sorted(recs, key=lambda x: x["imp"] or x["stk"], reverse=True)
    tdet = [{"num":i+1,
             "material":    r["mat"],
             "descripcion": r["desc"],
             "gerencia":    r["ger"],
             "centro":      _nom(r["den"],r["cen"]),
             "grupo":       _nom(r["ngrp"],r["grp"]),
             "stock":       "{:,.0f}".format(r["stk"]),
             "importe":     "$ {:,.0f}".format(r["imp"]),
             "salidas":     "{:,.0f}".format(r["sal"]),
             "val_salidas": "$ {:,.0f}".format(r["vsal"]),
             "cobertura": fmt_cob(r["cob"]),
             "alta":        r["cob"]>2000}
            for i,r in enumerate(top)]

    # Lista de gerencias únicas para el filtro
    gerencias = sorted(set(r["ger"] for r in recs if r["ger"] and r["ger"] != "GENERAL"))

    # Totales por gerencia para la dona principal (vista TODAS)
    ger_totals = {}
    for r in recs:
        g = r["ger"]
        if g not in ger_totals:
            ger_totals[g] = {"imp": 0, "stk": 0, "sal": 0}
        ger_totals[g]["imp"] += r["imp"]
        ger_totals[g]["stk"] += r["stk"]
        ger_totals[g]["sal"] += r["sal"]
    ger_sorted = sorted(ger_totals.items(), key=lambda x: x[1]["imp"], reverse=True)
    cl_ger = [g for g,_ in ger_sorted]
    cd_ger = [round(v["imp"]/1e6, 1) for _,v in ger_sorted]

    def _calc_edad(recs_g):
        cs = [{"cat":"a) Normal","r":0,"s":0,"v":0},{"cat":"b) Sin mov salida >6m","r":0,"s":0,"v":0},
              {"cat":"c) Sin mov salida >12m","r":0,"s":0,"v":0},{"cat":"d) Sin salidas en SAP","r":0,"s":0,"v":0}]
        ce = [{"cat":"a) Con entradas recientes","r":0,"s":0,"v":0},{"cat":"b) Sin mov entrada >6m","r":0,"s":0,"v":0},
              {"cat":"c) Sin mov entrada >12m","r":0,"s":0,"v":0},{"cat":"d) Sin entradas en SAP","r":0,"s":0,"v":0}]
        for r in recs_g:
            si = 3 if r["sal"]==0 else (2 if r["cob"]>H*4 else (1 if r["cob"]>H*2 else 0))
            ei = 3 if (r["sal"]==0 and r["stk"]>0) else (2 if r["cob"]>H*4 else (1 if r["cob"]>H*2 else 0))
            for c,i in [(cs,si),(ce,ei)]:
                c[i]["r"]+=1; c[i]["s"]+=r["stk"]; c[i]["v"]+=r["imp"]
        def conv(cats): return [{"categoria":c["cat"],"referencias":c["r"],"stock":c["s"],"valor":c["v"]} for c in cats if c["r"]>0]
        return {"salida":conv(cs),"entrada":conv(ce)}

    edad_por_ger = {"TODAS": _calc_edad(recs)}
    for ger in gerencias:
        edad_por_ger[ger] = _calc_edad([r for r in recs if r["ger"]==ger])

    periodo = extraer_periodo(nombre_archivo) if nombre_archivo else ""
    return {
        "kpis":           kpis,
        "tabla_centros":  tabla_c,
        "tabla_detallada":tdet,
        "chart":          {"cl":cl,"cd":cd,"sd":sd,"gl":gl,"gd":gd,"el":cl,"en":en,"esm":esm,"cl_ger":cl_ger,"cd_ger":cd_ger},
        "fecha":          datetime.now().strftime("%d/%m/%Y %H:%M"),
        "hist":           H,
        "hoja_usada":     hoja_nombre,
        "periodo":        periodo,
        "nombre_archivo": os.path.splitext(nombre_archivo)[0].replace("_"," ") if nombre_archivo else hoja_nombre,
        "gerencias":      gerencias,
        "edad_por_ger":   edad_por_ger,
    }

# ══════════════════════════════════════════════════
#  TEMPLATES
# ══════════════════════════════════════════════════

LOGIN_T = r"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Acceso — EMCALI Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#1A1F2E;color:#E8ECF4;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.w{max-width:420px;width:100%;text-align:center}
.logo{font-size:18px;font-weight:900;color:#003B7A;background:white;padding:8px 18px;border-radius:8px;display:inline-block;margin-bottom:20px}
h1{font-size:22px;font-weight:900;text-transform:uppercase;margin-bottom:6px;color:#E8ECF4}
.sub{color:#8A94B2;font-size:12px;margin-bottom:24px}
.card{background:rgba(255,255,255,.04);border:1px solid #3D4562;border-radius:14px;padding:28px;text-align:left}
.lbl{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A94B2;margin-bottom:6px;display:block}
.inp{width:100%;padding:10px 14px;background:#2D3347;border:1px solid #3D4562;border-radius:8px;color:#E8ECF4;font-size:14px;outline:none;margin-bottom:14px}
.inp:focus{border-color:#00C5D4}
.btn{background:linear-gradient(135deg,#0057B8,#003B7A);color:white;border:none;width:100%;padding:13px;border-radius:8px;font-size:15px;font-weight:700;text-transform:uppercase;cursor:pointer;margin-top:4px}
.btn:hover{background:linear-gradient(135deg,#00C5D4,#0057B8)}
.err{background:rgba(232,0,61,.1);border:1px solid rgba(232,0,61,.3);border-radius:8px;padding:10px;font-size:12px;color:#FF4B6E;margin-bottom:14px}
</style></head><body><div class="w">
<div class="logo">EMCALI</div>
<h1>Dashboard Inventarios</h1>
<p class="sub">Gerencia de Energía — UGA Energía</p>
<div class="card">
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="POST" action="/dashboard_uga/login">
<label class="lbl">Usuario</label>
<input class="inp" type="text" name="username" placeholder="Usuario..." autocomplete="off" autofocus>
<label class="lbl">Contraseña</label>
<input class="inp" type="password" name="password" placeholder="Contraseña...">
<button type="submit" class="btn">&#128274; Ingresar</button>
</form>
</div></div></body></html>"""

USUARIOS_T = r"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Gestión Usuarios — EMCALI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#1A1F2E;color:#E8ECF4;padding:30px;font-size:13px}
h1{color:#00C5D4;margin-bottom:6px;font-size:22px;font-weight:900;text-transform:uppercase;letter-spacing:1px}
.sub{color:#8A94B2;font-size:12px;margin-bottom:24px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:1000px}
.card{background:rgba(255,255,255,.04);border:1px solid #3D4562;border-radius:12px;padding:20px}
.ch{font-family:Arial,sans-serif;font-size:13px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#00C5D4;margin-bottom:16px}
.lbl{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A94B2;margin-bottom:5px;display:block;margin-top:10px}
.inp{width:100%;padding:8px 12px;background:#2D3347;border:1px solid #3D4562;border-radius:7px;color:#E8ECF4;font-size:13px;outline:none;margin-bottom:4px}
.inp:focus{border-color:#00C5D4}
select.inp option{background:#2D3347}
.btn{padding:9px 20px;border-radius:7px;font-size:12px;font-weight:700;text-transform:uppercase;cursor:pointer;border:none}
.btn-p{background:#003B7A;color:white;width:100%;margin-top:12px}.btn-p:hover{background:#0057B8}
.btn-del{background:rgba(232,0,61,.1);border:1px solid rgba(232,0,61,.3);color:#FF4B6E;padding:5px 12px;font-size:11px}
.btn-nav{background:rgba(0,197,212,.1);border:1px solid #00C5D4;color:#00C5D4;text-decoration:none;display:inline-block;padding:8px 18px;border-radius:7px;font-size:12px;font-weight:700;text-transform:uppercase}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:#003B7A;color:white;padding:8px 12px;font-size:11px;text-transform:uppercase;text-align:left}
tbody tr{border-bottom:1px solid #3D4562}tbody tr:hover{background:rgba(0,197,212,.05)}
tbody td{padding:8px 12px}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:10px;font-weight:700}
.b-admin{background:rgba(245,197,24,.15);color:#F5C518;border:1px solid rgba(245,197,24,.4)}
.b-viewer{background:rgba(0,197,212,.1);color:#00C5D4;border:1px solid rgba(0,197,212,.3)}
.ok{background:rgba(0,176,91,.1);border:1px solid rgba(0,176,91,.3);border-radius:8px;padding:10px 14px;font-size:12px;color:#00B05B;margin-bottom:16px}
.err{background:rgba(232,0,61,.1);border:1px solid rgba(232,0,61,.3);border-radius:8px;padding:10px 14px;font-size:12px;color:#FF4B6E;margin-bottom:16px}
.nav{display:flex;gap:10px;margin-top:20px;max-width:1000px}
</style></head><body>
<h1>&#128101; Gestión de Usuarios</h1>
<p class="sub">Administra los usuarios con acceso al dashboard.</p>
{% if msg %}<div class="{{ 'ok' if ok else 'err' }}">{{ msg }}</div>{% endif %}
<div class="grid">
<!-- Tabla usuarios -->
<div class="card" style="grid-column:1/-1">
<div class="ch">Usuarios Registrados</div>
<table><thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Gerencia</th><th>Acción</th></tr></thead>
<tbody>{% for u in usuarios %}
<tr>
<td style="font-weight:600">{{ u.username }}</td>
<td>{{ u.nombre }}</td>
<td><span class="badge {{ 'b-admin' if u.rol=='admin' else 'b-viewer' }}">{{ u.rol }}</span></td>
<td>{{ u.gerencia }}</td>
<td>
  {% if u.username != session_user %}
  <form method="POST" action="/dashboard_uga/usuarios/eliminar" style="display:inline">
    <input type="hidden" name="username" value="{{ u.username }}">
    <button type="submit" class="btn btn-del" onclick="return confirm('¿Eliminar usuario {{ u.username }}?')">&#128465; Eliminar</button>
  </form>
  {% else %}
  <span style="color:#8A94B2;font-size:11px">Usuario actual</span>
  {% endif %}
</td>
</tr>{% endfor %}</tbody></table>
</div>
<!-- Formulario nuevo usuario -->
<div class="card">
<div class="ch">➕ Nuevo Usuario</div>
<form method="POST" action="/dashboard_uga/usuarios/nuevo">
<label class="lbl">Usuario</label>
<input class="inp" type="text" name="username" placeholder="ej: jperez" required>
<label class="lbl">Nombre completo</label>
<input class="inp" type="text" name="nombre" placeholder="ej: Juan Pérez" required>
<label class="lbl">Contraseña</label>
<input class="inp" type="password" name="password" placeholder="Contraseña..." required>
<label class="lbl">Rol</label>
<select class="inp" name="rol">
  <option value="viewer">Viewer — Solo visualiza</option>
  <option value="admin">Admin — Carga archivos y gestiona usuarios</option>
</select>
<label class="lbl">Gerencia</label>
<select class="inp" name="gerencia">
  <option value="TODAS">TODAS — Ve todas las gerencias</option>
  {% for g in gerencias %}<option value="{{ g }}">{{ g }}</option>{% endfor %}
</select>
<button type="submit" class="btn btn-p">&#10003; Crear Usuario</button>
</form>
</div>
<!-- Cambiar contraseña -->
<div class="card">
<div class="ch">&#128274; Cambiar Contraseña</div>
<form method="POST" action="/dashboard_uga/usuarios/cambiar_password">
<label class="lbl">Usuario</label>
<select class="inp" name="username">
  {% for u in usuarios %}<option value="{{ u.username }}">{{ u.username }} ({{ u.nombre }})</option>{% endfor %}
</select>
<label class="lbl">Nueva Contraseña</label>
<input class="inp" type="password" name="password" placeholder="Nueva contraseña..." required>
<button type="submit" class="btn btn-p">&#128274; Cambiar Contraseña</button>
</form>
</div>
</div>
<div class="nav">
<a class="btn-nav" href="/dashboard_uga/dashboard">&#128202; Volver al Dashboard</a>
</div>
</body></html>"""

ADMIN_T = r"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Cargar Reporte - EMCALI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#1A1F2E;color:#E8ECF4;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.w{max-width:520px;width:100%}
.logo{font-size:18px;font-weight:900;color:#003B7A;background:white;padding:8px 18px;border-radius:8px;display:inline-block;margin-bottom:20px}
h1{font-size:26px;font-weight:900;text-transform:uppercase;margin-bottom:6px}
.sub{color:#8A94B2;font-size:13px;margin-bottom:22px;line-height:1.6}
.card{background:rgba(255,255,255,.04);border:1px solid #3D4562;border-radius:14px;padding:28px;margin-top:16px}
.lbl{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A94B2;margin-bottom:6px;display:block}
.inp{width:100%;padding:10px 14px;background:#2D3347;border:1px solid #3D4562;border-radius:8px;color:#E8ECF4;font-size:14px;outline:none;margin-bottom:14px}
.inp:focus{border-color:#00C5D4}
.drop{border:2px dashed #3D4562;border-radius:10px;padding:32px 20px;text-align:center;cursor:pointer;transition:.2s;position:relative;margin-bottom:16px}
.drop:hover{border-color:#00C5D4;background:rgba(0,197,212,.05)}
.drop input{position:absolute;inset:0;opacity:0;cursor:pointer;font-size:0;width:100%;height:100%}
.ic{font-size:40px;margin-bottom:8px}.dt{font-size:15px;color:#00C5D4;font-weight:700;margin-bottom:4px}.ds{font-size:12px;color:#8A94B2}
.fn{margin-top:8px;font-size:12px;color:#00B05B;font-weight:600;min-height:16px}
.btn{background:linear-gradient(135deg,#0057B8,#003B7A);color:white;border:none;width:100%;padding:14px;border-radius:8px;font-size:16px;font-weight:700;text-transform:uppercase;cursor:pointer;transition:.2s;margin-top:4px}
.btn:hover:not(:disabled){background:linear-gradient(135deg,#00C5D4,#0057B8)}.btn:disabled{opacity:.4;cursor:not-allowed}
.err{background:rgba(232,0,61,.1);border:1px solid rgba(232,0,61,.3);border-radius:8px;padding:12px;font-size:12px;color:#FF4B6E;margin-bottom:16px;white-space:pre-wrap}
.tip{background:rgba(0,197,212,.08);border:1px solid rgba(0,197,212,.2);border-radius:8px;padding:10px 14px;font-size:11px;color:#8A94B2;margin-top:14px;line-height:1.6}
.ver{display:flex;align-items:center;justify-content:center;gap:8px;padding:12px;background:rgba(0,176,91,.1);border:1px solid rgba(0,176,91,.3);border-radius:8px;color:#00B05B;font-weight:700;font-size:13px;text-decoration:none;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
.ver:hover{background:rgba(0,176,91,.2)}
.hist{display:block;text-align:center;padding:10px;background:rgba(0,197,212,.05);border:1px solid #3D4562;border-radius:8px;color:#8A94B2;font-size:12px;text-decoration:none}
.hist:hover{color:#00C5D4;border-color:#00C5D4}
</style></head><body><div class="w">
<div class="logo">EMCALI</div>
<h1>Cargar Reporte SAP</h1>
<p class="sub">Solo usuarios autorizados pueden cargar archivos.<br>Los demas funcionarios acceden directamente al dashboard.</p>
{% if tiene_datos %}
<a class="ver" href="/dashboard_uga/dashboard">&#128202; Ver Dashboard Actual</a>
<a class="hist" href="/dashboard_uga/historial">&#128337; Historial de reportes mensuales</a>
{% endif %}
<div class="card">
{% if error %}<div class="err">&#9888; {{ error }}</div>{% endif %}
<form method="POST" action="/dashboard_uga/upload" enctype="multipart/form-data" id="f">
<label class="lbl">&#128274; PIN de autorizacion</label>
<input class="inp" type="password" name="pin" placeholder="Ingresa el PIN..." autocomplete="off" id="pinI">
<label class="lbl">&#128194; Archivo SAP</label>
<div class="drop" id="dz">
<input type="file" name="file" id="fi" accept=".xlsb,.xlsx,.xls,.xlsm" onchange="elegir(this)">
<div class="ic">&#128194;</div>
<div class="dt">Arrastra el archivo aqui</div>
<div class="ds">XLSB &bull; XLSX &bull; XLS &bull; XLSM</div>
<div class="fn" id="fn"></div>
</div>
<button type="submit" class="btn" id="btn" disabled>&#9889; GENERAR DASHBOARD</button>
</form>
<div class="tip">&#128161; El sistema escanea todas las hojas del archivo SAP y elige la mas completa.</div>
</div></div>
<div class="tip">&#128161; El sistema escanea todas las hojas del archivo SAP y elige la mas completa.</div>
</div>

<div class="card" style="margin-top:16px">
<div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A94B2;margin-bottom:12px">&#128273; Codigo de Acceso Temporal (24 horas)</div>
{% if pin_temporal %}
<div style="background:#0D1321;border:2px solid #00C5D4;border-radius:10px;padding:16px;display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
  <div>
    <div style="font-size:11px;color:#8A94B2;margin-bottom:4px">Codigo activo hasta las {{ expira }}</div>
    <div id="pinShow" style="font-size:32px;font-weight:900;color:#00C5D4;letter-spacing:6px;font-family:monospace">{{ pin_temporal }}</div>
  </div>
  <button onclick="copiarPin('{{ pin_temporal }}')" style="background:rgba(0,197,212,.15);border:1px solid #00C5D4;color:#00C5D4;padding:10px 18px;border-radius:8px;font-size:12px;font-weight:700;cursor:pointer;text-transform:uppercase" id="btnCopiar">&#128203; Copiar</button>
</div>
{% endif %}
<button onclick="generarPin()" style="width:100%;background:linear-gradient(135deg,#003B7A,#0057B8);color:white;border:none;padding:12px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;text-transform:uppercase;letter-spacing:1px" id="btnGen">&#9889; Generar Nuevo Codigo Temporal</button>
<div id="pinMsg" style="margin-top:8px;font-size:11px;color:#8A94B2;text-align:center"></div>
</div>
</div>
<script>
function elegir(i){if(i.files.length){document.getElementById("fn").textContent="Listo: "+i.files[0].name;chkBtn();}}
function chkBtn(){var p=document.getElementById("pinI").value.trim();var f=document.getElementById("fi").files.length>0;document.getElementById("btn").disabled=!(p&&f);}
document.getElementById("pinI").addEventListener("input",chkBtn);
document.getElementById("f").addEventListener("submit",function(){document.getElementById("btn").disabled=true;document.getElementById("btn").textContent="Analizando hojas SAP...";});
var dz=document.getElementById("dz");
dz.addEventListener("dragover",function(e){e.preventDefault();dz.style.borderColor="#00C5D4";});
dz.addEventListener("dragleave",function(){dz.style.borderColor="#3D4562";});
dz.addEventListener("drop",function(e){e.preventDefault();dz.style.borderColor="#3D4562";var f=e.dataTransfer.files[0];if(f){var dt=new DataTransfer();dt.items.add(f);document.getElementById("fi").files=dt.files;elegir(document.getElementById("fi"));}});
function generarPin(){
  document.getElementById("btnGen").textContent="Generando...";
  document.getElementById("btnGen").disabled=true;
  fetch("/dashboard_uga/generar_pin",{method:"POST"})
    .then(function(r){return r.json();})
    .then(function(d){
      document.getElementById("btnGen").textContent="&#9889; Generar Nuevo Codigo Temporal";
      document.getElementById("btnGen").disabled=false;
      document.getElementById("pinMsg").innerHTML="&#10003; Codigo generado. Valido por 24 horas. Comparte: <strong style='color:#00C5D4'>"+d.pin+"</strong>";
      setTimeout(function(){location.reload();},1200);
    });
}
function copiarPin(pin){
  navigator.clipboard.writeText(pin).then(function(){
    var b=document.getElementById("btnCopiar");
    b.textContent="&#10003; Copiado!";
    setTimeout(function(){b.textContent="&#128203; Copiar";},2000);
  });
}
</script></body></html>"""

HIST_T = r"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Historial Reportes - EMCALI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#1A1F2E;color:#E8ECF4;padding:30px;font-size:13px}
h1{color:#00C5D4;margin-bottom:6px;font-size:22px;font-weight:900;text-transform:uppercase;letter-spacing:1px}
.sub{color:#8A94B2;font-size:12px;margin-bottom:20px;line-height:1.6}
table{width:100%;max-width:1060px;border-collapse:collapse}
thead th{background:#003B7A;color:white;padding:10px 14px;font-size:11px;text-transform:uppercase;text-align:left;white-space:nowrap}
tbody tr{border-bottom:1px solid #3D4562;transition:.15s}
tbody tr:hover{background:rgba(0,197,212,.06)}
tbody td{padding:10px 14px}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;background:rgba(0,197,212,.15);color:#00C5D4;border:1px solid rgba(0,197,212,.3)}
.badge-actual{background:rgba(0,176,91,.15);color:#00B05B;border-color:rgba(0,176,91,.3)}
.badge-sel{background:rgba(245,197,24,.2);color:#F5C518;border-color:#F5C518}
.val{color:#00C5D4;font-weight:600}
.nav{display:flex;gap:12px;margin-top:24px;flex-wrap:wrap;max-width:1060px}
.btn{padding:10px 22px;border-radius:8px;font-size:12px;font-weight:700;text-transform:uppercase;text-decoration:none;display:inline-block;cursor:pointer;border:none}
.btn-p{background:#003B7A;color:white}.btn-p:hover{background:#0057B8}
.btn-s{background:rgba(255,255,255,.05);border:1px solid #3D4562;color:#8A94B2}.btn-s:hover{color:#00C5D4;border-color:#00C5D4}
.btn-cmp{background:rgba(245,197,24,.15);border:1px solid rgba(245,197,24,.5);color:#F5C518}.btn-cmp:hover{background:rgba(245,197,24,.3)}
.btn-del{background:rgba(232,0,61,.1);border:1px solid rgba(232,0,61,.3);color:#FF4B6E}.btn-del:hover{background:rgba(232,0,61,.25)}
.empty{color:#8A94B2;padding:60px;text-align:center;font-size:14px;border:1px solid #3D4562;border-radius:12px;max-width:1060px}
.chk{width:16px;height:16px;cursor:pointer;accent-color:#F5C518}
.hint{font-size:11px;color:#8A94B2;margin-bottom:12px;max-width:1060px}
/* Modal comparativo */
.modal-bg{display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.8);align-items:center;justify-content:center}
.modal-box{background:#1E2538;border:1px solid #3D4562;border-radius:16px;width:96%;max-width:1100px;max-height:92vh;display:flex;flex-direction:column;box-shadow:0 24px 64px rgba(0,0,0,.8)}
.modal-hdr{background:rgba(245,197,24,.1);border-bottom:1px solid #3D4562;padding:16px 24px;display:flex;align-items:center;border-radius:16px 16px 0 0}
.modal-body{overflow-y:auto;flex:1;padding:20px 24px}
.modal-ftr{padding:12px 24px;border-top:1px solid #3D4562;text-align:right}
.cmp-grid{display:grid;gap:16px}
.cmp-titulo{font-family:'Barlow Condensed',Arial,sans-serif;font-size:13px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#F5C518;margin-bottom:10px}
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
.kpi-c{background:rgba(255,255,255,.04);border:1px solid #3D4562;border-radius:8px;padding:12px;text-align:center}
.kpi-c .kl{font-size:10px;color:#8A94B2;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.kpi-c .kv{font-size:20px;font-weight:800;color:#00C5D4}
.cmp-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
.cmp-table thead th{background:#003B7A;color:white;padding:8px 12px;text-align:left;font-size:11px;text-transform:uppercase}
.cmp-table tbody tr{border-bottom:1px solid rgba(255,255,255,.05)}
.cmp-table tbody td{padding:7px 12px}
.pos{color:#00B05B;font-weight:700}.neg{color:#FF4B6E;font-weight:700}.neu{color:#8A94B2}
</style></head><body>
<h1>&#128337; Historial de Reportes</h1>
<p class="sub">Haz clic en <b>Ver</b> para abrir un reporte. Marca dos periodos y haz clic en <b>Comparar</b> para ver las diferencias.</p>
{% if reportes %}
<div class="hint">&#9745; Selecciona exactamente 2 periodos para comparar</div>
<table>
<thead><tr>
  <th style="width:36px"></th>
  <th>#</th><th>Periodo</th><th>Fecha carga</th>
  <th>Stock</th><th>Valor</th><th>Cobertura</th><th>Items</th>
  <th>Acciones</th>
</tr></thead>
<tbody>{% for r in reportes %}
<tr id="row-{{ r.id }}">
  <td><input type="checkbox" class="chk" value="{{ r.id }}" onchange="selCheck(this,'{{ r.periodo or r.mes }}')"></td>
  <td style="color:#8A94B2;font-size:11px">{{ loop.index }}</td>
  <td><span class="badge {{ 'badge-actual' if loop.index==1 else '' }}" id="badge-{{ r.id }}">{{ r.periodo or r.mes }}</span></td>
  <td style="font-size:11px;color:#8A94B2">{{ r.fecha }}</td>
  <td>{{ r.stock }}</td>
  <td class="val">{{ r.valor }}</td>
  <td>{{ r.cob }}</td>
  <td>{{ r.refs }}</td>
  <td style="display:flex;gap:6px;align-items:center">
    <a href="/historial/{{ r.id }}" style="color:#00C5D4;font-size:11px;font-weight:700;text-decoration:none;padding:4px 10px;border:1px solid rgba(0,197,212,.3);border-radius:5px">Ver &rsaquo;</a>
    <button onclick="eliminar('{{ r.id }}','{{ r.periodo or r.mes }}')" style="background:rgba(232,0,61,.1);border:1px solid rgba(232,0,61,.3);color:#FF4B6E;padding:4px 10px;border-radius:5px;font-size:11px;font-weight:700;cursor:pointer">&#128465;</button>
  </td>
</tr>{% endfor %}</tbody></table>
<div class="nav">
  <a class="btn btn-p" href="/dashboard_uga/dashboard">&#128202; Dashboard Actual</a>
  <a class="btn btn-s" href="/dashboard_uga/cargar">&#128194; Cargar Nuevo</a>
  <select id="selGerCmp" style="background:#2D3347;border:1px solid #3D4562;color:#E8ECF4;padding:7px 14px;border-radius:7px;font-size:12px;outline:none;cursor:pointer;margin-right:8px">
  <option value="TODAS">Todas las gerencias</option>
  <option value="Gerencia Energia">Gerencia Energia</option>
  <option value="Gerencia Acueducto - Alcantarillado">Gerencia Acueducto</option>
  <option value="Gerencia Telecomunicaciones">Gerencia Telecom.</option>
  <option value="Corporativo">Corporativo</option>
</select>
<button class="btn btn-cmp" id="btnCmp" onclick="comparar()" disabled>&#9878; Comparar Periodos Seleccionados</button>
</div>
{% else %}
<div class="empty">Aun no hay reportes.<br><br>Carga el primer archivo SAP para comenzar el historial.</div>
<div class="nav"><a class="btn btn-s" href="/dashboard_uga/cargar">&#128194; Cargar Nuevo</a></div>
{% endif %}

<!-- MODAL COMPARATIVO -->
<div class="modal-bg" id="modalCmp">
<div class="modal-box">
  <div class="modal-hdr">
    <span style="font-size:16px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#F5C518">&#9878; Comparativo de Periodos</span>
    <button onclick="cerrarCmp()" style="margin-left:auto;background:rgba(255,255,255,.08);border:1px solid #3D4562;color:#E8ECF4;width:34px;height:34px;border-radius:8px;font-size:20px;cursor:pointer">&times;</button>
  </div>
  <div class="modal-body" id="cmpBody">Cargando...</div>
  <div class="modal-ftr">
    <button onclick="cerrarCmp()" style="background:linear-gradient(135deg,#0057B8,#003B7A);color:white;border:none;padding:9px 24px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;text-transform:uppercase">Cerrar</button>
  </div>
</div></div>

<script>
var sel = [];
function selCheck(cb, label){
  if(cb.checked){
    if(sel.length>=6){cb.checked=false;alert("Maximo 6 periodos.");return;}
    sel.push({id:cb.value,label:label});
  } else {
    sel=sel.filter(function(x){return x.id!==cb.value;});
  }
  var _n=sel.length;document.getElementById("btnCmp").disabled=_n<2;document.getElementById("btnCmp").textContent=_n>=2?"Comparar "+_n+" periodos":"Comparar Periodos";
}

function eliminar(id, label){
  if(!confirm("¿Eliminar el reporte \""+label+"\"?\nEsta accion no se puede deshacer.")) return;
  fetch("/historial/eliminar/"+id, {method:"POST"})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        var row=document.getElementById("row-"+id);
        if(row) row.remove();
        sel=sel.filter(function(x){return x.id!==id;});
        document.getElementById("btnCmp").disabled=sel.length<2;
      } else { alert("Error al eliminar: "+d.error); }
    });
}

function comparar(){
  if(sel.length<2) return;
  document.getElementById("modalCmp").style.display="flex";
  document.getElementById("cmpBody").innerHTML="<div style='text-align:center;padding:40px;color:#8A94B2'>Cargando...</div>";
  var _gCmp=document.getElementById("selGerCmp")?document.getElementById("selGerCmp").value:"TODAS";
  Promise.all(sel.map(function(s){
    var _u="/historial/datos/"+s.id+(_gCmp&&_gCmp!="TODAS"?"?gerencia="+encodeURIComponent(_gCmp):"");
    return fetch(_u).then(function(r){return r.json();});
  })).then(function(res){
    var periodos=sel.map(function(s){return s.label;});
    function dif(va,vb){
      var na=parseFloat(String(va).replace(/[^0-9.\-]/g,"")||0);
      var nb=parseFloat(String(vb).replace(/[^0-9.\-]/g,"")||0);
      if(isNaN(na)||isNaN(nb)||!nb) return '<span style="color:#8A94B2">-</span>';
      var p=((na-nb)/Math.abs(nb)*100).toFixed(1);
      var col=na>=nb?"#00B05B":"#FF4B6E";
      return '<span style="color:'+col+'">'+(na>=nb?"&#9650;":"&#9660;")+Math.abs(p)+'%</span>';
    }
    var h='<div style="overflow-x:auto"><table class="cmp-table"><thead><tr><th>Indicador</th>';
    periodos.forEach(function(p,i){
      h+='<th style="text-align:right;color:#F5C518">'+p+'</th>';
      if(i>0) h+='<th style="text-align:right;font-size:10px;color:#8A94B2">Var.</th>';
    });
    h+='</tr></thead><tbody>';
    [["stock","&#128230; Stock"],["importe","&#128178; Valor"],["cobertura","&#128197; Cobertura"],
     ["salidas","&#128228; Salidas"],["sin_mov","&#9888; Sin Mov."]].forEach(function(k){
      h+='<tr><td style="color:#00C5D4;font-weight:700">'+k[1]+'</td>';
      res.forEach(function(r,i){
        h+='<td style="text-align:right">'+r.kpis[k[0]]+'</td>';
        if(i>0) h+='<td style="text-align:right">'+dif(r.kpis[k[0]],res[0].kpis[k[0]])+'</td>';
      });
      h+='</tr>';
    });
    h+='</tbody></table></div>';
    h+='<div class="cmp-titulo" style="margin-top:16px">&#127963; Comparativo por Centro</div>';
    h+='<div style="overflow-x:auto"><table class="cmp-table"><thead><tr><th>Centro</th>';
    periodos.forEach(function(p,i){
      h+='<th style="text-align:right">'+p+'</th>';
      if(i>0) h+='<th style="text-align:right;font-size:10px">Var.</th>';
    });
    h+='</tr></thead><tbody>';
    var allC={};
    res.forEach(function(r){r.tabla_centros.forEach(function(c){allC[c.nombre]=1;});});
    Object.keys(allC).forEach(function(n){
      h+='<tr><td style="color:#E8ECF4;font-weight:500">'+n+'</td>';
      res.forEach(function(r,i){
        var f=r.tabla_centros.find(function(c){return c.nombre===n;});
        var v=f?f.importe:"-";
        h+='<td style="text-align:right;color:#00C5D4">'+v+'</td>';
        if(i>0){
          var p=res[0].tabla_centros.find(function(c){return c.nombre===n;});
          h+='<td style="text-align:right">'+dif(v,p?p.importe:"-")+'</td>';
        }
      });
      h+='</tr>';
    });
    h+='</tbody></table></div>';
    document.getElementById("cmpBody").innerHTML=h;
  });
}

function cerrarCmp(){
  document.getElementById("modalCmp").style.display="none";
}
document.addEventListener("keydown",function(e){if(e.key==="Escape")cerrarCmp();});
document.getElementById("modalCmp").addEventListener("click",function(e){if(e.target===this)cerrarCmp();});
</script>
</body></html>"""

DASH_T = r"""<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cobertura Inventarios EMCALI</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=Barlow:wght@300;400;500;600&display=swap');
:root{--C:#003B7A;--CY:#00C5D4;--VE:#00B05B;--AM:#F5C518;--NA:#FF7A00;--RO:#E8003D;--RC:#FF4B6E;--G1:#1A1F2E;--G2:#2D3347;--GB:#3D4562;--TL:#E8ECF4;--TD:#8A94B2;--BG:rgba(255,255,255,.04)}
*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Barlow',sans-serif;background:var(--G1);color:var(--TL);font-size:13px}
.hdr{background:linear-gradient(135deg,var(--C) 0%,#001E50 50%,#000D25 100%);border-bottom:3px solid var(--CY)}
.hi{display:flex;align-items:center;justify-content:space-between;padding:16px 30px}
.lb{width:58px;height:58px;background:white;border-radius:10px;display:flex;align-items:center;justify-content:center;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:15px;color:var(--C)}
.la{display:flex;align-items:center;gap:14px}
.ht{font-family:'Barlow Condensed',sans-serif;font-size:24px;font-weight:800;color:white;letter-spacing:1px;text-transform:uppercase}
.hs{font-size:11px;color:var(--CY);letter-spacing:2px;text-transform:uppercase;margin-top:3px}
.hm{text-align:right;font-size:11px;color:var(--TD)}.hm strong{color:var(--CY);font-size:13px;display:block}
.bn{background:rgba(0,197,212,.15);border:1px solid var(--CY);color:var(--CY);padding:5px 14px;border-radius:6px;font-family:'Barlow Condensed',sans-serif;font-size:12px;font-weight:700;text-transform:uppercase;text-decoration:none;transition:.2s;display:inline-block;margin-top:6px;margin-left:4px}
.bn:hover{background:var(--CY);color:var(--G1)}
.bn-green{background:rgba(0,176,91,.15);border-color:rgba(0,176,91,.5);color:#00B05B}.bn-green:hover{background:#00B05B;color:white}
.hist-banner{background:rgba(245,197,24,.08);border-bottom:2px solid rgba(245,197,24,.3);padding:8px 30px;font-size:12px;color:var(--AM)}
.hist-banner a{color:var(--CY);text-decoration:none;font-weight:700}
.tabs{background:var(--G2);padding:0 30px;border-bottom:1px solid var(--GB);display:flex;gap:4px}
.tab{padding:12px 22px;font-family:'Barlow Condensed',sans-serif;font-weight:600;font-size:13px;letter-spacing:.5px;text-transform:uppercase;cursor:pointer;border:none;background:none;color:var(--TD);border-bottom:3px solid transparent;transition:.2s;margin-bottom:-1px}
.tab:hover{color:var(--TL)}.tab.on{color:var(--CY);border-bottom-color:var(--CY);background:rgba(0,197,212,.08)}
.pg{display:none;padding:20px 30px}.pg.on{display:block}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--BG);border:1px solid var(--GB);border-radius:10px;padding:14px 16px;text-align:center;position:relative;overflow:hidden;transition:.2s}
.kpi:hover{background:rgba(255,255,255,.07);transform:translateY(-2px)}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.cy::before{background:var(--CY)}.ve::before{background:var(--VE)}.am::before{background:var(--AM)}.na::before{background:var(--NA)}.ro::before{background:var(--RO)}
.kl{font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--TD);margin-bottom:6px}
.kv{font-family:'Barlow Condensed',sans-serif;font-size:26px;font-weight:800;line-height:1}
.cy .kv{color:var(--CY)}.ve .kv{color:var(--VE)}.am .kv{color:var(--AM)}.na .kv{color:var(--NA)}.ro .kv{color:var(--RC)}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.g3{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px;margin-bottom:16px}
.card{background:var(--BG);border:1px solid var(--GB);border-radius:12px;overflow:hidden}
.ch{background:rgba(0,197,212,.08);border-bottom:1px solid var(--GB);padding:10px 16px;display:flex;align-items:center}
.ch h3{font-family:'Barlow Condensed',sans-serif;font-size:13px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--CY)}
.cb{padding:14px}.ts{overflow-x:auto;overflow-y:auto;max-height:340px}
table{width:100%;border-collapse:collapse;font-size:11.5px}
thead th{background:var(--C);color:white;padding:8px 10px;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:11px;text-transform:uppercase;position:sticky;top:0;z-index:2;white-space:nowrap}
tbody tr{border-bottom:1px solid rgba(255,255,255,.04)}tbody tr:hover{background:rgba(0,197,212,.06)}
tbody td{padding:7px 10px;color:var(--TL);white-space:nowrap}
.cn{color:var(--TD);font-size:10px;text-align:center;width:28px}.tr{text-align:right}.hl{color:var(--CY)!important;font-weight:600}
.hrc{background:rgba(255,75,110,.08)!important}
.cc{position:relative;width:100%;height:220px}.ccl{position:relative;width:100%;height:260px}
.nota{background:rgba(0,86,184,.15);border:1px solid rgba(0,197,212,.2);border-radius:6px;padding:6px 12px;font-size:10px;color:var(--TD);margin-top:10px;text-transform:uppercase}
.ftr{text-align:center;padding:16px;color:var(--TD);font-size:10px;border-top:1px solid var(--GB);margin-top:20px}
.hoja-badge{font-size:10px;color:var(--TD);margin-top:4px}
#srch{width:350px;padding:8px 14px;background:var(--G2);border:1px solid var(--GB);border-radius:8px;color:var(--TL);font-size:12px;outline:none;margin-bottom:12px}
.td-desc{white-space:normal!important;max-width:260px;line-height:1.3;min-width:160px}
.td-mat{font-family:monospace;font-size:11px;white-space:nowrap}
</style></head><body>
<div class="hdr"><div class="hi">
<div class="la"><div class="lb">EMCALI</div>
<div><div class="ht">Cobertura de Inventarios</div>
<div class="hs">GERENCIA DE ENERGIA &middot; UGA Energia</div>
<div class="hoja-badge">&#128196; {{ d.nombre_archivo }}{% if d.periodo %} &nbsp;&middot;&nbsp; <span style="color:#F5C518;font-weight:700">{{ d.periodo }}</span>{% endif %}</div></div></div>
<div class="hm"><strong>{{ d.fecha }}</strong>Historico: {{ d.hist }} dias<br>
<a href="/dashboard_uga/historial" class="bn">&#128337; Historial</a>
{% if usuario and usuario.rol == 'admin' %}
<a href="/dashboard_uga/cargar" class="bn bn-green">&#128194; Cargar</a>
<a href="/dashboard_uga/usuarios" class="bn" style="background:rgba(245,197,24,.15);border-color:rgba(245,197,24,.5);color:#F5C518">&#128101; Usuarios</a>
{% endif %}
<a href="/dashboard_uga/logout" class="bn" style="background:rgba(255,75,110,.15);border-color:rgba(255,75,110,.5);color:#FF4B6E;font-weight:900">&#128682; Cerrar Sesion</a>
</div></div></div>
{% if hist_id %}
<div class="hist-banner">&#9888;&nbsp; Viendo reporte historico del mes <strong>{{ d._mes }}</strong> &nbsp;&mdash;&nbsp; <a href="/dashboard_uga/dashboard">Ver reporte actual &rarr;</a></div>
{% endif %}
{% if d.gerencias and d.gerencias|length > 1 %}
<div style="background:#2D3347;border-bottom:1px solid #3D4562;padding:8px 30px;display:flex;align-items:center;gap:12px">
<span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#8A94B2">&#127963; Gerencia:</span>
<select id="selGer" onchange="filtrarGerencia(this.value)" style="background:#1A1F2E;border:1px solid #3D4562;color:#E8ECF4;padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer;outline:none">
<option value="TODAS">Todas las gerencias</option>
{% for g in d.gerencias %}<option value="{{ g }}" {{ 'selected' if g == gerencia_sel else '' }}>{{ g }}</option>{% endfor %}
</select>
<span id="gerBadge" style="font-size:11px;color:#8A94B2"></span>
</div>
{% endif %}
<div class="tabs">
<button class="tab on" onclick="pg('cob',this)">&#128202; Cobertura</button>
<button class="tab" onclick="pg('det',this)">&#128203; Detallado</button>
{% if d.edad_inventario %}<button class="tab" onclick="pg('edad',this)">&#128197; Edad Inventario</button>{% endif %}
</div>
<div id="pg-cob" class="pg on">
<div class="kpis">
<div class="kpi cy"><div class="kl">Stock Total</div><div class="kv">{{ d.kpis.stock }}</div></div>
<div class="kpi ve"><div class="kl">Valor Stock</div><div class="kv">{{ d.kpis.importe }}</div></div>
<div class="kpi am"><div class="kl">Centros / Unidades</div><div class="kv">{{ d.kpis.referencias }}</div></div>
<div class="kpi na"><div class="kl">Cant. Salidas</div><div class="kv">{{ d.kpis.salidas }}</div></div>
<div class="kpi ro"><div class="kl">Cobertura en Dias</div><div class="kv">{{ d.kpis.cobertura }}</div></div>
</div>
<div class="g3">
<div class="card"><div class="ch"><h3>Distribucion por Centro / Unidad</h3></div><div class="cb"><div class="cc"><canvas id="cD"></canvas></div></div></div>
<div class="card" id="cardCentros">
<div class="ch" onclick="abrirModal()" style="cursor:pointer">
<h3>Resumen por Centro</h3>
<span style="margin-left:auto;font-size:11px;color:var(--CY)">&#x26F6; Ver completo</span>
</div>
<div class="cb" style="padding:0"><div class="ts"><table>
<thead><tr><th>#</th><th>Centro / Unidad</th><th>Stock</th><th>Valor</th><th>Salidas</th><th>Cob.Dias</th></tr></thead>
<tbody>{% for r in d.tabla_centros %}<tr>
<td class="cn">{{r.num}}</td><td>{{r.nombre}}</td><td class="tr">{{r.stock}}</td>
<td class="tr hl">{{r.importe}}</td><td class="tr">{{r.salidas}}</td><td class="tr">{{r.cobertura}}</td>
</tr>{% endfor %}</tbody></table></div></div></div>
<div id="modalCentros" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.8);align-items:center;justify-content:center">
<div style="background:#1E2538;border:1px solid #3D4562;border-radius:16px;width:92%;max-width:960px;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 24px 64px rgba(0,0,0,.8)">
<div style="background:rgba(0,197,212,.1);border-bottom:1px solid #3D4562;padding:16px 24px;display:flex;align-items:center;border-radius:16px 16px 0 0">
<span style="font-family:'Barlow Condensed',sans-serif;font-size:16px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#00C5D4">&#128202; Resumen por Centro / Unidad</span>
<button onclick="abrirGrafCentros()" style="margin-left:10px;background:rgba(245,197,24,.15);border:1px solid rgba(245,197,24,.5);color:#F5C518;padding:6px 14px;border-radius:7px;font-size:11px;font-weight:700;cursor:pointer">&#128200; Graficas</button>
<button onclick="cerrarModal()" style="margin-left:auto;background:rgba(255,255,255,.08);border:1px solid #3D4562;color:#E8ECF4;width:34px;height:34px;border-radius:8px;font-size:20px;cursor:pointer">&times;</button>
</div>
<div style="overflow-y:auto;flex:1">
<table style="width:100%;border-collapse:collapse;font-size:12px">
<thead><tr>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:left;position:sticky;top:0;font-size:11px;text-transform:uppercase">#</th>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:left;position:sticky;top:0;font-size:11px;text-transform:uppercase">Centro / Unidad</th>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:right;position:sticky;top:0;font-size:11px;text-transform:uppercase">Stock</th>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:right;position:sticky;top:0;font-size:11px;text-transform:uppercase">Valor</th>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:right;position:sticky;top:0;font-size:11px;text-transform:uppercase">Salidas</th>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:right;position:sticky;top:0;font-size:11px;text-transform:uppercase">N&#176; Mat.</th>
<th style="background:#003B7A;color:white;padding:10px 14px;text-align:right;position:sticky;top:0;font-size:11px;text-transform:uppercase">Cob. Dias</th>
</tr></thead>
<tbody>{% for r in d.tabla_centros %}
<tr style="border-bottom:1px solid rgba(255,255,255,.05)">
<td style="padding:9px 14px;color:#8A94B2;font-size:11px">{{r.num}}</td>
<td style="padding:9px 14px;color:#E8ECF4;font-weight:500">{{r.nombre}}</td>
<td style="padding:9px 14px;text-align:right">{{r.stock}}</td>
<td style="padding:9px 14px;text-align:right;color:#00C5D4;font-weight:600">{{r.importe}}</td>
<td style="padding:9px 14px;text-align:right">{{r.salidas}}</td>
<td style="padding:9px 14px;text-align:right">{{r.referencias}}</td>
<td style="padding:9px 14px;text-align:right">{{r.cobertura}}</td>
</tr>{% endfor %}</tbody></table>
</div>
<div style="padding:12px 24px;border-top:1px solid #3D4562;text-align:right">
<button onclick="cerrarModal()" style="background:linear-gradient(135deg,#0057B8,#003B7A);color:white;border:none;padding:9px 24px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;text-transform:uppercase">Cerrar</button>
</div>
</div></div>
<div class="card"><div class="ch"><h3>Grupo de Articulos</h3></div><div class="cb"><div class="cc"><canvas id="cG"></canvas></div></div></div>
</div>
<div class="g2">
<div class="card"><div class="ch"><h3>Movimiento de Stock por Centro (%)</h3></div><div class="cb"><div class="ccl"><canvas id="cE"></canvas></div></div></div>
<div class="card"><div class="ch"><h3>Participacion de Stock por Centro</h3></div><div class="cb"><div class="ccl"><canvas id="cS"></canvas></div></div></div>
</div>
<div class="nota">{{ d.hist }} dias de historico &middot; Cobertura = {{ d.hist }} x Stock / Cant. Salidas</div>
</div>
<div id="pg-det" class="pg">
<div class="kpis">
<div class="kpi cy"><div class="kl">Stock Total</div><div class="kv">{{ d.kpis.stock }}</div></div>
<div class="kpi ve"><div class="kl">Valor Stock</div><div class="kv">{{ d.kpis.importe }}</div></div>
<div class="kpi am"><div class="kl">Centros</div><div class="kv">{{ d.kpis.referencias }}</div></div>
<div class="kpi ro"><div class="kl">Cobertura</div><div class="kv">{{ d.kpis.cobertura }}</div></div>
<div class="kpi na"><div class="kl">Sin Movimiento</div><div class="kv">{{ d.kpis.sin_mov }}</div></div>
</div>
<input id="srch" type="text" placeholder="Buscar material, descripcion, centro o grupo..." onkeyup="filtrar()">
<div class="card">
<div class="ch"><h3>Top 200 Materiales por Valor de Inventario</h3>
<span style="margin-left:auto;font-size:10px;color:var(--TD)">Filas rojas = cobertura &gt; 2.000 dias</span></div>
<div class="ts" style="max-height:600px"><table id="tD">
<thead><tr><th>#</th><th>MATERIAL</th><th>DESCRIPCION</th><th>CENTRO</th><th>GRUPO</th><th>STOCK</th><th>VALOR</th><th>SALIDAS</th><th>VALOR SALIDAS</th><th>COB. DIAS</th></tr></thead>
<tbody>{% for r in d.tabla_detallada %}<tr class="{{ 'hrc' if r.alta else '' }}">
<td class="cn">{{r.num}}</td><td class="td-mat">{{r.material}}</td>
<td class="td-desc">{{r.descripcion}}</td><td>{{r.centro}}</td><td>{{r.grupo}}</td>
<td class="tr">{{r.stock}}</td><td class="tr hl">{{r.importe}}</td>
<td class="tr">{{r.salidas}}</td><td class="tr">{{r.val_salidas}}</td><td class="tr">{{r.cobertura}}</td>
</tr>{% endfor %}</tbody></table></div></div>
</div>
{% if d.edad_inventario %}
<div id="pg-edad" class="pg">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
<div class="card"><div class="ch"><h3>&#128197; Edad Salida &mdash; Valor Stock</h3></div><div class="cb"><div class="cc"><canvas id="cEdS"></canvas></div></div></div>
<div class="card"><div class="ch"><h3>&#128197; Edad Entrada &mdash; Valor Stock</h3></div><div class="cb"><div class="cc"><canvas id="cEdE"></canvas></div></div></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
<div class="card"><div class="ch"><h3>&#128202; Edad Salida &mdash; Stock Unidades</h3></div><div class="cb"><div class="cc"><canvas id="cEdSS"></canvas></div></div></div>
<div class="card"><div class="ch"><h3>&#128202; Edad Entrada &mdash; Stock Unidades</h3></div><div class="cb"><div class="cc"><canvas id="cEdES"></canvas></div></div></div>
</div>
<div class="card" style="margin-bottom:16px"><div class="ch"><h3>&#9878; Comparativo Salida vs Entrada</h3></div><div class="cb"><div class="ccl"><canvas id="cEdCmp"></canvas></div></div></div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
<div class="card"><div class="ch"><h3>&#128204; Detalle Edad Salida</h3></div><div class="cb" style="padding:0"><div class="ts"><table>
<thead><tr><th>Categoria</th><th class="tr">Mat.</th><th class="tr">Stock</th><th class="tr">Valor</th></tr></thead>
<tbody>{% for r in d.edad_inventario.salida %}<tr><td>{{r.categoria}}</td>
<td class="tr">{{"{:,.0f}".format(r.referencias)}}</td>
<td class="tr">{{"{:,.0f}".format(r.stock)}}</td>
<td class="tr hl">${{"%.1fM"%(r.valor/1e6) if r.valor>=1e6 else "%.0fK"%(r.valor/1e3) if r.valor>=1e3 else "%.0f"%r.valor}}</td>
</tr>{% endfor %}</tbody></table></div></div></div>
<div class="card"><div class="ch"><h3>&#128204; Detalle Edad Entrada</h3></div><div class="cb" style="padding:0"><div class="ts"><table>
<thead><tr><th>Categoria</th><th class="tr">Ref.</th><th class="tr">Stock</th><th class="tr">Valor</th></tr></thead>
<tbody>{% for r in d.edad_inventario.entrada %}<tr><td>{{r.categoria}}</td>
<td class="tr">{{"{:,.0f}".format(r.referencias)}}</td>
<td class="tr">{{"{:,.0f}".format(r.stock)}}</td>
<td class="tr hl">${{"%.1fM"%(r.valor/1e6) if r.valor>=1e6 else "%.0fK"%(r.valor/1e3) if r.valor>=1e3 else "%.0f"%r.valor}}</td>
</tr>{% endfor %}</tbody></table></div></div></div>
</div>
<div class="nota">Edad Inventario &bull; General: hoja Resumen SAP &bull; Por gerencia: calculado del detalle</div>
</div>
{% endif %}
<!-- MODAL GRAFICAS POR CENTRO -->
<div id="modalGraf" style="display:none;position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.85);align-items:center;justify-content:center">
<div style="background:#1E2538;border:1px solid #3D4562;border-radius:16px;width:94%;max-width:900px;max-height:92vh;display:flex;flex-direction:column">
<div style="background:rgba(245,197,24,.1);border-bottom:1px solid #3D4562;padding:14px 20px;display:flex;align-items:center;gap:12px;border-radius:16px 16px 0 0">
<span style="font-family:'Barlow Condensed',sans-serif;font-size:15px;font-weight:700;text-transform:uppercase;color:#F5C518">&#128200; Graficas por Centro / Unidad</span>
<select id="selTipoGraf" onchange="var _t=this.value;setTimeout(function(){renderGrafCentros(_t);},10);" style="background:#2D3347;border:1px solid #3D4562;color:#E8ECF4;padding:5px 12px;border-radius:6px;font-size:12px;outline:none">
<option value="valor">Valor Stock ($M)</option>
<option value="stock">Stock (Unidades)</option>
<option value="salidas">Salidas</option>
<option value="cobertura">Cobertura (Dias)</option>
</select>
<button onclick="cerrarGrafCentros()" style="margin-left:auto;background:rgba(255,255,255,.08);border:1px solid #3D4562;color:#E8ECF4;width:34px;height:34px;border-radius:8px;font-size:20px;cursor:pointer">&times;</button>
</div>
<div style="padding:20px;flex:1;overflow-y:auto"><div style="position:relative;width:100%;height:400px"><canvas id="cGrafCentros"></canvas></div></div>
<div style="padding:10px 20px;border-top:1px solid #3D4562;text-align:right">
<button onclick="cerrarGrafCentros()" style="background:linear-gradient(135deg,#0057B8,#003B7A);color:white;border:none;padding:9px 24px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;text-transform:uppercase">Cerrar</button>
</div></div></div>
<div style="position:fixed;bottom:6px;left:14px;font-size:10px;color:#3D4562;z-index:100">Desarrollado por <b style="color:#00C5D4">Fabio A. Moreno</b></div><div style="position:fixed;bottom:6px;right:14px;background:rgba(0,197,212,.15);border:1px solid #00C5D4;color:#00C5D4;padding:2px 8px;border-radius:20px;font-size:10px;z-index:100">v8</div><div class="ftr">DASHBOARD EMCALI &middot; {{ d.fecha }}{% if d.periodo %} &middot; {{ d.periodo }}{% endif %}</div>
<script>
var C={{ d.chart | tojson }};
var CL=["#00C5D4","#4A9FD4","#0057B8","#00B05B","#F5C518","#FF7A00","#E8003D","#9B5DE5","#F15BB5","#00BBF9"];
var _CX={{ d.tabla_centros | tojson }};
/* Raw numeric values for graficas */
function _pN(v){var s=String(v).replace(/[$\s]/g,"").replace(/,/g,"");return parseFloat(s)||0;}
var _CXR=_CX.map(function(r){
  return {nombre:r.nombre,
    valor:+(_pN(r.importe)/1e6).toFixed(1),
    stock:Math.round(_pN(r.stock)),
    salidas:Math.round(_pN(r.salidas)),
    cobertura_txt:String(r.cobertura||""),
    cobertura:+(r.cob_dias||0)};
});

var OP={responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:"#8A94B2",font:{size:10},boxWidth:12}},tooltip:{backgroundColor:"rgba(26,31,46,.95)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1}}};
function pg(id,b){document.querySelectorAll(".pg").forEach(function(x){x.classList.remove("on")});document.querySelectorAll(".tab").forEach(function(x){x.classList.remove("on")});document.getElementById("pg-"+id).classList.add("on");b.classList.add("on");}
function filtrar(){var q=document.getElementById("srch").value.toLowerCase();document.querySelectorAll("#tD tbody tr").forEach(function(r){r.style.display=r.textContent.toLowerCase().indexOf(q)>=0?"":"none"});}
var _HIST_ID={{ hist_id|tojson if hist_id else "null" }};
function filtrarGerencia(g){
  var base=_HIST_ID?("/historial/ver/"+_HIST_ID):"/dashboard_uga/dashboard";
  window.location.href=base+"?gerencia="+encodeURIComponent(g)+"&t="+Date.now();
}
function abrirModal(){document.getElementById("modalCentros").style.display="flex";document.body.style.overflow="hidden";}
function cerrarModal(){document.getElementById("modalCentros").style.display="none";document.body.style.overflow="";}
function abrirGrafCentros(){
  var modal=document.getElementById("modalGraf");
  modal.style.display="flex";
  var sel=document.getElementById("selTipoGraf");
  if(sel) sel.value="valor";
  setTimeout(function(){renderGrafCentros("valor");},100);
}
function cerrarGrafCentros(){
  document.getElementById("modalGraf").style.display="none";
}
document.addEventListener("keydown",function(e){if(e.key==="Escape")cerrarModal();});
(function(){var m=document.getElementById("modalCentros");if(m)m.addEventListener("click",function(e){if(e.target===this)cerrarModal();});})();
["cD","cG","cE","cS"].forEach(function(id){var c=Chart.getChart(id);if(c)c.destroy();});
function fmtM(v){if(v>=1000)return"$"+(v/1000).toFixed(1)+"B";if(v>=1)return"$"+v.toFixed(1)+"M";return"$"+(v*1000).toFixed(0)+"K";}
var TT={backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,padding:10,callbacks:{}};
new Chart(document.getElementById("cD"),{type:"doughnut",data:{labels:C.cl_ger||C.cl,datasets:[{data:C.cd_ger||C.cd,backgroundColor:CL,borderColor:"#1A1F2E",borderWidth:2,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:"55%",plugins:{legend:{position:"right",labels:{color:"#8A94B2",font:{size:9},boxWidth:10}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:function(ctx){var tot=ctx.dataset.data.reduce(function(a,b){return a+b;},0);var pct=tot>0?((ctx.parsed/tot)*100).toFixed(1):"0";var v=ctx.parsed>=1?"$"+ctx.parsed.toFixed(1)+"M":"$"+(ctx.parsed*1000).toFixed(0)+"K";return" "+ctx.label+": "+v+" ("+pct+"%)";}}}}}}); 
new Chart(document.getElementById("cG"),{type:"pie",data:{labels:C.gl,datasets:[{data:C.gd,backgroundColor:CL,borderColor:"#1A1F2E",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"right",labels:{color:"#8A94B2",font:{size:9},boxWidth:10}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:function(ctx){var tot=ctx.dataset.data.reduce(function(a,b){return a+b;},0);var pct=tot>0?((ctx.parsed/tot)*100).toFixed(1):"0";var v=ctx.parsed>=1?"$"+ctx.parsed.toFixed(1)+"M":"$"+(ctx.parsed*1000).toFixed(0)+"K";return" "+ctx.label+": "+v+" ("+pct+"%)";}}}}}}); 
new Chart(document.getElementById("cE"),{type:"bar",data:{labels:C.el,datasets:[{label:"Con movimiento",data:C.en,backgroundColor:"#4A9FD4"},{label:"Sin movimiento",data:C.esm,backgroundColor:"#E8003D"}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:"y",scales:{x:{stacked:true,max:100,ticks:{color:"#8A94B2",font:{size:9}},grid:{color:"rgba(255,255,255,.05)"}},y:{stacked:true,ticks:{color:"#8A94B2",font:{size:9}},grid:{display:false}}},plugins:{legend:{labels:{color:"#8A94B2",font:{size:9}}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:function(ctx){return" "+ctx.dataset.label+": "+ctx.parsed.x.toFixed(1)+"%";}}}}}});
new Chart(document.getElementById("cS"),{type:"bar",data:{labels:C.cl,datasets:[{label:"% Stock",data:C.sd,backgroundColor:CL,borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:"y",scales:{x:{ticks:{color:"#8A94B2",font:{size:9}},grid:{color:"rgba(255,255,255,.05)"}},y:{ticks:{color:"#8A94B2",font:{size:9}},grid:{display:false}}},plugins:{tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:function(ctx){return" "+ctx.label+": "+ctx.parsed.x.toFixed(1)+"% del stock";}}}}}});
{% if d.edad_inventario %}
var _ED={{ d.edad_inventario | tojson }};
if(_ED&&_ED.salida&&_ED.salida.length>0){
  var eSL=_ED.salida.map(function(r){return r.categoria;}),eSV=_ED.salida.map(function(r){return+((r.valor/1e6).toFixed(2));});
  var eEL=_ED.entrada&&_ED.entrada.length?_ED.entrada.map(function(r){return r.categoria;}):eSL;
  var eEV=_ED.entrada&&_ED.entrada.length?_ED.entrada.map(function(r){return+((r.valor/1e6).toFixed(2));}):eSV;
  var eSSV=_ED.salida.map(function(r){return+((r.stock/1e3).toFixed(1));}),eESV=eEL===eSL?eSSV:(_ED.entrada.map(function(r){return+((r.stock/1e3).toFixed(1));}));
  var C1=["#00B05B","#F5C518","#FF7A00","#E8003D"],C2=["#00C5D4","#4A9FD4","#FF7A00","#E8003D"];
  function eLM(ctx){var tot=ctx.dataset.data.reduce(function(a,b){return a+b;},0);var pct=tot>0?((ctx.parsed/tot)*100).toFixed(1):"0";return" "+ctx.label+": $"+ctx.parsed.toFixed(1)+"M ("+pct+"%)"; }
  function eLK(ctx){var tot=ctx.dataset.data.reduce(function(a,b){return a+b;},0);var pct=tot>0?((ctx.parsed/tot)*100).toFixed(1):"0";return" "+ctx.label+": "+ctx.parsed.toFixed(0)+"K ("+pct+"%)"; }
  function mkED(id,cfg){try{var el=document.getElementById(id);if(!el)return;var o=Chart.getChart(el);if(o)o.destroy();new Chart(el,cfg);}catch(e){console.error(id+":",e);}}
  mkED("cEdS",{type:"pie",data:{labels:eSL,datasets:[{data:eSV,backgroundColor:C1,borderColor:"#1A1F2E",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{color:"#8A94B2",font:{size:9},boxWidth:10}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:eLM}}}}});
  mkED("cEdE",{type:"pie",data:{labels:eEL,datasets:[{data:eEV,backgroundColor:C2,borderColor:"#1A1F2E",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{color:"#8A94B2",font:{size:9},boxWidth:10}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:eLM}}}}});
  mkED("cEdSS",{type:"doughnut",data:{labels:eSL,datasets:[{data:eSSV,backgroundColor:C1,borderColor:"#1A1F2E",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,cutout:"50%",plugins:{legend:{position:"bottom",labels:{color:"#8A94B2",font:{size:9},boxWidth:10}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:eLK}}}}});
  mkED("cEdES",{type:"doughnut",data:{labels:eEL,datasets:[{data:eESV,backgroundColor:C2,borderColor:"#1A1F2E",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,cutout:"50%",plugins:{legend:{position:"bottom",labels:{color:"#8A94B2",font:{size:9},boxWidth:10}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:eLK}}}}});
  mkED("cEdCmp",{type:"bar",data:{labels:eSL,datasets:[{label:"Salida ($M)",data:eSV,backgroundColor:"#00C5D4",borderRadius:4},{label:"Entrada ($M)",data:eEV,backgroundColor:"#F5C518",borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{ticks:{color:"#8A94B2",font:{size:9}},grid:{color:"rgba(255,255,255,.05)"}},y:{ticks:{color:"#8A94B2",font:{size:9},callback:function(v){return"$"+v+"M";}},grid:{color:"rgba(255,255,255,.05)"}}},plugins:{legend:{labels:{color:"#8A94B2",font:{size:9}}},tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",borderColor:"#3D4562",borderWidth:1,callbacks:{label:function(ctx){return" "+ctx.dataset.label+": $"+ctx.parsed.y.toFixed(1)+"M";}}}}}}); 
}
{% endif %}
function renderGrafCentros(tipo){
  var cv=document.getElementById("cGrafCentros");
  if(!cv) return;
  var old=Chart.getChart(cv); if(old) old.destroy();
  cv.style.width="100%"; cv.style.height="100%";
  var labels=_CXR.map(function(r){return r.nombre;}),vals,lbl,fmt;
  if(tipo==="valor"){vals=_CXR.map(function(r){return r.valor;});lbl="Valor Stock";fmt=function(v){if(v>=1e6)return" $"+(v/1e6).toFixed(1)+"B";if(v>=1e3)return" $"+(v/1e3).toFixed(1)+"MM";return" $"+v.toFixed(1)+"M";};}
  else if(tipo==="stock"){vals=_CXR.map(function(r){return r.stock;});lbl="Stock";fmt=function(v){if(v>=1e6)return" "+(v/1e6).toFixed(1)+"M uds";if(v>=1e3)return" "+(v/1e3).toFixed(1)+"K uds";return" "+Math.round(v)+" uds";};}
  else if(tipo==="salidas"){vals=_CXR.map(function(r){return r.salidas;});lbl="Salidas";fmt=function(v){if(v>=1e6)return" "+(v/1e6).toFixed(1)+"M";if(v>=1e3)return" "+(v/1e3).toFixed(1)+"K";return" "+Math.round(v);};}
  else{vals=_CXR.map(function(r){return r.cobertura>540?0:r.cobertura;});lbl="Cobertura";fmt=function(v,i){return i!==undefined&&_CXR[i]?" "+_CXR[i].cobertura_txt:v<=0?" >18 meses sin mov":" "+Math.round(v)+" dias";};}
  var colores=labels.map(function(_,i){return CL[i%CL.length];});
  try{new Chart(cv,{type:"bar",data:{labels:labels,datasets:[{label:lbl,data:vals,backgroundColor:colores,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:labels.length>4?"y":"x",
    scales:{x:{ticks:{color:"#8A94B2",font:{size:10}},grid:{color:"rgba(255,255,255,.05)"}},
            y:{ticks:{color:"#8A94B2",font:{size:10}},grid:{color:"rgba(255,255,255,.05)"}}},
    plugins:{legend:{display:false},
             tooltip:{backgroundColor:"rgba(26,31,46,.97)",titleColor:"#00C5D4",bodyColor:"#E8ECF4",
                      borderColor:"#3D4562",borderWidth:1,
                      callbacks:{label:function(ctx){
                        var horiz=ctx.chart.options.indexAxis==="y";
                        var v=horiz?ctx.parsed.x:ctx.parsed.y;
                        return fmt?fmt(v):" "+v;}}}}}});}catch(e){console.error("grafCentros:",e);}
}
(function(){
  var mg=document.getElementById("modalGraf");
  if(mg)mg.addEventListener("click",function(e){if(e.target===this)cerrarGrafCentros();});
})();

</script></body></html>"""

def filtrar_por_gerencia(datos, gerencia):
    """Filtra y recalcula TODO el dashboard para una gerencia específica."""
    import copy, re

    def parse(v):
        try:
            s = re.sub(r'[^0-9.]', '', str(v).replace(',',''))
            return float(s) if s else 0.0
        except: return 0.0

    d = copy.deepcopy(datos)
    det = [r for r in d["tabla_detallada"] if r.get("gerencia","") == gerencia]
    if not det:
        return d
    for i, r in enumerate(det): r["num"] = i + 1
    d["tabla_detallada"] = det

    total_stk = sum(parse(r.get("stock",0))   for r in det)
    total_imp = sum(parse(r.get("importe",0)) for r in det)
    total_sal = sum(parse(r.get("salidas",0)) for r in det)
    sin_mov   = sum(1 for r in det if parse(r.get("salidas",0)) == 0)
    H = d.get("hist", 1095)
    cob = round(H * total_stk / total_sal, 1) if total_sal > 0 else 0

    def fmt(n):
        if n>=1e6: return "%.1f M"%( n/1e6)
        if n>=1e3: return "%.1f K"%(n/1e3)
        return "%.0f"%n

    def fmt_dias(n):
        try: n=float(n)
        except: return str(n)
        if n>=1e6: return "%.1f M"%(n/1e6)
        if n>=1e3: return "%.1f K"%(n/1e3)
        return "%.1f"%n

    d["kpis"] = {
        "stock":       fmt(total_stk),
        "importe":     fmt(total_imp),
        "salidas":     fmt(total_sal),
        "referencias": str(len(det)),
        "cobertura":   fmt_dias(cob),
        "sin_mov":     str(sin_mov),
    }

    # 3. Recalcular tabla centros
    centros = {}
    for r in det:
        c = r.get("centro","SIN CENTRO")
        if c not in centros:
            centros[c] = {"stk":0,"imp":0,"sal":0,"cob_sum":0,"n":0}
        centros[c]["stk"] += parse(r.get("stock",0))
        centros[c]["imp"] += parse(r.get("importe",0))
        centros[c]["sal"] += parse(r.get("salidas",0))
        cv = parse(r.get("cobertura",0))
        if cv > 0: centros[c]["cob_sum"] += cv; centros[c]["n"] += 1

    cs = sorted(centros.items(), key=lambda x: x[1]["imp"] or x[1]["stk"], reverse=True)
    d["tabla_centros"] = [{"num":i+1,"nombre":n,
        "stock":    "{:,.0f}".format(v["stk"]),
        "importe":  "$ {:,.0f}".format(v["imp"]),
        "salidas":  "{:,.0f}".format(v["sal"]),
        "referencias": str(0),
        "cobertura": fmt_cob(H * v["stk"] / v["sal"] if v["sal"] > 0 else 0)}
        for i,(n,v) in enumerate(cs)]

    # 4. Recalcular gráficas
    CL = [n for n,v in cs[:8]]
    CD = [round((v["imp"] or v["stk"])/1e6, 1) for n,v in cs[:8]]
    SD = [round(v["stk"]/max(1,total_stk)*100, 1) for n,v in cs[:8]]
    EN, ESM = [], []
    for n,v in cs[:8]:
        sm = round(100 if v["sal"]==0 else max(0,min(100,100-v["sal"]/max(1,v["stk"])*100)),1)
        ESM.append(sm); EN.append(round(100-sm,1))

    # Grupos filtrados
    grps = {}
    for r in det:
        g = r.get("grupo","SIN GRUPO") or "SIN GRUPO"
        if g not in grps: grps[g] = 0
        grps[g] += parse(r.get("importe",0)) or parse(r.get("stock",0))
    gs = sorted(grps.items(), key=lambda x: x[1], reverse=True)
    GL = [g for g,_ in gs[:8]]
    GD = [round(v/1e6,1) for _,v in gs[:8]]

    d["chart"] = {"cl":CL,"cd":CD,"sd":SD,"gl":GL,"gd":GD,"el":CL,"en":EN,"esm":ESM,"cl_ger":CL,"cd_ger":CD}
    eg = datos.get("edad_por_ger",{})
    d["edad_inventario"] = eg.get(gerencia) or eg.get("TODAS") or datos.get("edad_inventario_oficial")
    return d

# ══════════════════════════════════════════════════
#  RUTAS
# ══════════════════════════════════════════════════

@app.route("/dashboard_uga/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        u = verificar_usuario(username, password)
        if u:
            session["usuario"] = {"username": username, "nombre": u["nombre"],
                                  "rol": u["rol"], "gerencia": u["gerencia"]}
            return redirect("/dashboard_uga/dashboard")
        return render_template_string(LOGIN_T, error="Usuario o contraseña incorrectos.")
    return render_template_string(LOGIN_T, error="")

@app.route("/dashboard_uga/logout")
def logout():
    session.clear()
    return redirect("/dashboard_uga/login")

@app.route("/dashboard_uga/usuarios")
@requiere_admin
def usuarios():
    users = cargar_usuarios()
    lista = [{"username":k,"nombre":v["nombre"],"rol":v["rol"],"gerencia":v.get("gerencia","TODAS")}
             for k,v in users.items()]
    # Gerencias disponibles del último reporte
    gerencias = []
    if os.path.exists(DJSON):
        with open(DJSON, encoding="utf-8") as fp:
            d = json.load(fp)
        # AUTO-FIX: si referencias=0 en tabla_centros, calcular desde tabla_detallada
        _tc = d.get("tabla_centros", [])
        if _tc and all(str(c.get("referencias","0")).replace(",","").strip() in ("0","") for c in _tc):
            from collections import Counter as _C
            _det = d.get("tabla_detallada", [])
            # Count by centro name (stripping [suffix] from tabla_centros nombre)
            _cnt = _C(r.get("centro","") for r in _det if r.get("centro",""))
            for _c in _tc:
                _base = _c.get("nombre","").split(" [")[0].strip()
                _refs = _cnt.get(_base, 0)
                if not _refs:  # try partial match
                    _refs = sum(v for k,v in _cnt.items() if _base and (_base in k or k in _base))
                if _refs: _c["referencias"] = "{:,.0f}".format(_refs)
            _saved = sum(1 for _c in _tc if _c.get("referencias","0") != "0")
            if _saved:
                try:
                    with open(DJSON, "w", encoding="utf-8") as _fp2:
                        import json as _j; _j.dump(d, _fp2, ensure_ascii=False)
                except: pass
            gerencias = d.get("gerencias", [])
    msg = request.args.get("msg","")
    ok  = request.args.get("ok","1") == "1"
    return render_template_string(USUARIOS_T, usuarios=lista, gerencias=gerencias,
                                  msg=msg, ok=ok, session_user=session["usuario"]["username"])

@app.route("/dashboard_uga/usuarios/nuevo", methods=["POST"])
@requiere_admin
def nuevo_usuario():
    username = request.form.get("username","").strip().lower()
    nombre   = request.form.get("nombre","").strip()
    password = request.form.get("password","").strip()
    rol      = request.form.get("rol","viewer")
    gerencia = request.form.get("gerencia","TODAS")
    if not username or not password:
        return redirect("/dashboard_uga/usuarios?msg=Usuario+y+contraseña+son+obligatorios&ok=0")
    users = cargar_usuarios()
    if username in users:
        return redirect("/dashboard_uga/usuarios?msg=El+usuario+ya+existe&ok=0")
    users[username] = {"password": password, "rol": rol, "nombre": nombre, "gerencia": gerencia}
    guardar_usuarios(users)
    return redirect("/dashboard_uga/usuarios?msg=Usuario+creado+correctamente")

@app.route("/dashboard_uga/usuarios/eliminar", methods=["POST"])
@requiere_admin
def eliminar_usuario():
    username = request.form.get("username","").strip()
    if username == session["usuario"]["username"]:
        return redirect("/dashboard_uga/usuarios?msg=No+puedes+eliminarte+a+ti+mismo&ok=0")
    users = cargar_usuarios()
    if username in users:
        del users[username]
        guardar_usuarios(users)
    return redirect("/dashboard_uga/usuarios?msg=Usuario+eliminado")

@app.route("/dashboard_uga/usuarios/cambiar_password", methods=["POST"])
@requiere_admin
def cambiar_password():
    username = request.form.get("username","").strip()
    password = request.form.get("password","").strip()
    if not password:
        return redirect("/dashboard_uga/usuarios?msg=La+contraseña+no+puede+estar+vacía&ok=0")
    users = cargar_usuarios()
    if username in users:
        users[username]["password"] = password
        guardar_usuarios(users)
    return redirect("/dashboard_uga/usuarios?msg=Contraseña+actualizada")

@app.route("/")
@app.route("/dashboard_uga")
def index():
    return redirect("/dashboard_uga/dashboard") if os.path.exists(DJSON) else redirect("/dashboard_uga/cargar")

@app.route("/dashboard_uga/cargar")
@app.route("/cargar")
def cargar():
    pt = pin_temporal_activo()
    return render_template_string(ADMIN_T, error=leer_error(), tiene_datos=os.path.exists(DJSON),
                                  pin_temporal=pt,
                                  expira=_pin_temporal["expira"].strftime("%H:%M del %d/%m") if pt else "")

@app.route("/dashboard_uga/upload", methods=["POST"])
@app.route("/upload", methods=["POST"])
def upload():
    try:
        pin = request.form.get("pin","").strip()
        if not verificar_pin(pin):
            guardar_error("PIN incorrecto. Solicita un codigo temporal al administrador."); return redirect("/cargar")
        if "file" not in request.files: guardar_error("No se recibio el archivo."); return redirect("/cargar")
        f = request.files["file"]
        if not f or not f.filename: guardar_error("No seleccionaste ningun archivo."); return redirect("/cargar")
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".xlsb",".xlsx",".xls",".xlsm"):
            guardar_error("Formato no valido: %s" % ext); return redirect("/cargar")
        ruta = os.path.join(UDIR, "reporte" + ext); f.save(ruta)
        try: hojas = leer_todas_las_hojas(ruta, ext)
        except RuntimeError as e: guardar_error(str(e)); return redirect("/cargar")
        except Exception: guardar_error("Error leyendo:\n"+traceback.format_exc()[-600:]); return redirect("/cargar")
        if not hojas: guardar_error("No se encontraron hojas con datos."); return redirect("/cargar")
        hoja_nombre, mejor = mejor_hoja(hojas)
        if not mejor: guardar_error("Sin hoja util. Hojas: "+", ".join(hojas.keys())); return redirect("/cargar")
        headers, rows = mejor
        cols = detectar_cols(headers)
        max_sc = len(CAMPOS); diag_hojas=[]
        for nom,(hdr,rws) in hojas.items():
            sc=puntaje_hoja(hdr)
            cu=[h for h in hdr if any(kw.lower() in h.lower() for kws in CAMPOS.values() for kw in kws)]
            diag_hojas.append({"nombre":nom,"filas":len(rws),"score":sc,"cols_utiles":", ".join(cu[:5])})
        diag_hojas.sort(key=lambda x:x["score"],reverse=True)
        with open(DIAG,"w",encoding="utf-8") as fp:
            json.dump({"hoja_sel":hoja_nombre,"puntaje":puntaje_hoja(headers),"max_score":max_sc,
                       "cols":{k:v for k,v in cols.items()},"all_cols":headers,"hojas":diag_hojas},fp,ensure_ascii=False)
        nombre_archivo = f.filename
        datos = procesar(headers, rows, cols, hoja_nombre, nombre_archivo)
        if not datos:
            guardar_error("Hoja '%s' sin filas validas." % hoja_nombre); return redirect("/cargar")
        resumen = leer_resumen(ruta, ext)
        if resumen:
            if "edad_por_ger" in datos: datos["edad_por_ger"]["TODAS"] = resumen
            datos["edad_inventario_oficial"] = resumen
        with open(DJSON,"w",encoding="utf-8") as fp: json.dump(datos,fp,ensure_ascii=False)
        guardar_historial(datos)
        return redirect("/dashboard")
    except Exception:
        guardar_error("Error:\n"+traceback.format_exc()[-800:]); return redirect("/cargar")

@app.route("/dashboard_uga/dashboard")
@app.route("/dashboard")
@requiere_login
def dashboard():
    if not os.path.exists(DJSON): return redirect("/dashboard_uga/cargar")
    try:
        with open(DJSON,encoding="utf-8") as fp: datos=json.load(fp)
        # AUTO-FIX referencias=0: calcular desde tabla_detallada
        _tc=datos.get("tabla_centros",[])
        if _tc and all(str(c.get("referencias","0")).replace(",","").strip() in ("0","") for c in _tc):
            from collections import Counter as _C
            _cnt=_C(r.get("centro","") for r in datos.get("tabla_detallada",[]) if r.get("centro",""))
            _fixed=0
            for _c in _tc:
                _base=_c.get("nombre","").split(" [")[0].strip()
                _refs=_cnt.get(_base,0) or sum(v for k,v in _cnt.items() if _base and (k.startswith(_base[:12]) or _base.startswith(k[:12])))
                if _refs: _c["referencias"]="{:,.0f}".format(_refs); _fixed+=1
            if _fixed:
                try:
                    with open(DJSON,"w",encoding="utf-8") as _f: json.dump(datos,_f,ensure_ascii=False)
                except: pass
        usuario = session.get("usuario", {})
        # Filtro por gerencia
        gerencia_sel = request.args.get("gerencia", usuario.get("gerencia","TODAS"))
        print(f"[FILTRO] gerencia_sel={repr(gerencia_sel)}")
        if gerencia_sel and gerencia_sel != "TODAS":
            datos = filtrar_por_gerencia(datos, gerencia_sel)
        else:
            ei = datos.get("edad_inventario_oficial") or datos.get("edad_por_ger", {}).get("TODAS")
            if ei: datos["edad_inventario"] = ei
        from flask import make_response
        resp = make_response(render_template_string(DASH_T, d=datos, hist_id=None,
                             usuario=usuario, gerencia_sel=gerencia_sel))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception:
        err = traceback.format_exc()
        guardar_error("Error datos:\n"+err[-400:])
        return "<pre style='color:red;padding:20px'>" + err + "</pre>"

@app.route("/dashboard_uga/debug_gerencia")
def debug_gerencia():
    """Diagnóstico — muestra qué gerencias tienen los registros del _data.json"""
    if not os.path.exists(DJSON): return "No hay datos"
    with open(DJSON, encoding="utf-8") as fp: datos = json.load(fp)
    det = datos.get("tabla_detallada", [])
    gerencia_sel = request.args.get("g","")
    html = f"<h2>Total registros: {len(det)}</h2>"
    html += f"<h3>Gerencias en JSON: {datos.get('gerencias',[])}</h3>"
    # Contar por gerencia
    conteo = {}
    for r in det:
        g = r.get("gerencia","") or r.get("ger","") or "SIN CAMPO"
        conteo[g] = conteo.get(g,0) + 1
    html += "<h3>Gerencias en tabla_detallada:</h3><ul>"
    for g,n in sorted(conteo.items(), key=lambda x:-x[1]):
        html += f"<li><b>{g}</b>: {n} registros &nbsp; <a href='?g={g}'>filtrar</a></li>"
    html += "</ul>"
    if gerencia_sel:
        filtrados = [r for r in det if (r.get("gerencia","") or r.get("ger","")) == gerencia_sel]
        html += f"<h3>Filtro '{gerencia_sel}': {len(filtrados)} registros</h3>"
    return html

@app.route("/dashboard_uga/historial")
@app.route("/historial")
def historial():
    return render_template_string(HIST_T, reportes=listar_historial())

@app.route("/historial/<id_rep>")
def ver_historial(id_rep):
    datos = cargar_historial(id_rep)
    if not datos: return redirect("/historial")
    return render_template_string(DASH_T, d=datos, hist_id=id_rep)

@app.route("/historial/eliminar/<id_rep>", methods=["POST"])
def eliminar_historial(id_rep):
    try:
        archivos = glob.glob(os.path.join(HDIR, f"*{id_rep}*.json"))
        for a in archivos:
            os.remove(a)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

@app.route("/historial/datos/<id_rep>")
def datos_historial(id_rep):
    datos = cargar_historial(id_rep)
    if not datos: return json.dumps({})
    gerencia = request.args.get("gerencia", "TODAS")
    if gerencia and gerencia != "TODAS":
        datos = filtrar_por_gerencia(datos, gerencia)
    return json.dumps(datos, ensure_ascii=False)
    return json.dumps(datos, ensure_ascii=False)

@app.route("/diagnostico")
def diagnostico():
    return redirect("/dashboard_uga/cargar")

@app.route("/dashboard_uga/generar_pin", methods=["POST"])
def generar_pin():
    pin = generar_pin_temporal()
    ip  = ip_local()
    return json.dumps({"pin": pin, "url": f"http://{ip}:{PUERTO}/dashboard_uga"})

@app.route("/cols")
def cols_debug():
    """Muestra columnas del archivo para ayudar a mapear nombre_grupo."""
    if not os.path.exists(DIAG): return "No hay diagnostico. Sube el archivo primero."
    import json as _j
    with open(DIAG, encoding="utf-8") as fp: info = _j.load(fp)
    cols = info.get("cols", {})
    all_cols = info.get("all_cols", [])
    html = "<h2>Columnas mapeadas</h2><pre>"
    for k,v in cols.items():
        html += f"{k:20s} -> {v}\n"
    html += "</pre><h2>Todas las columnas del archivo</h2><ol>"
    for c in all_cols:
        html += f"<li>{c}</li>"
    html += "</ol>"
    return html

ACCESO_T = r"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Inventarios — EMCALI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#1A1F2E;color:#E8ECF4;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
.logo{font-size:20px;font-weight:900;color:#003B7A;background:white;padding:8px 20px;border-radius:8px;margin-bottom:16px}
h1{font-size:24px;font-weight:900;text-transform:uppercase;color:#E8ECF4;margin-bottom:6px;text-align:center}
.sub{color:#8A94B2;font-size:13px;margin-bottom:32px;text-align:center}
.card{background:rgba(255,255,255,.04);border:1px solid #3D4562;border-radius:16px;padding:32px;max-width:420px;width:100%;text-align:center}
.btn-acceso{display:block;background:linear-gradient(135deg,#0057B8,#003B7A);color:white;text-decoration:none;padding:16px;border-radius:10px;font-size:16px;font-weight:900;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
.btn-acceso:hover{background:linear-gradient(135deg,#00C5D4,#0057B8)}
.url-box{background:#0D1321;border:1px solid #3D4562;border-radius:8px;padding:12px;margin-top:20px;font-size:11px;color:#8A94B2;word-break:break-all}
.url-box strong{color:#00C5D4;display:block;margin-bottom:4px;font-size:10px;text-transform:uppercase;letter-spacing:1px}
.btn-copy{background:rgba(0,197,212,.1);border:1px solid #00C5D4;color:#00C5D4;padding:6px 14px;border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;margin-top:8px;text-transform:uppercase}
.info{display:flex;gap:12px;margin-top:20px;justify-content:center;flex-wrap:wrap}
.chip{background:rgba(255,255,255,.04);border:1px solid #3D4562;border-radius:20px;padding:5px 14px;font-size:11px;color:#8A94B2}
</style>
<script>
function copiarURL(){
  navigator.clipboard.writeText("{{ url }}").then(function(){
    var b=document.getElementById("btnCopy");
    b.textContent="Copiado \u2713";
    setTimeout(function(){b.textContent="Copiar enlace";},2000);
  });
}
window.onload=function(){
  fetch("/dashboard_uga/check_session").then(function(r){return r.json();})
    .then(function(d){if(d.ok) window.location.href="/dashboard_uga/dashboard";})
    .catch(function(){});
};
</script>
</head><body>
<div class="logo">EMCALI</div>
<h1>Dashboard Inventarios</h1>
<p class="sub">Gerencia de Energía &mdash; UGA Energía</p>
<div class="card">
  <a class="btn-acceso" href="/dashboard_uga/login">&#128274; Ingresar al Dashboard</a>
  <div class="info">
    <span class="chip">&#128202; Cobertura de Inventarios</span>
    <span class="chip">&#127963; Filtro por Gerencia</span>
    <span class="chip">&#128337; Historial mensual</span>
  </div>
  <div class="url-box">
    <strong>&#128279; Enlace directo — guarda o comparte</strong>
    {{ url }}
    <br><button class="btn-copy" id="btnCopy" onclick="copiarURL()">Copiar enlace</button>
  </div>
</div></body></html>"""

@app.route("/dashboard_uga/acceso")
@app.route("/acceso")
def acceso():
    ip  = ip_local()
    url = f"http://{ip}:{PUERTO}/dashboard_uga"
    if session.get("usuario"):
        return redirect("/dashboard_uga/dashboard")
    return render_template_string(ACCESO_T, url=url)

@app.route("/dashboard_uga/check_session")
def check_session():
    from flask import jsonify
    return jsonify({"ok": bool(session.get("usuario"))})

@app.route("/dashboard_uga/reset_usuarios")
def reset_usuarios():
    default = {
        "admin":  {"password":"emcali2024","rol":"admin", "nombre":"Administrador","gerencia":"TODAS","tipo":"planta","vence":""},
        "viewer": {"password":"emcali123", "rol":"viewer","nombre":"Visualizador",  "gerencia":"TODAS","tipo":"planta","vence":""},
    }
    guardar_usuarios(default)
    return "<h2 style='font-family:Arial;padding:20px;color:green'>&#10003; Usuarios reseteados correctamente.</h2><p style='font-family:Arial;padding:0 20px'><a href='/dashboard_uga/login'>Ir al login</a></p><p style='font-family:Arial;padding:10px 20px'>admin / emcali2024 &nbsp;|&nbsp; viewer / emcali123</p>"

if __name__ == "__main__":
    ip = ip_local()
    print("=" * 60)
    print("  DASHBOARD INVENTARIOS EMCALI — UGA ENERGIA")
    print(f"  Local:       http://127.0.0.1:{PUERTO}/{PREFIJO}")
    print(f"  RED INTERNA: http://{ip}:{PUERTO}/{PREFIJO}  <-- COMPARTE ESTA")
    print(f"  PIN fijo:    {PIN_CARGA}")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=PUERTO)