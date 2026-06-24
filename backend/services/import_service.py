"""
import_service.py — Importador unificado de RedCorruptela.

Antes existían 5 endpoints distintos con lógica de detección de tipo de RUC,
creación de etiquetas, y dedupe de Persona/Empresa duplicada en 3-4 lugares
(main.py:_batch_import, main.py:api_importar_empresas_inteligente,
main.py:api_db_importar). Este módulo concentra esa lógica en un solo lugar:

    ejecutar_importacion(db, datos, user) -> ImportOut

Formatos soportados (auto-detectados o forzados via `formato`):
    - csv               : lista estructurada de PersonaCreate (ex /api/db/importar)
    - ruc_batch         : listado tabulado "RUC<TAB>NOMBRE" (ex modo batch de
                          /api/db/importar-inteligente)
    - sunat_macro       : 21 columnas tabuladas de la macro SUNAT
                          (ex /api/empresas/importar-inteligente)
    - leder_individual  : reporte individual LEDER DATA pegado a mano
                          (ex modo individual de /api/db/importar-inteligente)
    - leder_telegram    : export HTML de Telegram del bot LEDER_DATA_BOT
                          (ex /api/importar/leder-telegram, delega en leder_parser.py)
"""

import re
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from models import Persona, Empresa, PersonaEmpresa, Relacion, PersonaEtiqueta, EmpresaEtiqueta
from schemas import ImportarRequest, ImportOut, PersonaCreate, FORMATOS_IMPORTACION
from crud import crear_o_obtener_etiqueta, registrar_auditoria
from services.leder_parser import procesar_texto_leder


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS COMPARTIDOS (antes duplicados en cada importador)
# ═══════════════════════════════════════════════════════════════════════════════

def _etiquetar_persona(db: Session, persona_id: int, etiqueta_id: Optional[int]) -> bool:
    if not etiqueta_id:
        return False
    existe = db.query(PersonaEtiqueta).filter(
        PersonaEtiqueta.persona_id == persona_id,
        PersonaEtiqueta.etiqueta_id == etiqueta_id,
    ).first()
    if existe:
        return False
    db.add(PersonaEtiqueta(persona_id=persona_id, etiqueta_id=etiqueta_id))
    return True


def _etiquetar_empresa(db: Session, empresa_id: int, etiqueta_id: Optional[int]) -> bool:
    if not etiqueta_id:
        return False
    existe = db.query(EmpresaEtiqueta).filter(
        EmpresaEtiqueta.empresa_id == empresa_id,
        EmpresaEtiqueta.etiqueta_id == etiqueta_id,
    ).first()
    if existe:
        return False
    db.add(EmpresaEtiqueta(empresa_id=empresa_id, etiqueta_id=etiqueta_id))
    return True


def _obtener_o_crear_persona(db: Session, dni: str, nombres: str = "", ap_paterno: str = "",
                              ap_materno: Optional[str] = None):
    """Busca una Persona por DNI; si no existe, la crea. Retorna (persona, creada: bool)."""
    persona = db.query(Persona).filter(Persona.dni == dni).first()
    if persona:
        return persona, False
    persona = Persona(
        dni=dni,
        nombres=nombres or "PENDIENTE",
        apellido_paterno=ap_paterno or "PENDIENTE",
        apellido_materno=ap_materno,
    )
    db.add(persona)
    db.flush()
    return persona, True


def _obtener_o_crear_empresa(db: Session, ruc: str, nombre: str = ""):
    """Busca una Empresa por RUC; si no existe, la crea. Retorna (empresa, creada: bool)."""
    empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
    if empresa:
        return empresa, False
    empresa = Empresa(ruc=ruc, nombre=nombre or f"EMPRESA {ruc}")
    db.add(empresa)
    db.flush()
    return empresa, True


