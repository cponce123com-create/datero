"""
leder_parser.py — Parser inteligente de exportaciones LEDER DATA (Telegram).

Soporta los siguientes bloques del bot [#LEDER_BOT]:
  - RENIEC ONLINE [/dni]     → Persona completa + notas (padres, dirección, etc.)
  - RENIEC NOMBRES [/nm]     → 1 o más personas desde búsqueda por nombre
  - ARBOL GENEALOGICO [/ag]  → Familiares con relaciones
  - META                     → Datos base de persona
  - META | FAMILIA [1]       → Familia RENIEC (jefe/hijos)
  - META | FAMILIA [2]       → Familia árbol genealógico (padres/tíos/primos)
  - META | EMPRESAS          → Vínculos empresa-cargo
  - META | SUNAT             → Estado SUNAT de empresa
  - META | TELEFONOS         → Teléfonos como notas
  - META | SUELDOS           → Sueldos como notas
  - META | DIRECCIONES       → Direcciones adicionales como notas
"""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from models import Persona, Relacion, Empresa, PersonaEmpresa

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

_TIPO_A_RELACION: Dict[str, str] = {
    "PADRE": "padre", "MADRE": "madre",
    "HERMANO": "hermano", "HERMANA": "hermana",
    "HIJO": "hijo", "HIJA": "hija",
    "HIJASTRO": "hijastro", "HIJASTRA": "hijastra",
    "ESPOSO": "conyuge", "ESPOSA": "conyuge",
    "CONYUGE": "conyuge", "CONCUBINA": "conyuge",
    "COMPARTEN HIJOS": "conyuge",
    "SOBRINO": "sobrino", "SOBRINA": "sobrina",
    "TIO PATERNO": "tio", "TIO MATERNO": "tio",
    "TIA PATERNA": "tia", "TIA MATERNA": "tia",
    "PRIMO PATERNO": "primo", "PRIMO MATERNO": "primo",
    "PRIMA PATERNA": "prima", "PRIMA MATERNA": "prima",
    "CUNADO": "cunado", "CUNADA": "cunada",
    "HERMANASTRO": "hermanastro", "HERMANASTRA": "hermanastra",
    "ABUELO": "abuelo", "ABUELA": "abuela",
    "NIETO": "nieto", "NIETA": "nieta",
    "SUEGRO": "suegro", "SUEGRA": "suegra",
    "YERNO": "yerno", "NUERA": "nuera",
}

# Mapeo de tipos de meta para extraer datos complementarios
_META_COMPLEMENT = {
    "TELEFONOS": ("telefonos", "TELEFONO"),
    "SUELDOS": ("sueldos", None),
    "DIRECCIONES": ("direcciones", "DIRECCION"),
    "CORREOS": ("correos", "CORREO"),
    "VEHICULOS": ("vehiculos", "PLACA"),
    "TRABAJOS": ("trabajos", None),
    "AFPS": ("afps", None),
    "HOGAR": ("hogar", None),
}


class LederResult:
    """Resultado acumulativo del parseo de un chat."""
    def __init__(self):
        self.p = 0       # personas creadas/actualizadas
        self.r = 0       # relaciones creadas
        self.e = 0       # empresas creadas/actualizadas
        self.v = 0       # vinculos persona-empresa creados
        self.err: List[str] = []  # errores


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE TEXTO
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_html(texto: str) -> str:
    """Convierte HTML a texto plano."""
    t = texto
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</(?:p|div|tr|li|h[1-6]|blockquote|pre)>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<[^>]+>', '', t)
    for entity, char in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "),
        ("&#10;", "\n"), ("&#13;", ""), ("&#39;", "'"), ("&quot;", "'"),
    ]:
        t = t.replace(entity, char)
    t = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t


def _campo(texto: str, campo: str) -> Optional[str]:
    """Extrae el valor de un campo: 'CAMPO : VALOR'."""
    m = re.search(
        r'^' + re.escape(campo) + r'\s*:\s*(.+?)$',
        texto, re.MULTILINE | re.IGNORECASE
    )
    if m:
        v = m.group(1).strip()
        return v if v and v != "-" else None
    return None


