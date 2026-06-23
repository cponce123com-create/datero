"""
main.py — Aplicación principal de RedCorruptela (FastAPI).

Punto de entrada del backend. Define todas las rutas REST y sirve
los archivos estáticos del frontend.
"""

import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import re

from database import get_db, init_db
from models import Persona, Relacion, Usuario, Auditoria
from auth import (
    get_current_user, requiere_rol, crear_token,
    verificar_password, seed_usuario_admin, hash_password,
)
from crud import (
    crear_persona, obtener_persona_por_dni, buscar_personas,
    actualizar_persona, eliminar_persona,
    crear_relacion, obtener_relaciones_directas, eliminar_relacion,
    crear_o_obtener_etiqueta, listar_etiquetas,
    asignar_etiqueta, desasignar_etiqueta, personas_por_etiqueta,
    registrar_trabajo, registrar_auditoria,
)
from parentesco import (
    inferir_todos_parentescos,
    inferir_parentesco_especifico,
)
from schemas import (
    PersonaCreate, PersonaUpdate, PersonaOut, PersonaBrief,
    RelacionCreate, RelacionOut,
    EtiquetaCreate, EtiquetaOut,
    PersonaEtiquetaAssign, PersonaEtiquetaOut,
    ParentescoOut, ParentescoLista,
    FichaPersonaOut, BusquedaPersonaOut,
    ArbolOut, ArbolNodo, TrabajoOut,
    LoginRequest, TokenResponse, UsuarioOut,
    AuditoriaOut, AuditoriaLista, SmartImportOut,
)

# ─── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ─── Inicialización ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crea las tablas y seed de usuarios al iniciar."""
    init_db()
    db = next(get_db())
    try:
        seed_usuario_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="RedCorruptela API",
    description="API para la detección de redes de corrupción mediante análisis de parentescos",
    version="0.2.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory="../static"), name="static")


@app.get("/")
async def root():
    """Redirige al frontend principal."""
    return FileResponse("../static/index.html")


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def api_login(request: Request, datos: LoginRequest, db: Session = Depends(get_db)):
    """Inicio de sesión. Retorna JWT token."""
    usuario = db.query(Usuario).filter(
        Usuario.username == datos.username, Usuario.activo == True
    ).first()
    if not usuario or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    token = crear_token(usuario.username, usuario.id, usuario.rol)
    return TokenResponse(
        access_token=token,
        username=usuario.username,
        rol=usuario.rol,
    )