def _vincular_si_no_existe(db: Session, persona_id: int, empresa_id: int, cargo: str) -> bool:
    existe = db.query(PersonaEmpresa).filter(
        PersonaEmpresa.persona_id == persona_id,
        PersonaEmpresa.empresa_id == empresa_id,
        PersonaEmpresa.cargo == cargo,
    ).first()
    if existe:
        return False
    db.add(PersonaEmpresa(persona_id=persona_id, empresa_id=empresa_id, cargo=cargo))
    return True


def _separar_nombre_completo(nombre_completo: str):
    """'APELLIDO1 APELLIDO2 NOMBRES...' -> (nombres, ap_paterno, ap_materno)."""
    partes = nombre_completo.split()
    if len(partes) >= 3:
        return " ".join(partes[2:]), partes[0], partes[1]
    if len(partes) == 2:
        return "", partes[0], partes[1]
    if len(partes) == 1:
        return "", partes[0], None
    return "", "", None


def _parsear_nombre_ruc10(texto: str):
    """Campo 'Número de RUC:' de un RUC 10 → 'RUC - APELLIDOS NOMBRES'."""
    if " - " in texto:
        texto = texto.split(" - ", 1)[1].strip()
    return _separar_nombre_completo(texto)


def _parsear_representante_legal(texto: str):
    texto = texto.strip()
    if not texto or texto.lower().startswith("no se encontr"):
        return None, None
    if " - " in texto:
        nombre, cargo = texto.split(" - ", 1)
        return nombre.strip(), cargo.strip()
    return texto, "representante legal"


def _buscar_persona_por_nombre(db: Session, nombre_completo: str):
    """Busca una persona por nombre completo. Retorna la persona o None."""
    nom, ap_p, ap_m = _separar_nombre_completo(nombre_completo)
    if not ap_p:
        return None
    q = db.query(Persona).filter(
        Persona.activo == True,
        Persona.apellido_paterno.ilike(ap_p),
    )
    if ap_m:
        q = q.filter(Persona.apellido_materno.ilike(ap_m))
    if nom:
        # Coincidir con al menos una palabra del nombre
        for palabra in nom.split():
            q = q.filter(Persona.nombres.ilike(f"%{palabra}%"))
    return q.first()


def _aplicar_campos_sunat(empresa: Empresa, partes: List[str]):
    """Mapea las 21 columnas tabuladas de la macro SUNAT al modelo Empresa."""
    def v(idx):
        return partes[idx].strip() if len(partes) > idx and partes[idx].strip() else None

    campos = {
        2: "tipo_contribuyente", 3: "nombre_comercial", 4: "fecha_inscripcion",
        5: "fecha_inicio_actividades", 6: "estado", 7: "condicion", 8: "direccion",
        9: "sistema_emision", 10: "actividad_comercio_exterior", 11: "sistema_contabilidad",
        12: "actividad_economica", 13: "comprobantes_autorizados",
        14: "sistema_emision_electronica", 15: "emisor_electronico_desde",
        16: "comprobantes_electronicos", 17: "afiliado_ple", 18: "padrones",
        20: "establecimientos",
    }
    for idx, attr in campos.items():
        val = v(idx)
        if val:
            setattr(empresa, attr, val)


# ═══════════════════════════════════════════════════════════════════════════════
# DETECCIÓN DE FORMATO
# ═══════════════════════════════════════════════════════════════════════════════