def _todos_campos(texto: str, campo: str) -> List[str]:
    """Extrae todas las ocurrencias de un campo."""
    return re.findall(
        r'^' + re.escape(campo) + r'\s*:\s*(.+?)$',
        texto, re.MULTILINE | re.IGNORECASE
    )


def _dni_limpio(texto: str) -> Optional[str]:
    """Extrae DNI (primeros 8 dígitos antes del guion opcional)."""
    dni = _campo(texto, "DNI")
    if not dni:
        return None
    return dni.split("-")[0].strip()


def _separar_nombre_completo_leder(nombre_completo: str):
    """'APELLIDO1 APELLIDO2 NOMBRES...' -> (nombres, ap_paterno, ap_materno)."""
    partes = nombre_completo.split()
    if len(partes) >= 3:
        return " ".join(partes[2:]), partes[0], partes[1]
    elif len(partes) == 2:
        return "", partes[0], partes[1]
    elif len(partes) == 1:
        return "", partes[0], None
    return "", "", None


def _extraer_edad(fecha_texto: str) -> Optional[str]:
    """Extrae la fecha de un texto tipo '06/12/1991 (32)' o '1991-05-02'."""
    if not fecha_texto:
        return None
    # dd/mm/aaaa (edad)
    m = re.match(r'(\d{2}/\d{2}/\d{4})', fecha_texto)
    if m:
        # Intentar convertir a date ISO
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
        except ValueError:
            return m.group(1)
    # aaaa-mm-dd
    m = re.match(r'(\d{4}-\d{2}-\d{2})', fecha_texto)
    if m:
        return m.group(1)
    return fecha_texto


def _nota_persona(persona: Persona, texto: str):
    """Acumula notas en una persona."""
    sep = "\n"
    if persona.notas:
        persona.notas += sep + texto
    else:
        persona.notas = texto


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE BD
# ═══════════════════════════════════════════════════════════════════════════════

def _obtener_o_crear_persona(
    db: Session, dni: str,
    nombres: str = "", ap_paterno: str = "", ap_materno: Optional[str] = None
) -> Persona:
    """Busca por DNI; si no existe la crea. Siempre retorna la persona."""
    p = db.query(Persona).filter(Persona.dni == dni).first()
    if p:
        # Actualizar datos si estaba pendiente
        if nombres and p.nombres == "PENDIENTE":
            p.nombres = nombres
        if ap_paterno and p.apellido_paterno == "PENDIENTE":
            p.apellido_paterno = ap_paterno
        if ap_materno and not p.apellido_materno:
            p.apellido_materno = ap_materno
        return p
    p = Persona(
        dni=dni,
        nombres=nombres or "PENDIENTE",
        apellido_paterno=ap_paterno or "PENDIENTE",
        apellido_materno=ap_materno,
    )
    db.add(p)
    db.flush()
    return p


def _crear_relacion(
    db: Session, dni_origen: str, dni_destino: str, tipo: str,
    certeza: str = "confirmado", notas: Optional[str] = None
) -> bool:
    """Crea una relacion entre dos personas si no existe."""
    origen = _obtener_o_crear_persona(db, dni_origen)
    destino = _obtener_o_crear_persona(db, dni_destino)
    existente = db.query(Relacion).filter(
        Relacion.persona_origen_id == origen.id,
        Relacion.persona_destino_id == destino.id,
        Relacion.tipo_relacion == tipo,
    ).first()
    if existente:
        return False
    db.add(Relacion(
        persona_origen_id=origen.id,
        persona_destino_id=destino.id,
        tipo_relacion=tipo,
        certeza=certeza,
        notas=notas,
    ))
    return True


