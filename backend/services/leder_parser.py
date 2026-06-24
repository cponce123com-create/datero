"""leder_parser.py — Parser de exportaciones LEDER DATA (Telegram)."""

import re
from typing import List, Optional
from sqlalchemy.orm import Session
from models import Persona, Relacion, Empresa, PersonaEmpresa

_REL_MAP = {
    "PADRE": "padre", "MADRE": "madre", "HERMANO": "hermano",
    "HERMANA": "hermana", "ESPOSA": "conyuge", "ESPOSO": "conyuge",
    "CONCUBINA": "conyuge", "HIJO": "hijo", "HIJA": "hija",
    "JEFE(A)": None,
}
_REL_EXT = {
    "TIO PATERNO": ("tio", "hermano"), "TIO MATERNO": ("tio", "hermano"),
    "TIA PATERNA": ("tia", "hermana"), "TIA MATERNA": ("tia", "hermana"),
    "PRIMO PATERNO": ("primo", "hermano"), "PRIMO MATERNO": ("primo", "hermano"),
    "PRIMA PATERNA": ("prima", "hermana"), "PRIMA MATERNA": ("prima", "hermana"),
    "SOBRINO": ("sobrino", "hermano"), "SOBRINA": ("sobrina", "hermana"),
    "CUNADO": ("cunado", "hermano"), "CUNADA": ("cunada", "hermana"),
    "HERMANASTRO": ("hermanastro", "hermano"), "HERMANASTRA": ("hermanastra", "hermana"),
    "COMPARTEN HIJOS": ("comparte_hijos", "conyuge"),
}


class LederResult:
    def __init__(self):
        self.p = self.r = self.e = self.v = 0
        self.err = []


def _strip_html(t):
    # Convertir <br>, <br/>, <br />, </p>, </div>, </tr> a newlines ANTES de quitar tags
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</(?:p|div|tr|li|h[1-6]|blockquote|pre)>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<[^>]+>', '', t)
    for e, c in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&nbsp;"," "),
                 ("&#10;","\n"),("&#13;",""),("&#39;","'"),("&quot;","'")]:
        t = t.replace(e, c)
    t = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), t)
    # Normalizar multiples newlines seguidos
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t


def _campo(texto, campo):
    m = re.search(r"^" + re.escape(campo) + r"\s*:\s*(.+?)$", texto, re.MULTILINE | re.IGNORECASE)
    if m:
        v = m.group(1).strip()
        return v if v and v != "-" else None
    return None


def _todos_campos(texto, campo):
    return re.findall(r"^" + re.escape(campo) + r"\s*:\s*(.+?)$", texto, re.MULTILINE | re.IGNORECASE)


def _persona(db, dni, nom=None, ap=None, am=None):
    p = db.query(Persona).filter(Persona.dni == dni).first()
    if not p:
        p = Persona(dni=dni, nombres=nom or "PENDIENTE",
                    apellido_paterno=ap or "PENDIENTE", apellido_materno=am)
        db.add(p); db.flush()
    elif nom and p.nombres == "PENDIENTE":
        p.nombres = nom
        if ap: p.apellido_paterno = ap
        if am: p.apellido_materno = am
    return p


def _rel(db, o, d, t, notas=None):
    op = _persona(db, o)
    dp = _persona(db, d)
    exist = db.query(Relacion).filter(
        Relacion.persona_origen_id == op.id, Relacion.persona_destino_id == dp.id,
        Relacion.tipo_relacion == t).first()
    if not exist:
        db.add(Relacion(persona_origen_id=op.id, persona_destino_id=dp.id,
                        tipo_relacion=t, certeza="confirmado", notas=notas))
        return True
    return False


def _nota(p, texto):
    sep = "\n"
    p.notas = (p.notas + sep + texto) if p.notas else texto


def _dni_limpio(texto):
    dni = _campo(texto, "DNI")
    if not dni: return None
    return dni.split("-")[0].strip() if "-" in dni else dni.strip()