def detectar_formato(datos: ImportarRequest) -> str:
    if datos.personas is not None:
        return "csv"

    texto = (datos.texto or "").strip()
    if not texto:
        return "csv"  # dejara que el handler reporte "sin datos"

    if "[#LEDER_BOT]" in texto:
        return "leder_telegram"

    primera_linea = texto.split("\n", 1)[0].strip().upper()
    if "INGRESAR EL NUMERO DE RUC" in primera_linea:
        return "sunat_macro"

    if re.search(r"^\s*DNI\s*:", texto, re.MULTILINE) and re.search(r"^\s*NOMBRES\s*:", texto, re.MULTILINE | re.IGNORECASE):
        return "leder_individual"

    # Detectar SUNAT macro multi-columna sin header:
    # primera linea empieza con RUC + TAB + 10+ tabs (11+ columnas)
    primera_data = texto.split("\n", 1)[0].strip()
    num_tabs = primera_data.count("\t")
    if re.match(r"^\d{11}\t", primera_data) and num_tabs >= 10:
        return "sunat_macro"

    # Heuristica RUC batch: primera linea tabulada o "11digitos resto"
    if "\t" in primera_linea or (len(primera_linea) >= 11 and primera_linea[2:10].isdigit()):
        return "ruc_batch"

    # Fallback: si la primera linea empieza con 11 digitos numericos seguidos de espacio
    if re.match(r"^\d{11}\s", texto):
        return "ruc_batch"

    return "leder_individual"


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS POR FORMATO
# ═══════════════════════════════════════════════════════════════════════════════

def _importar_csv(db: Session, personas: List[PersonaCreate]) -> ImportOut:
    creados = 0
    errores = []
    for datos in personas:
        try:
            existente = db.query(Persona).filter(Persona.dni == datos.dni).first()
            if existente:
                errores.append(f"DNI {datos.dni}: ya existe")
                continue
            db.add(Persona(
                dni=datos.dni, nombres=datos.nombres,
                apellido_paterno=datos.apellido_paterno,
                apellido_materno=datos.apellido_materno,
                fecha_nacimiento=datos.fecha_nacimiento,
                foto_url=datos.foto_url, notas=datos.notas,
            ))
            creados += 1
        except Exception as e:
            errores.append(f"DNI {datos.dni}: {str(e)[:100]}")
    db.flush()
    return ImportOut(
        mensaje=f"Importacion completada: {creados} creados, {len(errores)} errores",
        total_procesadas=len(personas), personas_creadas=creados, errores=errores,
    )


def _importar_ruc_batch(db: Session, texto: str, etiqueta_id: Optional[int], etiqueta_nombre: str) -> ImportOut:
    errores = []
    personas_data = []
    empresas_data = []

    for line in texto.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        partes = line.split("\t")
        ruc = partes[0].strip() if partes else ""
        nombre_completo = partes[1].strip() if len(partes) > 1 else ""
        if not nombre_completo:
            m = re.match(r"^(\d{11})\s+(.+)", line)
            if m:
                ruc, nombre_completo = m.group(1), m.group(2).strip()
        if not nombre_completo:
            continue
        if len(ruc) != 11 or not ruc.isdigit():
            errores.append(f"RUC invalido ({ruc}): {nombre_completo}")
            continue

        if ruc[0] == "1":
            dni = ruc[2:10]
            if not dni.isdigit():
                errores.append(f"DNI invalido en RUC {ruc}: {nombre_completo}")
                continue
            nom, ap_p, ap_m = _parsear_nombre_ruc10(nombre_completo)
            personas_data.append({"dni": dni, "nombres": nom, "ap_p": ap_p, "ap_m": ap_m, "ruc": ruc, "nombre": nombre_completo})
        elif ruc[0] in ("2", "3"):
            empresas_data.append({"ruc": ruc, "nombre": nombre_completo})
        else:
            errores.append(f"Tipo RUC no reconocido ({ruc[0]}): {nombre_completo}")

    if not personas_data and not empresas_data:
        return ImportOut(mensaje="No se encontraron datos validos", errores=errores)

    pc = ec = vc = rc = pet = eet = 0
    for pdata in personas_data:
        persona, creada = _obtener_o_crear_persona(db, pdata["dni"], pdata["nombres"], pdata["ap_p"], pdata["ap_m"])
        if creada:
            pc += 1
        if _etiquetar_persona(db, persona.id, etiqueta_id):
            pet += 1

        # Crear empresa RUC-10 y vincular persona como titular
        empresa, e_creada = _obtener_o_crear_empresa(db, pdata["ruc"], persona.nombre_completo)
        if e_creada:
            ec += 1
        if _etiquetar_empresa(db, empresa.id, etiqueta_id):
            eet += 1
        if _vincular_si_no_existe(db, persona.id, empresa.id, "titular - persona natural con negocio"):
            vc += 1

    for edata in empresas_data:
        empresa, creada = _obtener_o_crear_empresa(db, edata["ruc"], edata["nombre"])
        if creada:
            ec += 1
        if _etiquetar_empresa(db, empresa.id, etiqueta_id):
            eet += 1

    db.commit()
    tet = pet + eet
    partes_msg = []
    if pc: partes_msg.append(f"{pc} persona(s) creada(s)")
    if ec: partes_msg.append(f"{ec} empresa(s) creada(s)")
    if vc: partes_msg.append(f"{vc} vinculo(s) RUC-10")
    if tet: partes_msg.append(f"{tet} etiquetado(s) como '{etiqueta_nombre}'")
    if not partes_msg: partes_msg.append("Todo ya existia")

    return ImportOut(
        mensaje=f"Batch: {', '.join(partes_msg)}",
        total_procesadas=len(personas_data) + len(empresas_data),
        personas_creadas=pc, empresas_creadas=ec, vinculos_creados=vc, etiquetados=tet, errores=errores,
    )