def _actualizar_fecha_nac(db: Session, persona: Persona, fecha_str: Optional[str]):
    """Actualiza fecha_nacimiento si es valida."""
    if not fecha_str:
        return
    try:
        persona.fecha_nacimiento = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        # Intentar formatos alternativos
        for fmt in ("%d/%m/%Y", "%Y/%m/%d"):
            try:
                persona.fecha_nacimiento = datetime.strptime(fecha_str, fmt).date()
                return
            except (ValueError, TypeError):
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUES DE PERSONAS (compartido por varios detectores)
# ═══════════════════════════════════════════════════════════════════════════════

def _bloques_personas(texto: str) -> List[Dict[str, Any]]:
    """Divide un texto multilinea en bloques individuales de persona.
    Cada bloque empieza con 'DNI :' en una linea nueva."""
    bloques = []
    # Separar por lineas que empiezan con DNI :
    partes = re.split(r'\n(?=DNI\s*:\s*\d)', texto)
    for parte in partes:
        if not _campo(parte, "DNI"):
            continue
        dni = _dni_limpio(parte)
        if not dni:
            continue
        bloques.append({
            "dni": dni,
            "apellidos": _campo(parte, "APELLIDOS"),
            "nombres": _campo(parte, "NOMBRES"),
            "tipo": _campo(parte, "TIPO"),
            "genero": _campo(parte, "GENERO") or _campo(parte, "SEXO"),
            "verificacion": _campo(parte, "VERIFICACION RELACION"),
            "filiacion": _campo(parte, "FILIACION"),
            "fecha_nac": _extraer_edad(_campo(parte, "FECHA NACIMIENTO") or _campo(parte, "NACIMIENTO") or ""),
            "edad": _campo(parte, "EDAD"),
            "direccion": _campo(parte, "DIRECCION"),
            "estado_civil": _campo(parte, "ESTADO CIVIL"),
            "instruccion": _campo(parte, "GRADO INSTRUCCION"),
        })
    return bloques


def _crear_persona_desde_bloque(db: Session, blq: Dict[str, Any]) -> Persona:
    """Crea o actualiza una persona desde un bloque de datos."""
    ap = blq["apellidos"] or ""
    nom = blq["nombres"] or ""
    partes_ap = ap.split() if ap else []
    ap_p = partes_ap[0] if partes_ap else None
    ap_m = partes_ap[1] if len(partes_ap) > 1 else None
    p = _obtener_o_crear_persona(db, blq["dni"], nom, ap_p or "", ap_m)

    # Fecha de nacimiento
    if blq["fecha_nac"]:
        _actualizar_fecha_nac(db, p, blq["fecha_nac"])

    # Notas adicionales
    notas = []
    for label, val in [
        ("Genero", blq["genero"]),
        ("Estado civil", blq["estado_civil"]),
        ("Instruccion", blq["instruccion"]),
        ("Direccion", blq["direccion"]),
    ]:
        if val:
            notas.append(f"{label}: {val}")
    if blq["verificacion"]:
        notas.append(f"Verificacion: {blq['verificacion']}")
    if notas:
        _nota_persona(p, "[LEDER] " + "; ".join(notas))
    db.flush()
    return p


def _crear_persona_simple(
    db: Session, dni: str, apellidos: Optional[str], nombres: Optional[str]
) -> Persona:
    """Crea persona desde datos simples (sin bloque completo)."""
    ap = apellidos or ""
    nom = nombres or ""
    partes_ap = ap.split() if ap else []
    ap_p = partes_ap[0] if partes_ap else None
    ap_m = partes_ap[1] if len(partes_ap) > 1 else None
    return _obtener_o_crear_persona(db, dni, nom, ap_p or "", ap_m)


# ═══════════════════════════════════════════════════════════════════════════════
# PARSEADORES POR TIPO DE BLOQUE
# ═══════════════════════════════════════════════════════════════════════════════