@app.get("/api/auth/me", response_model=UsuarioOut)
def api_auth_me(user: Usuario = Depends(get_current_user)):
    """Retorna datos del usuario autenticado."""
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS: PERSONAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/personas", response_model=PersonaOut, status_code=status.HTTP_201_CREATED)
def api_crear_persona(
    datos: PersonaCreate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    try:
        persona = crear_persona(db, datos)
        registrar_auditoria(db, user.id, user.username, "CREATE", "Persona", persona.dni, datos.model_dump())
        return persona
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/api/personas", response_model=BusquedaPersonaOut)
def api_buscar_personas(
    q: str = Query(..., min_length=1),
    limite: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    resultados = buscar_personas(db, q, limite)
    return BusquedaPersonaOut(
        resultados=[PersonaBrief.model_validate(p) for p in resultados],
        total=len(resultados),
    )


@app.get("/api/personas/{dni}", response_model=FichaPersonaOut)
def api_obtener_persona(
    dni: str,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")

    relaciones_raw = obtener_relaciones_directas(db, persona.id)
    relaciones_out = []
    for r in relaciones_raw:
        persona_rel = db.query(Persona).filter(Persona.id == r["persona_relacionada_id"]).first()
        if persona_rel:
            relaciones_out.append(RelacionOut(
                id=r["relacion_id"],
                tipo_relacion=r["tipo_relacion"],
                certeza=r["certeza"],
                notas=r["notas"],
                persona_relacionada=PersonaBrief.model_validate(persona_rel),
            ))

    inferencias = inferir_todos_parentescos(db, persona)
    parentescos_out = []
    for inf in inferencias:
        parentescos_out.append(ParentescoOut(
            tipo_parentesco=inf["tipo_parentesco"],
            persona=PersonaBrief.model_validate(inf["persona"]),
            camino=inf["camino"],
        ))

    etiquetas_out = [PersonaEtiquetaOut.model_validate(pe) for pe in persona.etiquetas_asignadas]
    trabajos_out = [TrabajoOut.model_validate(t) for t in persona.trabajos]

    return FichaPersonaOut(
        persona=PersonaOut.model_validate(persona),
        relaciones_directas=relaciones_out,
        parentescos_inferidos=parentescos_out,
        etiquetas=etiquetas_out,
        trabajos=trabajos_out,
    )


@app.put("/api/personas/{dni}", response_model=PersonaOut)
def api_actualizar_persona(
    dni: str,
    datos: PersonaUpdate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    persona = actualizar_persona(db, dni, datos)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    registrar_auditoria(db, user.id, user.username, "UPDATE", "Persona", dni, datos.model_dump(exclude_unset=True))
    return persona


@app.delete("/api/personas/{dni}", status_code=status.HTTP_204_NO_CONTENT)
def api_eliminar_persona(
    dni: str,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    eliminado = eliminar_persona(db, dni)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    registrar_auditoria(db, user.id, user.username, "DELETE", "Persona", dni)


# ═══════════════════════════════════════════════════════════════════════════════
# RELACIONES
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/relaciones", status_code=status.HTTP_201_CREATED)
def api_crear_relacion(
    datos: RelacionCreate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    try:
        relacion = crear_relacion(db, datos)
        registrar_auditoria(db, user.id, user.username, "CREATE", "Relacion", str(relacion.id), datos.model_dump())
        return {
            "mensaje": "Relación creada exitosamente",
            "id": relacion.id,
            "origen": relacion.origen.nombre_completo,
            "tipo": relacion.tipo_relacion,
            "destino": relacion.destino.nombre_completo,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/api/relaciones/{dni}", response_model=List[RelacionOut])
def api_relaciones_por_dni(
    dni: str,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    relaciones_raw = obtener_relaciones_directas(db, persona.id)
    relaciones_out = []
    for r in relaciones_raw:
        persona_rel = db.query(Persona).filter(Persona.id == r["persona_relacionada_id"]).first()
        if persona_rel:
            relaciones_out.append(RelacionOut(
                id=r["relacion_id"],
                tipo_relacion=r["tipo_relacion"],
                certeza=r["certeza"],
                notas=r["notas"],
                persona_relacionada=PersonaBrief.model_validate(persona_rel),
            ))
    return relaciones_out


@app.delete("/api/relaciones/{relacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_eliminar_relacion(
    relacion_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    if not eliminar_relacion(db, relacion_id):
        raise HTTPException(status_code=404, detail="Relación no encontrada")
    registrar_auditoria(db, user.id, user.username, "DELETE", "Relacion", str(relacion_id))


# ═══════════════════════════════════════════════════════════════════════════════
# PARENTESCO (INFERENCIA)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/parentesco", response_model=ParentescoLista)
def api_inferir_parentesco(
    dni: str = Query(...),
    tipo: str = Query(..., description="abuelo, tio, cunado, suegro, etc."),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    resultados = inferir_parentesco_especifico(db, persona, tipo)
    parentescos_out = [ParentescoOut(tipo_parentesco=r["tipo_parentesco"], persona=PersonaBrief.model_validate(r["persona"]), camino=r["camino"]) for r in resultados]
    return ParentescoLista(dni=dni, nombre_completo=persona.nombre_completo, parentescos=parentescos_out)


# ═══════════════════════════════════════════════════════════════════════════════
# ÁRBOL GENEALÓGICO
# ═══════════════════════════════════════════════════════════════════════════════

def _construir_arbol_ascendente(db: Session, persona: Persona, profundidad: int) -> List[ArbolNodo]:
    if profundidad <= 0: return []
    nodos = []
    padres = db.query(Persona).join(Relacion, Persona.id == Relacion.persona_origen_id).filter(Relacion.persona_destino_id == persona.id, Relacion.tipo_relacion.in_(["padre", "madre"]), Persona.activo == True).all()
    for p in padres:
        rel = db.query(Relacion).filter(Relacion.persona_origen_id == p.id, Relacion.persona_destino_id == persona.id).first()
        tipo = rel.tipo_relacion if rel else "padre"
        nodos.append(ArbolNodo(persona=PersonaBrief.model_validate(p), tipo_relacion=tipo, hijos=_construir_arbol_ascendente(db, p, profundidad - 1)))
    return nodos

def _construir_arbol_descendente(db: Session, persona: Persona, profundidad: int) -> List[ArbolNodo]:
    if profundidad <= 0: return []
    nodos = []
    hijos = db.query(Persona).join(Relacion, Persona.id == Relacion.persona_destino_id).filter(Relacion.persona_origen_id == persona.id, Relacion.tipo_relacion.in_(["padre", "madre"]), Persona.activo == True).all()
    for h in hijos:
        rel = db.query(Relacion).filter(Relacion.persona_origen_id == persona.id, Relacion.persona_destino_id == h.id).first()
        tipo = "hijo" if (rel and rel.tipo_relacion == "padre") else "hija" if rel else "hijo"
        nodos.append(ArbolNodo(persona=PersonaBrief.model_validate(h), tipo_relacion=tipo, hijos=_construir_arbol_descendente(db, h, profundidad - 1)))
    return nodos

@app.get("/api/personas/{dni}/arbol", response_model=ArbolOut)
def api_arbol_genealogico(dni: str, profundidad: int = Query(2, ge=1, le=4), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    persona = obtener_persona_por_dni(db, dni)
    if not persona: raise HTTPException(status_code=404, detail="Persona no encontrada")
    return ArbolOut(raiz=PersonaBrief.model_validate(persona), profundidad=profundidad, ascendentes=_construir_arbol_ascendente(db, persona, profundidad), descendentes=_construir_arbol_descendente(db, persona, profundidad))


# ═══════════════════════════════════════════════════════════════════════════════
# ETIQUETAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/etiquetas", response_model=EtiquetaOut, status_code=status.HTTP_201_CREATED)
def api_crear_etiqueta(datos: EtiquetaCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    try:
        etiqueta = crear_o_obtener_etiqueta(db, datos.nombre)
        registrar_auditoria(db, user.id, user.username, "CREATE", "Etiqueta", etiqueta.nombre)
        return etiqueta
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/api/etiquetas", response_model=List[EtiquetaOut])
def api_listar_etiquetas(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    return listar_etiquetas(db)

@app.get("/api/etiquetas/{nombre}/personas", response_model=List[PersonaBrief])
def api_personas_por_etiqueta(nombre: str, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    personas = personas_por_etiqueta(db, nombre)
    return [PersonaBrief.model_validate(p) for p in personas]

@app.post("/api/personas/{dni}/etiquetas", status_code=status.HTTP_201_CREATED)
def api_asignar_etiqueta(dni: str, datos: PersonaEtiquetaAssign, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    persona = obtener_persona_por_dni(db, dni)
    if not persona: raise HTTPException(status_code=404, detail="Persona no encontrada")
    try:
        asignacion = asignar_etiqueta(db, persona.id, datos)
        registrar_auditoria(db, user.id, user.username, "CREATE", "PersonaEtiqueta", f"{dni}/{datos.etiqueta_nombre}")
        return {"mensaje": f"Etiqueta '{datos.etiqueta_nombre}' asignada a {persona.nombre_completo}", "id": asignacion.id}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.delete("/api/personas/{dni}/etiquetas/{etiqueta_nombre}", status_code=status.HTTP_204_NO_CONTENT)
def api_desasignar_etiqueta(dni: str, etiqueta_nombre: str, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    persona = obtener_persona_por_dni(db, dni)
    if not persona: raise HTTPException(status_code=404, detail="Persona no encontrada")
    if not desasignar_etiqueta(db, persona.id, etiqueta_nombre):
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada en esta persona")
    registrar_auditoria(db, user.id, user.username, "DELETE", "PersonaEtiqueta", f"{dni}/{etiqueta_nombre}")


# ═══════════════════════════════════════════════════════════════════════════════
# VISOR DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/db/todas", response_model=List[PersonaOut])
def api_db_todas(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    from models import Persona as P
    return db.query(P).filter(P.activo == True).order_by(P.apellido_paterno, P.nombres).all()

@app.post("/api/db/importar", status_code=status.HTTP_201_CREATED)
def api_db_importar(personas: List[PersonaCreate], db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    creados = 0
    errores = []
    for datos in personas:
        try:
            from models import Persona as P
            existente = db.query(P).filter(P.dni == datos.dni).first()
            if existente:
                errores.append(f"DNI {datos.dni}: ya existe")
                continue
            persona = P(dni=datos.dni, nombres=datos.nombres, apellido_paterno=datos.apellido_paterno, apellido_materno=datos.apellido_materno, fecha_nacimiento=datos.fecha_nacimiento, foto_url=datos.foto_url, notas=datos.notas)
            db.add(persona)
            creados += 1
        except Exception as e:
            errores.append(f"DNI {datos.dni}: {str(e)}")
    db.commit()
    registrar_auditoria(db, user.id, user.username, "CREATE", "Importar", f"{creados} personas")
    return {"mensaje": f"Importación completada: {creados} creados, {len(errores)} errores", "creados": creados, "errores": errores}


# ═══════════════════════════════════════════════════════════════════════════════
# SMART IMPORTER - parses LEDER DATA format
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/db/importar-inteligente", status_code=status.HTTP_201_CREATED)
def api_importar_inteligente(
    texto: dict = Body(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """
    Importador inteligente. Soporta dos modos:

    MODO LEDER DATA (individual):
      {"texto": "DNI: 44124016\nNOMBRES: DUBAL DANTE\nAPELLIDOS: OLANO ROMERO\n..."}

    MODO BATCH RUC 10 (lista masiva):
      {"texto": "10011477432\tCORIAT CELIS ENRIQUE\n10027726459\tJARAMILLO CALLE RICARDO\n...",
       "etiqueta": "PROVEEDOR 2019-2022"}

    En modo batch, extrae DNI del RUC 10 (posiciones 2-9) y asigna
    automaticamente la etiqueta a todas las personas creadas.
    """
    from models import PersonaTrabajo, PersonaEtiqueta as PE, Etiqueta as ET
    try:
        return _batch_import(texto, db, user)
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

def _batch_import(texto, db, user):
    from models import PersonaTrabajo, PersonaEtiqueta as PE, Etiqueta as ET
    raw = texto.get("texto", "")
    etiqueta_nombre = texto.get("etiqueta", "").strip()

    # ── DETECTAR MODO ──────────────────────────────────────────────────────
    primera_linea = raw.strip().split("\n")[0] if raw.strip() else ""
    es_batch = "\t" in primera_linea or (len(primera_linea) >= 11 and primera_linea[2:10].isdigit())

        # ── MODO BATCH RUC 10 ─────────────────────────────────────────────────
    if es_batch:
        errores = []

        # Crear/obtener etiqueta
        etiqueta_id = None
        if etiqueta_nombre:
            e_existente = db.query(ET).filter(ET.nombre == etiqueta_nombre).first()
            if not e_existente:
                e_existente = ET(nombre=etiqueta_nombre)
                db.add(e_existente)
                db.flush()
            etiqueta_id = e_existente.id

        # ── PARSEAR TODAS LAS LÍNEAS ────────────────────────────────────────
        personas_por_dni = {}  # dni -> (nombres, ap_paterno, ap_materno)
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line: continue

            parts = line.split("\t")
            ruc = parts[0].strip() if len(parts) > 0 else ""
            nombre_completo = parts[1].strip() if len(parts) > 1 else ""
            if not nombre_completo:
                m = re.match(r"^(\d{11})\s+(.+)", line)
                if m: ruc = m.group(1); nombre_completo = m.group(2).strip()
            if not nombre_completo: continue

            dni = None
            if len(ruc) == 11 and ruc[2:10].isdigit(): dni = ruc[2:10]
            elif len(ruc) == 8 and ruc.isdigit(): dni = ruc
            if not dni: errores.append(f"RUC invalido: {nombre_completo}"); continue

            nombre_parts = nombre_completo.split()
            if len(nombre_parts) >= 3:
                ap_p = nombre_parts[0]; ap_m = nombre_parts[1]; nom = " ".join(nombre_parts[2:])
            elif len(nombre_parts) == 2:
                ap_p = nombre_parts[0]; ap_m = nombre_parts[1]; nom = ""
            else:
                ap_p = nombre_parts[0] if nombre_parts else ""; ap_m = None; nom = ""
            personas_por_dni[dni] = (nom, ap_p, ap_m)  # deduplicado por DNI

        if not personas_por_dni:
            return SmartImportOut(mensaje="No se encontraron datos validos", persona_dni=None, errores=errores)

        # ── CONSULTAR EXISTENTES EN UNA SOLA QUERY ──────────────────────────
        dnis_existentes = set(
            row[0] for row in db.query(Persona.dni).filter(Persona.dni.in_(list(personas_por_dni.keys()))).all()
        )
        dnis_existentes_etiqueta = set()
        if etiqueta_id and dnis_existentes:
            dnis_existentes_etiqueta = set(
                row[0] for row in db.query(Persona.dni).join(PE, PE.persona_id == Persona.id).filter(
                    Persona.dni.in_(list(dnis_existentes)), PE.etiqueta_id == etiqueta_id
                ).all()
            )

        # ── BULK INSERT (un solo lote) ──────────────────────────────────────
        objects_to_add = []
        persona_dni_id_map = {}  # dni -> id after flush
        creados = 0
        for dni, (nom, ap_p, ap_m) in personas_por_dni.items():
            if dni not in dnis_existentes:
                p = Persona(dni=dni, nombres=nom, apellido_paterno=ap_p, apellido_materno=ap_m)
                objects_to_add.append(p)
                creados += 1

        if objects_to_add:
            db.add_all(objects_to_add)
            db.flush()  # Solo 1 flush para todos
            for p in objects_to_add:
                persona_dni_id_map[p.dni] = p.id

        # ── BULK TAG ASSIGNMENT ────────────────────────────────────────────
        tag_objects = []
        tags_asignados = 0
        if etiqueta_id:
            for dni, (nom, ap_p, ap_m) in personas_por_dni.items():
                pid = persona_dni_id_map.get(dni)
                if not pid:
                    if dni in dnis_existentes and dni not in dnis_existentes_etiqueta:
                        pid_row = db.query(Persona.id).filter(Persona.dni == dni).first()
                        pid = pid_row[0] if pid_row else None
                if pid:
                    tag_objects.append(PE(persona_id=pid, etiqueta_id=etiqueta_id))
                    tags_asignados += 1

        if tag_objects:
            db.add_all(tag_objects)

        # ── ÚNICO COMMIT ────────────────────────────────────────────────────
        db.commit()
        registrar_auditoria(db, user.id, user.username, "CREATE", "ImportarBatch", f"{creados} creados" + (f" etiqueta={etiqueta_nombre}" if etiqueta_nombre else ""))

        return SmartImportOut(
            mensaje=f"Batch: {creados} creados, {tags_asignados} etiquetados" + (f" como '{etiqueta_nombre}'" if etiqueta_nombre else ""),
            persona_dni=None,
            errores=errores,
        )

    # ── MODO LEDER DATA (individual) ──────────────────────────────────────# ── MODO LEDER DATA (individual) ──────────────────────────────────────
    errores = []
    persona = None
    trabajo_reg = None
    familiares_creados = 0

    # Create tag if specified (for individual import)
    etiqueta_id = None
    if etiqueta_nombre:
        e_existente = db.query(ET).filter(ET.nombre == etiqueta_nombre).first()
        if not e_existente:
            e_existente = ET(nombre=etiqueta_nombre)
            db.add(e_existente)
            db.flush()
        etiqueta_id = e_existente.id

    # --- Extract DNI ---
    m = re.search(r'DNI\s*:\s*(\d+)', raw)
    dni = m.group(1).strip() if m else None
    if not dni:
        raise HTTPException(status_code=400, detail="No se encontro DNI en el texto")

    # --- Extract names ---
    m_nombres = re.search(r'NOMBRES\s*:\s*(.+)', raw)
    m_ape = re.search(r'APELLIDOS\s*:\s*(.+)', raw)
    m_fec = re.search(r'FECHA NACIMIENTO\s*:\s*(\d{2}/\d{2}/\d{4})', raw)

    nombres = m_nombres.group(1).strip() if m_nombres else ""
    apellidos = m_ape.group(1).strip() if m_ape else ""

    ape_parts = apellidos.split() if apellidos else []
    ap_paterno = ape_parts[0] if len(ape_parts) > 0 else ""
    ap_materno = ape_parts[1] if len(ape_parts) > 1 else None

    fecha_nac = None
    if m_fec:
        from datetime import datetime
        try: fecha_nac = datetime.strptime(m_fec.group(1), "%d/%m/%Y").date()
        except: pass

    # --- Create or update persona ---
    from models import Persona as P
    existente = db.query(P).filter(P.dni == dni).first()
    if existente: persona = existente
    else:
        persona = P(dni=dni, nombres=nombres, apellido_paterno=ap_paterno, apellido_materno=ap_materno, fecha_nacimiento=fecha_nac)
        db.add(persona)
        db.flush()
        # Assign tag if specified
        if etiqueta_id:
            db.add(PE(persona_id=persona.id, etiqueta_id=etiqueta_id))

    # --- Extract TRABAJOS section ---
    m_trabajo_rs = re.search(r'RAZON SOCIAL\s*:\s*(.+)', raw)
    if m_trabajo_rs:
        empresa = m_trabajo_rs.group(1).strip()
        if empresa and empresa != "No se encontro":
            t_existente = db.query(PersonaTrabajo).filter(PersonaTrabajo.persona_id == persona.id, PersonaTrabajo.empresa_nombre == empresa).first()
            if not t_existente:
                db.add(PersonaTrabajo(persona_id=persona.id, empresa_nombre=empresa))
                trabajo_reg = empresa

    # --- Extract FAMILIA section ---
    lines = raw.split('\n')
    current_block = {}
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped.startswith('DNI') and ':' in line_stripped:
            if current_block.get('dni') and current_block.get('tipo'): pass
            current_block = {'dni': line_stripped.split(':')[1].strip()}
        elif line_stripped.startswith('APELLIDOS'): current_block['apellidos'] = line_stripped.split(':')[1].strip()
        elif line_stripped.startswith('NOMBRES'): current_block['nombres'] = line_stripped.split(':')[1].strip()
        elif line_stripped.startswith('GENERO'): current_block['genero'] = line_stripped.split(':')[1].strip()
        elif line_stripped.startswith('TIPO') and ':' in line_stripped:
            current_block['tipo'] = line_stripped.split(':')[1].strip()
            if current_block.get('dni') and current_block.get('tipo'):
                try:
                    fdni = current_block['dni']; fnombres = current_block.get('nombres', ''); fapellidos = current_block.get('apellidos', ''); ftipo = current_block['tipo'].upper().strip()
                    if fdni == persona.dni: continue
                    fm = db.query(P).filter(P.dni == fdni).first()
                    if not fm:
                        ape_p = fapellidos.split() if fapellidos else ['']
                        fm = P(dni=fdni, nombres=fnombres, apellido_paterno=ape_p[0] if len(ape_p)>0 else '', apellido_materno=ape_p[1] if len(ape_p)>1 else None)
                        db.add(fm); db.flush()
                    origen_id = None; destino_id = None; rel_tipo = None
                    if ftipo == 'MADRE': origen_id = fm.id; destino_id = persona.id; rel_tipo = 'madre'
                    elif ftipo == 'PADRE': origen_id = fm.id; destino_id = persona.id; rel_tipo = 'padre'
                    elif ftipo in ('HIJA','HIJO'): origen_id = persona.id; destino_id = fm.id; rel_tipo = 'padre'
                    elif ftipo in ('HERMANA','HERMANO'): origen_id = persona.id; destino_id = fm.id; rel_tipo = 'hermano'
                    elif ftipo in ('HIJASTRA','HIJASTRO'): origen_id = persona.id; destino_id = fm.id; rel_tipo = 'padre'
                    elif ftipo in ('CONYUGE','ESPOSO','ESPOSA'): origen_id = persona.id; destino_id = fm.id; rel_tipo = 'conyuge'
                    elif ftipo == 'COMPARTEN HIJOS': origen_id = persona.id; destino_id = fm.id; rel_tipo = 'conyuge'
                    if origen_id and rel_tipo:
                        from models import Relacion as REL
                        r_existente = db.query(REL).filter(REL.persona_origen_id == origen_id, REL.persona_destino_id == destino_id, REL.tipo_relacion == rel_tipo).first()
                        if not r_existente:
                            db.add(REL(persona_origen_id=origen_id, persona_destino_id=destino_id, tipo_relacion=rel_tipo, certeza='documento'))
                            familiares_creados += 1
                except Exception as e:
                    errores.append(f"Error familiar DNI {current_block.get('dni','?')}: {str(e)}")

    db.commit()

    mensaje = f"Importado: {persona.nombre_completo}"
    if trabajo_reg: mensaje += f" - Trabaja en: {trabajo_reg}"
    if familiares_creados > 0: mensaje += f" - {familiares_creados} familiar(es)"
    if etiqueta_nombre: mensaje += f" - Etiquetado: {etiqueta_nombre}"
    if errores: mensaje += f" - {len(errores)} error(es)"

    return SmartImportOut(mensaje=mensaje, persona_dni=persona.dni, familiares_creados=familiares_creados, empresa_registrada=trabajo_reg, errores=errores)



# ═══════════════════════════════════════════════════════════════════════════════
# AUDITORÍA
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/auditoria", response_model=AuditoriaLista)
def api_auditoria(
    entidad: Optional[str] = Query(None, description="Filtrar por entidad: Persona, Relacion, Etiqueta"),
    accion: Optional[str] = Query(None, description="Filtrar por accion: CREATE, UPDATE, DELETE"),
    username: Optional[str] = Query(None, description="Filtrar por usuario"),
    desde: Optional[str] = Query(None, description="Desde fecha ISO"),
    limite: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Historial de cambios. Solo admin."""
    q = db.query(Auditoria)
    if entidad: q = q.filter(Auditoria.entidad == entidad)
    if accion: q = q.filter(Auditoria.accion == accion)
    if username: q = q.filter(Auditoria.usuario_username == username)
    if desde:
        try:
            from datetime import datetime as dt
            q = q.filter(Auditoria.timestamp >= dt.fromisoformat(desde))
        except: pass
    q = q.order_by(Auditoria.timestamp.desc()).limit(limite)
    resultados = q.all()
    return AuditoriaLista(resultados=[AuditoriaOut.model_validate(r) for r in resultados], total=len(resultados))


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "RedCorruptela", "version": "0.2.0"}