def _importar_sunat_macro(db: Session, texto: str, etiqueta_id: Optional[int], etiqueta_nombre: str) -> ImportOut:
    lineas = [l.strip() for l in texto.strip().split("\n") if l.strip()]
    if not lineas:
        return ImportOut(mensaje="No hay datos para importar", errores=["texto vacio"])

    tiene_header = "INGRESAR EL NUMERO DE RUC" in lineas[0].upper()
    inicio = 1 if tiene_header else 0

    out = ImportOut(mensaje="")
    commit_cada = 5
    for i in range(inicio, len(lineas)):
        partes = lineas[i].split("\t")
        if len(partes) < 2:
            continue
        ruc = partes[0].strip()
        if len(ruc) != 11 or not ruc.isdigit():
            out.errores.append(f"Linea {i + 1}: RUC invalido '{ruc}'")
            continue

        # Commit periódico cada N RUCs para mantener la conexión activa
        # y evitar errores 7s2a (DisconnectionError) por transacciones largas
        if (i - inicio) > 0 and (i - inicio) % commit_cada == 0:
            db.flush()
            db.commit()

        out.total_procesadas += 1
        try:
            if ruc[0] == "1":
                dni = ruc[2:10]
                nom, ap_p, ap_m = _parsear_nombre_ruc10(partes[1].strip() if len(partes) > 1 else "")
                persona, p_creada = _obtener_o_crear_persona(db, dni, nom, ap_p, ap_m)
                if p_creada:
                    out.personas_creadas += 1
                    if _etiquetar_persona(db, persona.id, etiqueta_id):
                        out.etiquetados += 1

                empresa, e_creada = _obtener_o_crear_empresa(db, ruc, persona.nombre_completo)
                if e_creada:
                    out.empresas_creadas += 1
                    if _etiquetar_empresa(db, empresa.id, etiqueta_id):
                        out.etiquetados += 1
                else:
                    out.empresas_actualizadas += 1

                if _vincular_si_no_existe(db, persona.id, empresa.id, "titular - persona natural con negocio"):
                    out.vinculos_creados += 1

                _aplicar_campos_sunat(empresa, partes)

            elif ruc[0] in ("2", "3"):
                nombre_empresa = ""
                if len(partes) > 1:
                    txt = partes[1].strip()
                    nombre_empresa = txt.split(" - ", 1)[1].strip() if " - " in txt else txt

                empresa, e_creada = _obtener_o_crear_empresa(db, ruc, nombre_empresa)
                if e_creada:
                    out.empresas_creadas += 1
                    if _etiquetar_empresa(db, empresa.id, etiqueta_id):
                        out.etiquetados += 1
                else:
                    out.empresas_actualizadas += 1

                _aplicar_campos_sunat(empresa, partes)

                if len(partes) > 19:
                    rep_nombre, rep_cargo = _parsear_representante_legal(partes[19].strip())
                    if rep_nombre:
                        empresa.representante_legal_nombre = rep_nombre
                        empresa.representante_legal_dni = ""
                        rep_dni_encontrado = False

                        # Buscar persona por nombre completo (ap_paterno + ap_materno + nombres)
                        nom_rep, ap_p_rep, ap_m_rep = _separar_nombre_completo(rep_nombre)
                        if ap_p_rep:
                            rep_existente = _buscar_persona_por_nombre(db, rep_nombre)
                            if rep_existente:
                                empresa.representante_legal_dni = rep_existente.dni
                                rep_dni_encontrado = True
                                rep_persona = rep_existente
                            else:
                                # Crear persona con DNI sintetico
                                rep_persona, rep_creada = _obtener_o_crear_persona(
                                    db, f"REP-{ruc}", nom_rep or rep_nombre, ap_p_rep or "PENDIENTE", ap_m_rep,
                                )
                                if rep_creada:
                                    out.personas_creadas += 1
                                    if _etiquetar_persona(db, rep_persona.id, etiqueta_id):
                                        out.etiquetados += 1
                        else:
                            # No se pudo separar el nombre, crear con DNI sintetico
                            rep_persona, rep_creada = _obtener_o_crear_persona(
                                db, f"REP-{ruc}", rep_nombre, "PENDIENTE", None,
                            )
                            if rep_creada:
                                out.personas_creadas += 1

                        cargo_real = rep_cargo or "representante legal"
                        if _vincular_si_no_existe(db, rep_persona.id, empresa.id, cargo_real):
                            out.representantes_vinculados += 1
                            out.vinculos_creados += 1
            else:
                out.errores.append(f"RUC {ruc}: tipo no soportado ({ruc[0]})")
        except Exception as e:
            out.errores.append(f"RUC {ruc}: {str(e)[:100]}")

    db.flush()

    partes_msg = []
    if out.empresas_creadas: partes_msg.append(f"{out.empresas_creadas} empresa(s) creada(s)")
    if out.empresas_actualizadas: partes_msg.append(f"{out.empresas_actualizadas} actualizada(s)")
    if out.personas_creadas: partes_msg.append(f"{out.personas_creadas} persona(s) creada(s)")
    if out.vinculos_creados: partes_msg.append(f"{out.vinculos_creados} vinculo(s)")
    if out.representantes_vinculados: partes_msg.append(f"{out.representantes_vinculados} rep. legal(es)")
    if out.etiquetados: partes_msg.append(f"{out.etiquetados} etiquetado(s)")
    if not partes_msg: partes_msg.append("Todo ya existia en BD")

    errores_str = f" ({len(out.errores)} error(es))" if out.errores else ""
    out.mensaje = f"Importacion completada: {', '.join(partes_msg)}{errores_str}"
    return out


