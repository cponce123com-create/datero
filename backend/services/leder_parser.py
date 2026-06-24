"""leder_parser.py — Parser de exportaciones LEDER DATA (Telegram)."""

import re
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from models import Persona, Relacion, Empresa, PersonaEmpresa

_REL_MAP = {
    "PADRE": "padre", "MADRE": "madre", "HERMANO": "hermano",
    "HERMANA": "hermana", "ESPOSA": "conyuge", "ESPOSO": "conyuge",
    "CONCUBINA": "conyuge", "HIJO": None, "HIJA": None, "JEFE(A)": None,
}
_REL_EXT = {
    "TIO PATERNO": "tio_paterno", "TIO MATERNO": "tio_materno",
    "TIA PATERNA": "tia_paterna", "TIA MATERNA": "tia_materna",
    "PRIMO PATERNO": "primo_paterno", "PRIMO MATERNO": "primo_materno",
    "PRIMA PATERNA": "prima_paterna", "PRIMA MATERNA": "prima_materna",
    "SOBRINO": "sobrino", "SOBRINA": "sobrina",
    "CUNADO": "cunado", "CUNADA": "cunada",
    "HERMANASTRO": "hermanastro", "HERMANASTRA": "hermanastra",
    "COMPARTEN HIJOS": "comparte_hijos",
}

def _campo(texto, campo):
    m = re.search(r"^" + re.escape(campo) + r"\s*:\s*(.+?)$", texto, re.MULTILINE | re.IGNORECASE)
    if m:
        v = m.group(1).strip()
        return v if v and v != "-" else None
    return None

def _persona(db, dni, nom=None, ap=None, am=None):
    p = db.query(Persona).filter(Persona.dni == dni).first()
    if not p:
        p = Persona(dni=dni, nombres=nom or "PENDIENTE",
                    apellido_paterno=ap or "PENDIENTE", apellido_materno=am)
        db.add(p)
        db.flush()
    elif nom and p.nombres == "PENDIENTE":
        p.nombres = nom
        if ap: p.apellido_paterno = ap
        if am: p.apellido_materno = am
    return p

def _rel(db, o, d, t, notas=None):
    exist = db.query(Relacion).filter(
        Relacion.persona_origen_dni == o, Relacion.persona_destino_dni == d,
        Relacion.tipo_relacion == t).first()
    if not exist:
        db.add(Relacion(persona_origen_dni=o, persona_destino_dni=d,
                        tipo_relacion=t, certeza="confirmado", notas=notas))

def _nota(p, texto):
    p.notas = (p.notas + "\n" + texto) if p.notas else texto

# ─── Procesadores ────────────────────────────────────────────────────────

def procesar_persona(db, texto):
    dni = _campo(texto, "DNI")
    if not dni or "-" not in dni: return None
    dni = dni.split("-")[0].strip()
    nom = _campo(texto, "NOMBRES")
    ap = _campo(texto, "APELLIDOS")
    ap_p = ap.split()[0] if ap else None
    ap_m = ap.split()[1] if ap and len(ap.split()) > 1 else None
    p = _persona(db, dni, nom, ap_p, ap_m)
    fn = _campo(texto, "FECHA NACIMIENTO")
    if fn: p.fecha_nacimiento = fn
    extras = []
    for c, l in [("GENERO","Genero"),("ESTADO CIVIL","Estado civil"),
                 ("GRADO INSTRUCCION","Instruccion"),("DIRECCION","Direccion")]:
        v = _campo(texto, c)
        if v: extras.append(f"{l}: {v}")
    if extras: _nota(p, "; ".join(extras))
    db.flush()
    return dni