def _bloques_personas(texto):
    bloques = []
    partes = re.split(r"\n(?=DNI\s*:\s*\d+)", texto)
    for parte in partes:
        if not _campo(parte, "DNI"): continue
        dni = _dni_limpio(parte)
        if not dni: continue
        bloques.append({
            "dni": dni,
            "apellidos": _campo(parte, "APELLIDOS"),
            "nombres": _campo(parte, "NOMBRES"),
            "tipo": _campo(parte, "TIPO"),
            "genero": _campo(parte, "GENERO") or _campo(parte, "SEXO"),
            "verificacion": _campo(parte, "VERIFICACION RELACION"),
            "filiacion": _campo(parte, "FILIACION"),
            "fecha_nac": _campo(parte, "FECHA NACIMIENTO") or _campo(parte, "NACIMIENTO"),
            "direccion": _campo(parte, "DIRECCION"),
            "estado_civil": _campo(parte, "ESTADO CIVIL"),
            "instruccion": _campo(parte, "GRADO INSTRUCCION"),
        })
    return bloques


def _procesar_bloque_persona(db, blq):
    ap = blq["apellidos"]
    nom = blq["nombres"]
    app = ap.split()[0] if ap else None
    apm = ap.split()[1] if ap and len(ap.split()) > 1 else None
    noms = " ".join(nom.split()) if nom else "PENDIENTE"
    p = _persona(db, blq["dni"], noms, app, apm)
    if blq["fecha_nac"]: p.fecha_nacimiento = blq["fecha_nac"]
    extras = []
    for v, l in [(blq["genero"],"Genero"),(blq["estado_civil"],"Estado civil"),
                 (blq["instruccion"],"Instruccion"),(blq["direccion"],"Direccion")]:
        if v: extras.append(f"{l}: {v}")
    if extras: _nota(p, "; ".join(extras))
    if blq["verificacion"]: _nota(p, "Verif LEDER: " + blq["verificacion"])
    db.flush()
    return p


def procesar_meta(db, texto):
    dni = _dni_limpio(texto)
    if not dni: return None
    _procesar_bloque_persona(db, {"dni": dni,
        "apellidos": _campo(texto, "APELLIDOS"),
        "nombres": _campo(texto, "NOMBRES"),
        "genero": _campo(texto, "GENERO"),
        "fecha_nac": _campo(texto, "FECHA NACIMIENTO"),
        "direccion": _campo(texto, "DIRECCION"),
        "estado_civil": _campo(texto, "ESTADO CIVIL"),
        "instruccion": _campo(texto, "GRADO INSTRUCCION"),
    })
    return dni


def procesar_familia(db, texto, dni_actual):
    creadas = 0
    for blq in _bloques_personas(texto):
        f = _procesar_bloque_persona(db, blq)
        if not dni_actual: continue
        tipo = (blq["tipo"] or blq["filiacion"] or "").upper()
        if tipo in ("JEFE(A)", ""): continue
        rt = _REL_MAP.get(tipo)
        if rt:
            if _rel(db, dni_actual, blq["dni"], rt): creadas += 1
        elif tipo in ("HIJO", "HIJA"):
            if _rel(db, dni_actual, blq["dni"], "hijo", "LEDER: " + tipo): creadas += 1
        elif tipo in _REL_EXT:
            ext, base = _REL_EXT[tipo]
            if _rel(db, dni_actual, blq["dni"], base, "LEDER orig: " + tipo): creadas += 1
        else:
            _nota(f, "Rel LEDER: " + tipo)
    return creadas


def procesar_empresas(db, texto):
    rucs = []
    for bloque in re.split(r"\n(?=DNI\s*:\s*\d+)", texto):
        dni = _campo(bloque, "DNI"); ruc = _campo(bloque, "RUC")
        rz = _campo(bloque, "RAZON SOCIAL"); cargo = _campo(bloque, "CARGO")
        desde = _campo(bloque, "DESDE")
        if not ruc or not rz: continue
        emp = db.query(Empresa).filter(Empresa.ruc == ruc).first()
        if not emp:
            emp = Empresa(ruc=ruc, nombre=rz); db.add(emp); db.flush()
        if dni:
            dc = dni.split("-")[0].strip() if "-" in dni else dni.strip()
            p = _persona(db, dc)
            v = db.query(PersonaEmpresa).filter(
                PersonaEmpresa.persona_id == p.id,
                PersonaEmpresa.empresa_id == emp.id,
                PersonaEmpresa.cargo == (cargo or "trabajador")).first()
            if not v:
                db.add(PersonaEmpresa(persona_id=p.id, empresa_id=emp.id,
                                      cargo=cargo or "trabajador",
                                      observacion="Desde: " + desde if desde else None))
                rucs.append(ruc)
        else:
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
        emp = Empresa(ruc=ruc, nombre=rz or "RUC " + ruc); db.add(emp); db.flush()
    if est: emp.estado = est
    if cond: emp.condicion = cond
    return ruc