def _importar_leder_individual(db: Session, texto: str, etiqueta_id: Optional[int], etiqueta_nombre: str) -> ImportOut:
    errores = []
    familiares_creados = 0

    m = re.search(r"DNI\s*:\s*(\d+)", texto)
    dni = m.group(1).strip() if m else None
    if not dni:
        return ImportOut(mensaje="No se encontro DNI en el texto", errores=["DNI no encontrado"])

    m_nombres = re.search(r"NOMBRES\s*:\s*(.+)", texto)
    m_ape = re.search(r"APELLIDOS\s*:\s*(.+)", texto)
    m_fec = re.search(r"FECHA NACIMIENTO\s*:\s*(\d{2}/\d{2}/\d{4})", texto)

    nombres = m_nombres.group(1).strip() if m_nombres else ""
    apellidos = m_ape.group(1).strip() if m_ape else ""
    ape_parts = apellidos.split() if apellidos else []
    ap_paterno = ape_parts[0] if ape_parts else ""
    ap_materno = ape_parts[1] if len(ape_parts) > 1 else None

    fecha_nac = None
    if m_fec:
        try:
            fecha_nac = datetime.strptime(m_fec.group(1), "%d/%m/%Y").date()
        except ValueError:
            pass

    persona, creada = _obtener_o_crear_persona(db, dni, nombres, ap_paterno, ap_materno)
    if fecha_nac:
        persona.fecha_nacimiento = fecha_nac
    if creada:
        _etiquetar_persona(db, persona.id, etiqueta_id)

    trabajo_reg = None
    m_trabajo_rs = re.search(r"RAZON SOCIAL\s*:\s*(.+)", texto)
    if m_trabajo_rs:
        empresa_nombre = m_trabajo_rs.group(1).strip()
        if empresa_nombre and empresa_nombre != "No se encontro":
            empresa = db.query(Empresa).filter(Empresa.nombre == empresa_nombre, Empresa.activo == True).first()
            if not empresa:
                empresa = Empresa(ruc=f"AUTO-{persona.dni}", nombre=empresa_nombre)
                db.add(empresa)
                db.flush()
            if _vincular_si_no_existe(db, persona.id, empresa.id, "trabajador"):
                trabajo_reg = empresa_nombre

    # Bloques de familiares (formato repetido DNI/APELLIDOS/NOMBRES/.../TIPO)
    current_block = {}
    for line in texto.split("\n"):
        ls = line.strip()
        if ls.startswith("DNI") and ":" in ls:
            current_block = {"dni": ls.split(":", 1)[1].strip()}
        elif ls.startswith("APELLIDOS"):
            current_block["apellidos"] = ls.split(":", 1)[1].strip()
        elif ls.startswith("NOMBRES"):
            current_block["nombres"] = ls.split(":", 1)[1].strip()
        elif ls.startswith("TIPO") and ":" in ls:
            current_block["tipo"] = ls.split(":", 1)[1].strip()
            if current_block.get("dni") and current_block.get("tipo"):
                try:
                    familiares_creados += _procesar_familiar_leder(db, persona, current_block)
                except Exception as e:
                    errores.append(f"Error familiar DNI {current_block.get('dni', '?')}: {str(e)}")

    db.commit()

    mensaje = f"Importado: {persona.nombre_completo}"
    if trabajo_reg: mensaje += f" - Trabaja en: {trabajo_reg}"
    if familiares_creados: mensaje += f" - {familiares_creados} familiar(es)"
    if etiqueta_nombre: mensaje += f" - Etiquetado: {etiqueta_nombre}"
    if errores: mensaje += f" - {len(errores)} error(es)"

    return ImportOut(
        mensaje=mensaje, persona_dni=persona.dni, relaciones_creadas=familiares_creados,
        empresa_registrada=trabajo_reg, errores=errores,
    )