def procesar_familia2(db, texto, dni_ctx):
    c = 0
    for m in re.finditer(
        r"DNI\s*:\s*(\d+).*?APELLIDOS\s*:\s*(.+?)\s*NOMBRES\s*:\s*(.+?)\s*(?:GENERO|SEXO)\s*:\s*(.*?)\s*(?:EDAD|NACIMIENTO)\s*:\s*(.*?)\s*TIPO\s*:\s*(.+?)\s*(?:VERIFICACION RELACION\s*:\s*(.+?))?(?=DNI|\Z)",
        texto, re.DOTALL):
        df = m.group(1).strip()
        ap = m.group(2).strip()
        nom = m.group(3).strip()
        tipo = m.group(6).strip().upper()
        verif = m.group(7)
        app = ap.split()[0] if ap else ""
        apm = ap.split()[1] if len(ap.split()) > 1 else None
        noms = " ".join(nom.split())
        f = _persona(db, df, noms, app, apm)
        if verif: _nota(f, f"Verif LEDER: {verif.strip()}")
        if not dni_ctx or tipo in ("JEFE(A)",): continue
        rt = _REL_MAP.get(tipo)
        if rt:
            _rel(db, dni_ctx, df, rt)
            c += 1
        elif tipo in ("HIJO","HIJA"):
            _rel(db, dni_ctx, df, "hijo", f"LEDER: {tipo}")
            c += 1
        elif tipo in _REL_EXT:
            bt = "hermano"
            if "COMPARTEN" in tipo: bt = "conyuge"
            _rel(db, dni_ctx, df, bt, f"LEDER orig: {tipo}, verif: {verif or 'N/A'}")
            c += 1
        else:
            _nota(f, f"Rel LEDER: {tipo}")
    return c

def procesar_familia1(db, texto, dni_ctx):
    c = 0
    for m in re.finditer(
        r"DOCUMENTO\s*:\s*(\d+).*?APELLIDOS\s*:\s*(.+?)\s*NOMBRES\s*:\s*(.+?)\s*(?:NACIMIENTO|GENERO)\s*:\s*(.*?)\s*(?:SEXO|FILIACION)\s*:\s*(.*?)(?=DOCUMENTO|\Z)",
        texto, re.DOTALL):
        df = m.group(1).strip()
        ap = m.group(2).strip()
        nom = m.group(3).strip()
        fil = m.group(5).strip().upper() if m.group(5) else ""
        app = ap.split()[0] if ap else ""
        apm = ap.split()[1] if len(ap.split()) > 1 else None
        noms = " ".join(nom.split())
        f = _persona(db, df, noms, app, apm)
        if not dni_ctx: continue
        if fil in ("CONCUBINA","ESPOSA","ESPOSO"):
            _rel(db, dni_ctx, df, "conyuge"); c += 1
        else:
            _nota(f, f"Filiacion: {fil}")
    return c

def procesar_empresas(db, texto):
    rucs = []
    for bloque in re.split(r"\n(?=DNI\s*:\s*\d+)", texto):
        if "RUC" not in bloque: continue
        dni = _campo(bloque, "DNI"); ruc = _campo(bloque, "RUC")
        rz = _campo(bloque, "RAZON SOCIAL"); cargo = _campo(bloque, "CARGO")
        if not ruc or not rz: continue
        emp = db.query(Empresa).filter(Empresa.ruc == ruc).first()
        if not emp:
            emp = Empresa(ruc=ruc, nombre=rz); db.add(emp); db.flush()
        if dni:
            dc = dni.split("-")[0].strip()
            p = _persona(db, dc)
            v = db.query(PersonaEmpresa).filter(
                PersonaEmpresa.persona_id == p.id,
                PersonaEmpresa.empresa_id == emp.id,
                PersonaEmpresa.cargo == (cargo or "trabajador")).first()
            if not v:
                db.add(PersonaEmpresa(persona_id=p.id, empresa_id=emp.id,
                                      cargo=cargo or "trabajador"))
        rucs.append(ruc)
    return rucs

def procesar_sunat(db, texto):
    ruc = _campo(texto, "RUC"); rz = _campo(texto, "RAZON SOCIAL")
    est = _campo(texto, "ESTADO"); cond = _campo(texto, "CONDICION")
    if not ruc: return None
    if ruc.startswith("1") and len(ruc) == 11:
        dni = ruc[1:9]
        if rz:
            ps = rz.split()
            if len(ps) >= 3:
                _persona(db, dni, " ".join(ps[2:]), ps[0], ps[1] if len(ps) > 1 else None)
    emp = db.query(Empresa).filter(Empresa.ruc == ruc).first()
    if not emp:
        emp = Empresa(ruc=ruc, nombre=rz or f"RUC {ruc}"); db.add(emp); db.flush()
    if est: emp.estado = est
    if cond: emp.condicion = cond
    return ruc