def _complementarios(db, texto, tipo, dni_ctx):
    if not dni_ctx: return
    p = db.query(Persona).filter(Persona.dni == dni_ctx).first()
    if not p: return
    datos = []
    if tipo == "SUELDOS":
        emps = list(set(_todos_campos(texto, "EMPRESA")))
        if emps: datos.append("Trabajos (" + str(len(emps)) + "): " + ", ".join(emps))
    elif tipo == "TELEFONOS":
        tels = _todos_campos(texto, "TELEFONO")
        if tels: datos.append("Tel: " + ", ".join(tels))
    elif tipo == "CORREOS":
        mails = list(set(_todos_campos(texto, "CORREO")))
        if mails: datos.append("Email: " + ", ".join(mails))
    elif tipo == "VEHICULOS":
        placas = list(set(_todos_campos(texto, "PLACA")))
        if placas: datos.append("Veh: " + ", ".join(placas))
    elif tipo == "DIRECCIONES":
        dirs = list(set(_todos_campos(texto, "DIRECCION")))[:3]
        if dirs: datos.append("Direcciones: " + ", ".join(dirs))
    if datos: _nota(p, "[LEDER] " + "; ".join(datos))


def _detectar_tipo(msg):
    if "SUELDOS" in msg: return "SUELDOS"
    if "TELEFONOS" in msg: return "TELEFONOS"
    if "CORREOS" in msg: return "CORREOS"
    if "VEHICULOS" in msg: return "VEHICULOS"
    if "DIRECCIONES" in msg: return "DIRECCIONES"
    if "TRABAJOS" in msg: return "TRABAJOS"
    if "AFPS" in msg: return "AFPS"
    if "HOGAR" in msg: return "HOGAR"
    if "FAMILIA [1]" in msg: return "F1"
    if "FAMILIA [2]" in msg: return "F2"
    if "EMPRESAS" in msg and "META" in msg: return "E"
    if "SUNAT" in msg and "META" in msg: return "S"
    if "RENIEC" in msg: return "RENIEC"
    if "META" in msg and "PREMIUM" in msg: return "M"
    return None


def _es_continuacion(msg):
    return bool(re.match(r"^\[\d+/\d+\]", msg.strip()))


def procesar_texto_leder(db, raw):
    res = LederResult()
    raw = _strip_html(raw)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    dni_actual = None
    tipo_actual = None
    acumulado = ""

    mensajes = re.split(r"(?=\[#LEDER_BOT\])", raw)

    def _flush():
        nonlocal acumulado, tipo_actual, dni_actual
        if not acumulado or not tipo_actual:
            return
        try:
            if tipo_actual == "M":
                dn = procesar_meta(db, acumulado)
                if dn:
                    res.p += 1
                    dni_actual = dn
            elif tipo_actual in ("F1", "F2"):
                res.r += procesar_familia(db, acumulado, dni_actual)
            elif tipo_actual == "E":
                res.e += len(procesar_empresas(db, acumulado))
            elif tipo_actual == "S":
                if procesar_sunat(db, acumulado): res.e += 1
            elif tipo_actual in ("SUELDOS","TELEFONOS","CORREOS","VEHICULOS",
                                  "DIRECCIONES","TRABAJOS","AFPS","RENIEC","HOGAR"):
                _complementarios(db, acumulado, tipo_actual, dni_actual)
        except Exception as ex:
            res.err.append(str(ex)[:80])
        acumulado = ""

    for msg in mensajes:
        msg = msg.strip()
        if not msg: continue
        tipo = _detectar_tipo(msg)
        if tipo:
            _flush()
            tipo_actual = tipo
            acumulado = msg
        elif tipo_actual and _es_continuacion(msg):
            acumulado = acumulado + "\n" + msg
        else:
            _flush()
            tipo_actual = None
            dni_actual = None

    _flush()
    db.commit()
    return res