def _parsear_reniec_nombres(db: Session, texto: str, res: LederResult) -> Optional[str]:
    """Parsea resultado de /nm (RENIEC NOMBRES).
    Retorna el DNI de la primera persona (para contexto)."""
    persona_creada = False
    primer_dni = None

    for blq in _bloques_personas(texto):
        if primer_dni is None:
            primer_dni = blq["dni"]
        _crear_persona_desde_bloque(db, blq)
        persona_creada = True

    if persona_creada:
        res.p += 1
    return primer_dni


def _parsear_reniec_online(db: Session, texto: str, res: LederResult) -> Optional[str]:
    """Parsea resultado de /dni (RENIEC ONLINE).
    Crea la persona con datos completos + padres como notas.
    Retorna el DNI."""
    dni = _dni_limpio(texto)
    if not dni:
        return None

    apellidos = _campo(texto, "APELLIDOS") or ""
    nombres = _campo(texto, "NOMBRES") or ""
    partes_ap = apellidos.split()
    ap_p = partes_ap[0] if partes_ap else None
    ap_m = partes_ap[1] if len(partes_ap) > 1 else None

    p = _obtener_o_crear_persona(db, dni, nombres, ap_p or "", ap_m)

    # Fecha nacimiento
    fn = _campo(texto, "FECHA NACIMIENTO")
    if fn:
        _actualizar_fecha_nac(db, p, _extraer_edad(fn) or fn)

    # Datos generales como notas
    notas = []
    for label in ["GENERO", "ESTADO CIVIL", "GRADO INSTRUCCION", "ESTATURA"]:
        val = _campo(texto, label)
        if val:
            notas.append(f"{label.capitalize()}: {val}")

    # Direccion
    dept = _campo(texto, "DEPARTAMENTO") or ""
    prov = _campo(texto, "PROVINCIA") or ""
    dist = _campo(texto, "DISTRITO") or ""
    direcc = _campo(texto, "DIRECCION") or ""
    if direcc:
        dir_full = f"{direcc}, {dist}, {prov}, {dept}".strip(", ")
        notas.append(f"Direccion: {dir_full}")

    # Padres (como nota, a menos que /ag detecte despues)
    padre = _campo(texto, "PADRE")
    madre = _campo(texto, "MADRE")
    if padre:
        notas.append(f"Padre: {padre}")
    if madre:
        notas.append(f"Madre: {madre}")

    # Fechas
    for label in ["FECHA INSCRIPCION", "FECHA EMISION", "FECHA CADUCIDAD"]:
        val = _campo(texto, label)
        if val:
            notas.append(f"{label}: {val}")

    if notas:
        _nota_persona(p, "[RENIEC] " + "; ".join(notas))

    # Crear a los padres como personas si tienen DNI en el campo
    # (los padres en RENIEC a veces son solo nombres, no DNIs)
    if padre:
        for token in re.findall(r'\b\d{8}\b', padre):
            _obtener_o_crear_persona(db, token, padre.replace(token, "").strip())
    if madre:
        for token in re.findall(r'\b\d{8}\b', madre):
            _obtener_o_crear_persona(db, token, madre.replace(token, "").strip())

    res.p += 1
    return dni


def _parsear_arbol_genealogico(db: Session, texto: str, dni_ctx: Optional[str], res: LederResult):
    """Parsea resultado de /ag (ARBOL GENEALOGICO).
    Crea todas las personas del arbol y las relaciones."""
    for blq in _bloques_personas(texto):
        p = _crear_persona_desde_bloque(db, blq)
        res.p += 1

        # Determinar relacion con el contexto (persona consultada)
        tipo = (blq["tipo"] or blq["filiacion"] or "").upper().strip()
        if not tipo or tipo in ("JEFE(A)", "", "NINGUNA"):
            continue

        # Si hay DNI de contexto, crear relacion entre dni_ctx y esta persona
        if not dni_ctx:
            continue

        # Mapear tipo de relacion
        rel_base = _TIPO_A_RELACION.get(tipo)
        if rel_base:
            if _crear_relacion(db, dni_ctx, blq["dni"], rel_base,
                               "documento", f"LEDER: {tipo}"):
                res.r += 1
        elif tipo in ("HIJO", "HIJA"):
            if _crear_relacion(db, dni_ctx, blq["dni"], "hijo",
                               "documento", f"LEDER: {tipo}"):
                res.r += 1
        else:
            # Relacion no mapeada → nota
            _nota_persona(p, f"[LEDER] Relacion no mapeada: {tipo}")