# ─── Parsers de datos complementarios ────────────────────────────────────

def _parsear_datos_complementarios(db, texto, tipo, dni_ctx):
    if not dni_ctx: return
    p = db.query(Persona).filter(Persona.dni == dni_ctx).first()
    if not p: return
    datos = []
    if tipo == "SUELDOS":
        emps = re.findall(r"EMPRESA\s*:\s*(.+?)\s*$", texto, re.MULTILINE)
        if emps: datos.append(f"Trabajos ({len(set(emps))}): {', '.join(set(emps))}")
    elif tipo == "TELEFONOS":
        tels = re.findall(r"TELEFONO\s*:\s*(\d+)", texto)
        if tels: datos.append(f"Tel: {', '.join(tels)}")
    elif tipo == "CORREOS":
        mails = re.findall(r"CORREO\s*:\s*(.+?)$", texto, re.MULTILINE)
        if mails: datos.append(f"Email: {', '.join(set(mails))}")
    elif tipo == "VEHICULOS":
        placas = re.findall(r"PLACA\s*:\s*(.+?)$", texto, re.MULTILINE)
        if placas: datos.append(f"Veh: {', '.join(set(placas))}")
    elif tipo == "DIRECCIONES":
        dirs = re.findall(r"DIRECCION\s*:\s*(.+?)$", texto, re.MULTILINE)
        if dirs: datos.append(f"Direcciones: {', '.join(set(dirs[:3]))}")
    if datos: _nota(p, "[LEDER] " + "; ".join(datos))

# ─── Result ───────────────────────────────────────────────────────────────

class LederResult:
    def __init__(self):
        self.p = self.r = self.e = self.v = 0
        self.err = []

# ─── Procesador principal ─────────────────────────────────────────────────


def _strip_html(t):
    import re
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    t = t.replace('&nbsp;', ' ').replace('&#10;', '\n').replace('&#13;', '')
    t = t.replace("&#39;", "'").replace('&quot;', "'")
    t = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), t)
    return t
def procesar_texto_leder(db, raw):
    res = LederResult()
    raw = _strip_html(raw)
    for msg in re.split(r"(?=\[#LEDER_BOT\])", raw):
        msg = msg.strip()
        if len(msg) < 20: continue
        try:
            tipo = None
            if "[#LEDER_BOT]" in msg and "META [PREMIUM]" in msg and "|" not in msg.split("META")[1][:30]:
                tipo = "M"
            elif "FAMILIA [1]" in msg: tipo = "F1"
            elif "FAMILIA [2]" in msg: tipo = "F2"
            elif "EMPRESAS" in msg: tipo = "E"
            elif "SUNAT" in msg: tipo = "S"
            elif "SUELDOS" in msg: tipo = "SUELDOS"
            elif "TELEFONOS" in msg: tipo = "TELEFONOS"
            elif "CORREOS" in msg: tipo = "CORREOS"
            elif "VEHICULOS" in msg: tipo = "VEHICULOS"
            elif "DIRECCIONES" in msg: tipo = "DIRECCIONES"
            elif "TRABAJOS" in msg: tipo = "TRABAJOS"
            elif "RENIEC NOMBRES" in msg: tipo = "RENIEC"
            elif "AFPS" in msg: tipo = "AFPS"
            elif "HOGAR" in msg: tipo = "HOGAR"
            if not tipo: continue
            dni_ctx = _campo(msg, "DNI")
            if dni_ctx and "-" in dni_ctx: dni_ctx = dni_ctx.split("-")[0].strip()
            if tipo == "M":
                if procesar_persona(db, msg): res.p += 1
            elif tipo == "F1":
                res.r += procesar_familia1(db, msg, dni_ctx)
            elif tipo == "F2":
                res.r += procesar_familia2(db, msg, dni_ctx)
            elif tipo == "E":
                res.e += len(procesar_empresas(db, msg))
            elif tipo == "S":
                if procesar_sunat(db, msg): res.e += 1
            else:
                _parsear_datos_complementarios(db, msg, tipo, dni_ctx)
        except Exception as ex:
            res.err.append(str(ex)[:80])
    db.commit()
    return res