_TIPO_A_RELACION = {
    "MADRE": ("origen_es_familiar", "madre"),
    "PADRE": ("origen_es_familiar", "padre"),
    "HIJA": ("origen_es_persona", "padre"),
    "HIJO": ("origen_es_persona", "padre"),
    "HERMANA": ("origen_es_persona", "hermano"),
    "HERMANO": ("origen_es_persona", "hermano"),
    "HIJASTRA": ("origen_es_persona", "padre"),
    "HIJASTRO": ("origen_es_persona", "padre"),
    "CONYUGE": ("origen_es_persona", "conyuge"),
    "ESPOSO": ("origen_es_persona", "conyuge"),
    "ESPOSA": ("origen_es_persona", "conyuge"),
    "COMPARTEN HIJOS": ("origen_es_persona", "conyuge"),
}


def _procesar_familiar_leder(db: Session, persona: Persona, block: dict) -> int:
    fdni = block["dni"]
    if fdni == persona.dni:
        return 0
    ftipo = block["tipo"].upper().strip()
    regla = _TIPO_A_RELACION.get(ftipo)
    if not regla:
        return 0

    fnombres = block.get("nombres", "")
    fapellidos = block.get("apellidos", "")
    ape_p = fapellidos.split() if fapellidos else [""]
    familiar, _ = _obtener_o_crear_persona(
        db, fdni, fnombres, ape_p[0] if ape_p else "", ape_p[1] if len(ape_p) > 1 else None,
    )

    modo, rel_tipo = regla
    origen_id, destino_id = (familiar.id, persona.id) if modo == "origen_es_familiar" else (persona.id, familiar.id)

    existente = db.query(Relacion).filter(
        Relacion.persona_origen_id == origen_id,
        Relacion.persona_destino_id == destino_id,
        Relacion.tipo_relacion == rel_tipo,
    ).first()
    if existente:
        return 0
    db.add(Relacion(
        persona_origen_id=origen_id, persona_destino_id=destino_id,
        tipo_relacion=rel_tipo, certeza="documento",
    ))
    return 1