def _parsear_meta_familia_1(db: Session, texto: str, dni_ctx: Optional[str], res: LederResult):
    """Parsea META | FAMILIA [1] (jefe/hijos de RENIEC)."""
    for blq in _bloques_personas(texto):
        p = _crear_persona_desde_bloque(db, blq)
        res.p += 1
        if not dni_ctx:
            continue
        filiacion = (blq["filiacion"] or "").upper()
        if filiacion == "HIJO":
            if _crear_relacion(db, dni_ctx, blq["dni"], "hijo", "documento"):
                res.r += 1


def _parsear_meta_familia_2(db: Session, texto: str, dni_ctx: Optional[str], res: LederResult):
    """Parsea META | FAMILIA [2] (padres, tios, primos, hermanos)."""
    for blq in _bloques_personas(texto):
        p = _crear_persona_desde_bloque(db, blq)
        res.p += 1
        if not dni_ctx:
            continue
        tipo = (blq["tipo"] or "").upper().strip()
        if not tipo:
            continue
        rel_base = _TIPO_A_RELACION.get(tipo)
        if rel_base:
            if _crear_relacion(db, dni_ctx, blq["dni"], rel_base,
                               "documento", f"LEDER: {tipo}"):
                res.r += 1


def _parsear_meta_empresas(db: Session, texto: str, dni_ctx: Optional[str], res: LederResult):
    """Parsea META | EMPRESAS: vincula persona a empresas."""
    for bloque in re.split(r'\n(?=DNI\s*:\s*\d)', texto):
        dni_str = _campo(bloque, "DNI")
        if not dni_str:
            continue
        dni = dni_str.split("-")[0].strip() if "-" in dni_str else dni_str.strip()
        ruc = _campo(bloque, "RUC")
        rz = _campo(bloque, "RAZON SOCIAL")
        cargo = _campo(bloque, "CARGO") or "trabajador"
        desde = _campo(bloque, "DESDE")
        if not ruc or not rz:
            continue

        empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
        if not empresa:
            empresa = Empresa(ruc=ruc, nombre=rz)
            db.add(empresa)
            db.flush()
            res.e += 1

        # Vincular persona a empresa
        p = _obtener_o_crear_persona(db, dni)
        vinculo = db.query(PersonaEmpresa).filter(
            PersonaEmpresa.persona_id == p.id,
            PersonaEmpresa.empresa_id == empresa.id,
            PersonaEmpresa.cargo == cargo,
        ).first()
        if not vinculo:
            obs = f"Desde: {desde}" if desde else None
            db.add(PersonaEmpresa(
                persona_id=p.id, empresa_id=empresa.id,
                cargo=cargo, observacion=obs,
            ))
            res.v += 1


def _parsear_meta_sunat(db: Session, texto: str, res: LederResult):
    """Parsea META | SUNAT: crea/actualiza empresa."""
    ruc = _campo(texto, "RUC")
    rz = _campo(texto, "RAZON SOCIAL")
    estado = _campo(texto, "ESTADO")
    condicion = _campo(texto, "CONDICION")
    if not ruc:
        return
    empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
    if not empresa:
        empresa = Empresa(ruc=ruc, nombre=rz or f"RUC {ruc}")
        db.add(empresa)
        db.flush()
        res.e += 1
    if estado:
        empresa.estado = estado
    if condicion:
        empresa.condicion = condicion


def _parsear_meta_base(db: Session, texto: str, res: LederResult) -> Optional[str]:
    """Parsea META (basico): datos de persona + crea persona."""
    dni = _dni_limpio(texto)
    if not dni:
        return None

    apellidos = _campo(texto, "APELLIDOS") or ""
    nombres = _campo(texto, "NOMBRES") or ""
    partes_ap = apellidos.split()
    ap_p = partes_ap[0] if partes_ap else None
    ap_m = partes_ap[1] if len(partes_ap) > 1 else None

    p = _obtener_o_crear_persona(db, dni, nombres, ap_p or "", ap_m)

    # Fecha nacimiento
    fn = _campo(texto, "FECHA NACIMIENTO")
    if fn:
        _actualizar_fecha_nac(db, p, _extraer_edad(fn) or fn)

    # Notas
    notas = []
    for label in ["GENERO", "ESTADO CIVIL", "GRADO INSTRUCCION", "ESTATURA"]:
        val = _campo(texto, label)
        if val:
            notas.append(f"{label.capitalize()}: {val}")
    direcc = _campo(texto, "DIRECCION")
    if direcc:
        dept = _campo(texto, "DEPARTAMENTO") or ""
        prov = _campo(texto, "PROVINCIA") or ""
        dist = _campo(texto, "DISTRITO") or ""
        notas.append(f"Direccion: {direcc}, {dist}, {prov}, {dept}".strip(", "))
    if notas:
        _nota_persona(p, "[META] " + "; ".join(notas))

    res.p += 1
    return dni


def _parsear_meta_complement(
    db: Session, texto: str, tipo: str, dni_ctx: Optional[str]
):
    """Parsea meta complementario (telefonos, sueldos, etc.) y lo agrega como nota."""
    if not dni_ctx:
        return
    p = db.query(Persona).filter(Persona.dni == dni_ctx).first()
    if not p:
        return

    config = _META_COMPLEMENT.get(tipo)
    if not config:
        return

    campo_label, campo_extract = config
    datos = []

    if tipo == "TELEFONOS":
        telefonos = _todos_campos(texto, "TELEFONO")
        if telefonos:
            lines = []
            for tel in set(telefonos):
                lines.append(tel)
            datos.append(f"Tel: {', '.join(lines[:5])}")

    elif tipo == "SUELDOS":
        empresas = _todos_campos(texto, "EMPRESA")
        sueldos = _todos_campos(texto, "SUELDO")
        periodos = _todos_campos(texto, "PERIODO")
        if empresas and sueldos:
            resumen = []
            seen = set()
            for i in range(min(len(empresas), len(sueldos))):
                emp_short = empresas[i].split("SOCIEDAD")[0].strip()[:40]
                key = emp_short
                if key not in seen:
                    seen.add(key)
                    resumen.append(f"{emp_short}: {sueldos[i]}")
            if resumen:
                datos.append(f"Sueldos: {'; '.join(resumen[:3])}")

    elif tipo == "DIRECCIONES":
        dirs = list(set(_todos_campos(texto, "DIRECCION")))[:3]
        if dirs:
            datos.append(f"Direcciones: {'; '.join(dirs)}")

    elif tipo == "CORREOS":
        mails = list(set(_todos_campos(texto, "CORREO")))[:5]
        if mails:
            datos.append(f"Email: {', '.join(mails)}")

    elif tipo == "VEHICULOS":
        placas = list(set(_todos_campos(texto, "PLACA")))[:3]
        if placas:
            datos.append(f"Veh: {', '.join(placas)}")

    elif tipo == "TRABAJOS":
        empresas = list(set(_todos_campos(texto, "TRABAJO")))[:3]
        if empresas:
            datos.append(f"Trabajos: {'; '.join(empresas)}")

    if datos:
        _nota_persona(p, "[LEDER] " + "; ".join(datos))


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTOR DE TIPO DE BLOQUE
# ═══════════════════════════════════════════════════════════════════════════════