def _importar_leder_telegram(db: Session, texto: str) -> ImportOut:
    if not texto.strip():
        return ImportOut(mensaje="No hay datos para importar", errores=["texto vacio"])

    result = procesar_texto_leder(db, texto)

    partes = []
    if result.p: partes.append(f"{result.p} persona(s)")
    if result.r: partes.append(f"{result.r} relacion(es)")
    if result.e: partes.append(f"{result.e} empresa(s)")
    if result.v: partes.append(f"{result.v} vinculo(s)")
    errores_str = f" ({len(result.err)} error(es))" if result.err else ""
    mensaje = f"Importacion completada: {', '.join(partes) if partes else 'sin cambios'}{errores_str}"

    return ImportOut(
        mensaje=mensaje, personas_creadas=result.p, relaciones_creadas=result.r,
        empresas_creadas=result.e, vinculos_creados=result.v, errores=result.err[:5],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA ÚNICO
# ═══════════════════════════════════════════════════════════════════════════════

_HANDLERS = {
    "ruc_batch": lambda db, datos, etiqueta_id: _importar_ruc_batch(db, datos.texto or "", etiqueta_id, datos.etiqueta or ""),
    "sunat_macro": lambda db, datos, etiqueta_id: _importar_sunat_macro(db, datos.texto or "", etiqueta_id, datos.etiqueta or ""),
    "leder_individual": lambda db, datos, etiqueta_id: _importar_leder_individual(db, datos.texto or "", etiqueta_id, datos.etiqueta or ""),
    "leder_telegram": lambda db, datos, etiqueta_id: _importar_leder_telegram(db, datos.texto or ""),
}


def ejecutar_importacion(db: Session, datos: ImportarRequest, usuario_id: int, usuario_username: str) -> ImportOut:
    """Punto de entrada único para cualquier formato de importación soportado."""
    formato = (datos.formato or "auto").strip().lower()
    if formato == "auto" or formato not in FORMATOS_IMPORTACION:
        formato = detectar_formato(datos)

    if formato == "csv":
        if not datos.personas:
            return ImportOut(mensaje="No hay datos para importar", formato_detectado="csv", errores=["sin personas"])
        resultado = _importar_csv(db, datos.personas)
    else:
        if not (datos.texto or "").strip():
            return ImportOut(mensaje="No hay datos para importar", formato_detectado=formato, errores=["texto vacio"])

        etiqueta_id = None
        if datos.etiqueta and datos.etiqueta.strip():
            etiqueta_id = crear_o_obtener_etiqueta(db, datos.etiqueta.strip()).id

        resultado = _HANDLERS[formato](db, datos, etiqueta_id)

    resultado.formato_detectado = formato
    registrar_auditoria(
        db, usuario_id, usuario_username, "CREATE", "Importar", formato,
        {"resumen": resultado.mensaje},
    )
    db.commit()
    return resultado