def _detectar_tipo(msg: str) -> Optional[str]:
    """Detecta el tipo de bloque LEDER_BOT."""
    # Normalizar: tomar la primera linea con [#LEDER_BOT]
    lineas = msg.split('\n')
    titulo = ""
    for l in lineas:
        if "[#LEDER_BOT]" in l:
            titulo = l.upper()
            break

    if "RENIEC NOMBRES" in titulo:
        return "RENIEC_NOMBRES"
    if "RENIEC ONLINE" in titulo or "RENIEC [PREMIUM]" in msg.upper():
        return "RENIEC_ONLINE"
    if "ARBOL GENEALOGICO" in titulo:
        return "ARBOL_GENEALOGICO"
    if "META | FAMILIA [1]" in titulo or "META | FAMILIA [1]" in msg:
        return "FAMILIA_1"
    if "META | FAMILIA [2]" in titulo or "META | FAMILIA [2]" in msg:
        return "FAMILIA_2"
    if "META | EMPRESAS" in titulo:
        return "EMPRESAS"
    if "META | SUNAT" in titulo:
        return "SUNAT"
    if "META | TELEFONOS" in titulo:
        return "TELEFONOS"
    if "META | SUELDOS" in titulo:
        return "SUELDOS"
    if "META | DIRECCIONES" in titulo:
        return "DIRECCIONES"
    if "META | CORREOS" in titulo:
        return "CORREOS"
    if "META | VEHICULOS" in titulo:
        return "VEHICULOS"
    if "META | TRABAJOS" in titulo:
        return "TRABAJOS"
    if "META | AFPS" in titulo:
        return "AFPS"
    if "META | HOGAR" in titulo:
        return "HOGAR"
    if "META" in titulo and "[PREMIUM]" in msg:
        return "META_BASE"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def procesar_texto_leder(db: Session, raw: str) -> LederResult:
    """
    Parsea un chat Telegram completo de LEDER_BOT.

    El chat puede contener:
    - Mensajes de usuario (/nm, /dni, /ag, /meta, etc.)
    - Respuestas del bot ([#LEDER_BOT])
    - Fotos, PDFs, enlaces
    """
    res = LederResult()
    raw = _strip_html(raw)
    raw = raw.replace("\n", "\n").replace("\n", "\n")

    # Dividir en bloques de [#LEDER_BOT]
    bloques = re.split(r'(?=\[#LEDER_BOT\])', raw)

    dni_ctx: Optional[str] = None  # DNI de la persona actualmente consultada

    for bloque in bloques:
        bloque = bloque.strip()
        if not bloque:
            continue

        tipo = _detectar_tipo(bloque)
        if not tipo:
            continue

        try:
            if tipo == "RENIEC_NOMBRES":
                dn = _parsear_reniec_nombres(db, bloque, res)
                if dn:
                    dni_ctx = dn

            elif tipo == "RENIEC_ONLINE":
                dn = _parsear_reniec_online(db, bloque, res)
                if dn:
                    dni_ctx = dn

            elif tipo == "ARBOL_GENEALOGICO":
                _parsear_arbol_genealogico(db, bloque, dni_ctx, res)

            elif tipo == "FAMILIA_1":
                _parsear_meta_familia_1(db, bloque, dni_ctx, res)

            elif tipo == "FAMILIA_2":
                _parsear_meta_familia_2(db, bloque, dni_ctx, res)

            elif tipo == "EMPRESAS":
                _parsear_meta_empresas(db, bloque, dni_ctx, res)

            elif tipo == "SUNAT":
                _parsear_meta_sunat(db, bloque, res)

            elif tipo == "META_BASE":
                dn = _parsear_meta_base(db, bloque, res)
                if dn:
                    dni_ctx = dn

            elif tipo in _META_COMPLEMENT:
                _parsear_meta_complement(db, bloque, tipo, dni_ctx)

        except Exception as e:
            res.err.append(f"Error en bloque {tipo}: {str(e)[:80]}")
            try:
                db.rollback()
            except Exception:
                pass

    try:
        db.commit()
    except Exception as e:
        res.err.append(f"Error al guardar: {str(e)[:100]}")
        db.rollback()
    return res
