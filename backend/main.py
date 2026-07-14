"""
main.py — Aplicación principal de Datero (FastAPI).

Punto de entrada del backend. Define todas las rutas REST y sirve
los archivos estáticos del frontend.
"""

import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status, Body, Request, BackgroundTasks, Form
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import re

from database import get_db
from models import Persona, Relacion, Usuario, Auditoria, Empresa, PersonaEmpresa, EmpresaEtiqueta
from auth import (
    get_current_user, requiere_rol, crear_token,
    verificar_password, seed_usuario_admin, hash_password,
)
from crud import (
    crear_persona, obtener_persona_por_dni, buscar_personas,
    actualizar_persona, eliminar_persona,
    obtener_relaciones_directas,
    crear_o_obtener_etiqueta, listar_etiquetas,
    asignar_etiqueta, desasignar_etiqueta, personas_por_etiqueta,
    registrar_auditoria,
    crear_empresa, obtener_empresa_por_ruc, buscar_empresas,
    listar_todas_empresas, actualizar_empresa, eliminar_empresa,
    vincular_persona_empresa, desvincular_persona_empresa,
    asignar_etiqueta_empresa, desasignar_etiqueta_empresa,
    empresas_por_etiqueta, personas_por_empresa, empresas_por_persona,
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
    ArbolOut, ArbolNodo,
    LoginRequest, TokenResponse, UsuarioOut,
    AuditoriaOut, AuditoriaLista, ImportarRequest, ImportOut,
    EmpresaCreate, EmpresaUpdate, EmpresaOut, EmpresaBrief,
    PersonaEmpresaCreate, PersonaEmpresaOut,
    PersonaEmpresaPersonaOut, PersonaEmpresaEmpresaOut,
    EmpresaEtiquetaAssign, EmpresaEtiquetaOut,
    FichaEmpresaOut, BusquedaEmpresaOut,
    TagStats, EmpresaStats, StatsOut,
    CompararRequest, CompararResponse,
)
from services.relacion_service import (
    crear_relacion_bidireccional,
    eliminar_relacion_bidireccional,
)
from services.persona_service import (
    crear_persona_con_etiqueta,
    eliminar_persona_con_auditoria,
    actualizar_persona_con_auditoria,
)
from services.import_service import ejecutar_importacion

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan simplificado: solo activa pg_trgm y crea admin.
    Las migraciones se gestionan manualmente via Neon SQL editor
    o ejecutando 'alembic upgrade head' localmente si se desea.
    """
    # 1. Extension pg_trgm para busqueda textual
    try:
        from sqlalchemy import text as sa_text
        from database import engine as _eng
        with _eng.connect() as c:
            c.execute(sa_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            c.commit()
    except Exception as e:
        print(f"[lifespan] pg_trgm: {e}")

    # 2. Usuario admin por defecto
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            seed_usuario_admin(db)
        finally:
            db.close()
    except Exception as e:
        print(f"[lifespan] seed_admin: {e}")

    yield


app = FastAPI(
    title="Datero API",
    description="API para la deteccion de redes de corrupcion mediante analisis de parentescos",
    version="0.3.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="../static"), name="static")


@app.get("/")
async def root():
    return FileResponse("../static/index.html")


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/login-form")
def api_login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Login via form POST (fallback sin JS). Redirige al home con query param."""
    usuario = db.query(Usuario).filter(
        Usuario.username == username, Usuario.activo == True
    ).first()
    if not usuario or not verificar_password(password, usuario.password_hash):
        return RedirectResponse(url="/?error=credenciales_invalidas", status_code=303)
    token = crear_token(usuario.username, usuario.id, usuario.rol)
    return RedirectResponse(
        url=f"/?token={token}&user={usuario.username}&rol={usuario.rol}",
        status_code=303,
    )


@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def api_login(request: Request, datos: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(
        Usuario.username == datos.username, Usuario.activo == True
    ).first()
    if not usuario or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos")
    token = crear_token(usuario.username, usuario.id, usuario.rol)
    return TokenResponse(access_token=token, username=usuario.username, rol=usuario.rol)


@app.get("/api/auth/me", response_model=UsuarioOut)
def api_auth_me(user: Usuario = Depends(get_current_user)):
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# PERSONAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/personas", response_model=PersonaOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def api_crear_persona(request: Request, datos: PersonaCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    try:
        persona = crear_persona_con_etiqueta(db, datos, user.id, user.username)
        return persona
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/api/personas", response_model=BusquedaPersonaOut)
@limiter.limit("30/minute")
def api_buscar_personas(request: Request, q: str = Query(..., min_length=1), limite: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    resultados = buscar_personas(db, q, limite)
    return BusquedaPersonaOut(resultados=[PersonaBrief.model_validate(p) for p in resultados], total=len(resultados))


@app.get("/api/personas/{dni}", response_model=FichaPersonaOut)
def api_obtener_persona(dni: str, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")

    relaciones_raw = obtener_relaciones_directas(db, persona.id)
    relaciones_out = []
    for r in relaciones_raw:
        persona_rel = db.query(Persona).filter(Persona.id == r["persona_relacionada_id"]).first()
        if persona_rel:
            relaciones_out.append(RelacionOut(
                id=r["relacion_id"], tipo_relacion=r["tipo_relacion"],
                certeza=r["certeza"], notas=r["notas"],
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

    # Empresas vinculadas (nuevo modelo PersonaEmpresa)
    empresas_out = []
    for pe in persona.empresas:
        if pe.empresa and pe.empresa.activo:
            empresas_out.append(PersonaEmpresaPersonaOut(
                id=pe.id,
                empresa=EmpresaBrief.model_validate(pe.empresa),
                cargo=pe.cargo,
                fecha_desde=pe.fecha_desde,
                fecha_hasta=pe.fecha_hasta,
                observacion=pe.observacion,
            ))

    return FichaPersonaOut(
        persona=PersonaOut.model_validate(persona),
        relaciones_directas=relaciones_out,
        parentescos_inferidos=parentescos_out,
        etiquetas=etiquetas_out,
        empresas=empresas_out,
    )


@app.put("/api/personas/{dni}", response_model=PersonaOut)
def api_actualizar_persona(dni: str, datos: PersonaUpdate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    persona = actualizar_persona_con_auditoria(db, dni, datos, user.id, user.username)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    return persona


@app.delete("/api/personas/{dni}", status_code=status.HTTP_204_NO_CONTENT)
def api_eliminar_persona(dni: str, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    eliminado = eliminar_persona_con_auditoria(db, dni, user.id, user.username)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Persona no encontrada")


# ═══════════════════════════════════════════════════════════════════════════════
# RELACIONES
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/relaciones", status_code=status.HTTP_201_CREATED)
def api_crear_relacion(datos: RelacionCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    try:
        resultado = crear_relacion_bidireccional(db, datos, user.id, user.username)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/api/relaciones/{dni}", response_model=List[RelacionOut])
def api_relaciones_por_dni(dni: str, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    relaciones_raw = obtener_relaciones_directas(db, persona.id)
    relaciones_out = []
    for r in relaciones_raw:
        persona_rel = db.query(Persona).filter(Persona.id == r["persona_relacionada_id"]).first()
        if persona_rel:
            relaciones_out.append(RelacionOut(id=r["relacion_id"], tipo_relacion=r["tipo_relacion"], certeza=r["certeza"], notas=r["notas"], persona_relacionada=PersonaBrief.model_validate(persona_rel)))
    return relaciones_out


@app.delete("/api/relaciones/{relacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_eliminar_relacion(relacion_id: int, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    if not eliminar_relacion_bidireccional(db, relacion_id, user.id, user.username):
        raise HTTPException(status_code=404, detail="Relacion no encontrada")


# ═══════════════════════════════════════════════════════════════════════════════
# PARENTESCO (INFERENCIA)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/parentesco", response_model=ParentescoLista)
def api_inferir_parentesco(dni: str = Query(...), tipo: str = Query(...), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    resultados = inferir_parentesco_especifico(db, persona, tipo)
    parentescos_out = [ParentescoOut(tipo_parentesco=r["tipo_parentesco"], persona=PersonaBrief.model_validate(r["persona"]), camino=r["camino"]) for r in resultados]
    return ParentescoLista(dni=dni, nombre_completo=persona.nombre_completo, parentescos=parentescos_out)


# ═══════════════════════════════════════════════════════════════════════════════
# ARBOL GENEALOGICO
# ═══════════════════════════════════════════════════════════════════════════════

def _construir_arbol_ascendente(db: Session, persona: Persona, profundidad: int) -> List:
    if profundidad <= 0: return []
    nodos = []
    padres = db.query(Persona).join(Relacion, Persona.id == Relacion.persona_origen_id).filter(Relacion.persona_destino_id == persona.id, Relacion.tipo_relacion.in_(["padre", "madre"]), Persona.activo == True).all()
    for p in padres:
        rel = db.query(Relacion).filter(Relacion.persona_origen_id == p.id, Relacion.persona_destino_id == persona.id).first()
        tipo = rel.tipo_relacion if rel else "padre"
        nodos.append(ArbolNodo(persona=PersonaBrief.model_validate(p), tipo_relacion=tipo, hijos=_construir_arbol_ascendente(db, p, profundidad - 1)))
    return nodos

def _construir_arbol_descendente(db: Session, persona: Persona, profundidad: int) -> List:
    if profundidad <= 0: return []
    nodos = []
    hijos = db.query(Persona).join(Relacion, Persona.id == Relacion.persona_destino_id).filter(Relacion.persona_origen_id == persona.id, Relacion.tipo_relacion.in_(["padre", "madre"]), Persona.activo == True).all()
    for h in hijos:
        rel = db.query(Relacion).filter(Relacion.persona_origen_id == persona.id, Relacion.persona_destino_id == h.id).first()
        tipo = "hija" if (h.genero and h.genero.upper() == "FEMENINO") else "hijo"
        nodos.append(ArbolNodo(persona=PersonaBrief.model_validate(h), tipo_relacion=tipo, hijos=_construir_arbol_descendente(db, h, profundidad - 1)))
    return nodos

@app.get("/api/personas/{dni}/arbol", response_model=ArbolOut)
def api_arbol_genealogico(dni: str, profundidad: int = Query(2, ge=1, le=4), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    persona = obtener_persona_por_dni(db, dni)
    if not persona: raise HTTPException(status_code=404, detail="Persona no encontrada")
    return ArbolOut(raiz=PersonaBrief.model_validate(persona), profundidad=profundidad, ascendentes=_construir_arbol_ascendente(db, persona, profundidad), descendentes=_construir_arbol_descendente(db, persona, profundidad))


# ═══════════════════════════════════════════════════════════════════════════════
# ETIQUETAS (compartidas)
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

@app.get("/api/etiquetas/{nombre}/empresas", response_model=List[EmpresaBrief])
def api_empresas_por_etiqueta(nombre: str, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    empresas = empresas_por_etiqueta(db, nombre)
    return [EmpresaBrief.model_validate(e) for e in empresas]

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

@app.put("/api/etiquetas/{etiqueta_id}", response_model=EtiquetaOut)
def api_editar_etiqueta(etiqueta_id: int, datos: EtiquetaCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    from models import Etiqueta as ET
    et = db.query(ET).filter(ET.id == etiqueta_id).first()
    if not et: raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    old_name = et.nombre
    et.nombre = datos.nombre
    db.commit()
    registrar_auditoria(db, user.id, user.username, "UPDATE", "Etiqueta", f"{old_name} -> {datos.nombre}")
    return et


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRESAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/empresas", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def api_crear_empresa(datos: EmpresaCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    try:
        empresa = crear_empresa(db, datos)
        registrar_auditoria(db, user.id, user.username, "CREATE", "Empresa", empresa.ruc, datos.model_dump())
        return empresa
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/api/empresas", response_model=BusquedaEmpresaOut)
def api_buscar_empresas(q: str = Query(..., min_length=1), limite: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    resultados = buscar_empresas(db, q, limite)
    return BusquedaEmpresaOut(resultados=[EmpresaBrief.model_validate(e) for e in resultados], total=len(resultados))


@app.get("/api/empresas/todas", response_model=List[EmpresaOut])
def api_todas_empresas(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    return listar_todas_empresas(db)


@app.post("/api/empresas/enriquecer-todas")
def api_enriquecer_todas_empresas(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Inicia el enriquecimiento de todas las empresas en background."""
    global _progreso_enriquecer
    if _progreso_enriquecer.get("activo"):
        raise HTTPException(status_code=409, detail="Ya hay un enriquecimiento en curso")

    _progreso_enriquecer = {
        "activo": True,
        "total": 0,
        "actualizadas": 0,
        "errores": [],
        "mensaje": "Iniciando...",
        "ruc_actual": "",
    }

    background_tasks.add_task(_ejecutar_enriquecimiento, user.id, user.username)
    return {"mensaje": "Enriquecimiento iniciado en background", "total_empresas": len(listar_todas_empresas(db))}


@app.get("/api/empresas/enriquecer-progreso")
def api_enriquecer_progreso(user: Usuario = Depends(get_current_user)):
    """Retorna el progreso del enriquecimiento en curso."""
    global _progreso_enriquecer
    p = _progreso_enriquecer
    porcentaje = round((p["actualizadas"] / p["total"] * 100)) if p["total"] > 0 else 0
    return {
        "activo": p.get("activo", False),
        "total": p.get("total", 0),
        "actualizadas": p.get("actualizadas", 0),
        "porcentaje": porcentaje,
        "mensaje": p.get("mensaje", ""),
        "ruc_actual": p.get("ruc_actual", ""),
        "errores": p.get("errores", [])[-5:],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PERSONA ↔ EMPRESA (vinculos)
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/empresas/{ruc}", response_model=FichaEmpresaOut)
def api_obtener_empresa(ruc: str, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    empresa = obtener_empresa_por_ruc(db, ruc)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    # Personas vinculadas
    personas_out = []
    for pe in empresa.personas_relacionadas:
        if pe.persona and pe.persona.activo:
            personas_out.append(PersonaEmpresaEmpresaOut(
                id=pe.id,
                persona=PersonaBrief.model_validate(pe.persona),
                cargo=pe.cargo,
                fecha_desde=pe.fecha_desde,
                fecha_hasta=pe.fecha_hasta,
                observacion=pe.observacion,
            ))

    etiquetas_out = [EmpresaEtiquetaOut.model_validate(ee) for ee in empresa.etiquetas_asignadas]

    return FichaEmpresaOut(
        empresa=EmpresaOut.model_validate(empresa),
        personas_vinculadas=personas_out,
        etiquetas=etiquetas_out,
    )


@app.put("/api/empresas/{ruc}", response_model=EmpresaOut)
def api_actualizar_empresa(ruc: str, datos: EmpresaUpdate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    empresa = actualizar_empresa(db, ruc, datos)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    registrar_auditoria(db, user.id, user.username, "UPDATE", "Empresa", ruc, datos.model_dump(exclude_unset=True))
    return empresa


@app.delete("/api/empresas/{ruc}", status_code=status.HTTP_204_NO_CONTENT)
def api_eliminar_empresa(ruc: str, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    eliminado = eliminar_empresa(db, ruc)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    registrar_auditoria(db, user.id, user.username, "DELETE", "Empresa", ruc)


# ═══════════════════════════════════════════════════════════════════════════════
# ENRIQUECER EMPRESA DESDE SUNAT
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/empresas/{ruc}/enriquecer", response_model=dict)
def api_enriquecer_empresa(ruc: str, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    """Enriquece una empresa consultando SUNAT y actualizando sus campos."""
    empresa = obtener_empresa_por_ruc(db, ruc)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    from consultas.sunat_scraper import SunatScraper, SunatScraperError, CaptchaDetectedError

    # Intentar scraper directo de SUNAT primero (gratuito).
    # Si falla, intentar apiperu.dev como respaldo (requiere CONSULTA_TOKEN).
    try:
        scraper = SunatScraper()
        data = scraper.consultar_ruc(ruc)
    except (CaptchaDetectedError, SunatScraperError) as e1:
        # Fallback: apiperu.dev
        from consultas.reniec_sunat import ConsultaPeru
        try:
            api = ConsultaPeru()
            data = api.consultar_ruc(ruc)
        except Exception as e2:
            raise HTTPException(
                status_code=422,
                detail=f"SUNAT: {e1}. apiperu: {e2}" if str(e2) != str(e1) else str(e1),
            )

    # Mapeo de campos SUNAT -> modelo
    if data.get("nombre_o_razon_social"):
        empresa.nombre = data["nombre_o_razon_social"]
    if data.get("direccion"):
        empresa.direccion = data["direccion"]
    empresa.estado = data.get("estado") or empresa.estado
    empresa.condicion = data.get("condicion") or empresa.condicion
    empresa.tipo_contribuyente = data.get("tipo_contribuyente") or empresa.tipo_contribuyente
    empresa.nombre_comercial = data.get("nombre_comercial") or empresa.nombre_comercial
    empresa.fecha_inscripcion = data.get("fecha_inscripcion") or empresa.fecha_inscripcion
    empresa.fecha_inicio_actividades = data.get("fecha_inicio_actividades") or empresa.fecha_inicio_actividades
    empresa.sistema_contabilidad = data.get("sistema_contabilidad") or empresa.sistema_contabilidad
    empresa.actividad_comercio_exterior = data.get("actividad_comercio_exterior") or empresa.actividad_comercio_exterior
    empresa.actividad_economica = data.get("actividad_economica") or empresa.actividad_economica
    empresa.comprobantes_autorizados = data.get("comprobantes_autorizados") or empresa.comprobantes_autorizados
    empresa.sistema_emision = data.get("sistema_emision") or empresa.sistema_emision
    empresa.afiliado_ple = data.get("afiliado_ple") or empresa.afiliado_ple
    empresa.sistema_emision_electronica = data.get("sistema_emision_electronica") or empresa.sistema_emision_electronica
    empresa.emisor_electronico_desde = data.get("emisor_electronico_desde") or empresa.emisor_electronico_desde
    empresa.comprobantes_electronicos = data.get("comprobantes_electronicos") or empresa.comprobantes_electronicos
    empresa.padrones = data.get("padrones") or empresa.padrones
    empresa.establecimientos = data.get("establecimientos") or empresa.establecimientos

    if data.get("representante_legal"):
        empresa.representante_legal_dni = data["representante_legal"].get("dni") or empresa.representante_legal_dni
        empresa.representante_legal_nombre = data["representante_legal"].get("nombre") or empresa.representante_legal_nombre

    db.commit()
    db.refresh(empresa)
    registrar_auditoria(db, user.id, user.username, "UPDATE", "Empresa", ruc, {"accion": "enriquecer_sunat"})

    return {"mensaje": f"Empresa {ruc} enriquecida desde SUNAT", "campos_actualizados": len([v for v in data.values() if v])}


# ── Progreso de enriquecimiento (en memoria) ─────────────────────────────
_progreso_enriquecer = {
    "activo": False,
    "total": 0,
    "actualizadas": 0,
    "errores": [],
    "mensaje": "",
    "ruc_actual": "",
}


def _ejecutar_enriquecimiento(user_id: int, user_username: str):
    """
    Ejecuta el enriquecimiento en background.

    Crea su propia sesion de BD porque la sesion del endpoint
    ya fue cerrada por FastAPI cuando BackgroundTasks ejecuta.
    """
    global _progreso_enriquecer
    from consultas.sunat_scraper import SunatScraper
    from database import SessionLocal
    db = SessionLocal()
    try:
        empresas = listar_todas_empresas(db)
        total = len(empresas)
        _progreso_enriquecer["total"] = total
        _progreso_enriquecer["actualizadas"] = 0
        _progreso_enriquecer["errores"] = []
        _progreso_enriquecer["mensaje"] = "Iniciando..."
        _progreso_enriquecer["ruc_actual"] = ""

        from consultas.reniec_sunat import ConsultaPeru
        for i, emp in enumerate(empresas):
            if not _progreso_enriquecer.get("activo", True):
                _progreso_enriquecer["mensaje"] = "Cancelado por el usuario"
                db.rollback()
                return

            _progreso_enriquecer["ruc_actual"] = emp.ruc
            try:
                # Intentar scraper directo SUNAT primero (gratuito)
                try:
                    scraper = SunatScraper()
                    data = scraper.consultar_ruc(emp.ruc)
                except Exception:
                    # Fallback: apiperu.dev
                    api = ConsultaPeru()
                    data = api.consultar_ruc(emp.ruc)
                if data.get("nombre_o_razon_social"):
                    emp.nombre = data["nombre_o_razon_social"]
                if data.get("direccion"):
                    emp.direccion = data["direccion"]
                for campo in ["estado", "condicion", "tipo_contribuyente", "nombre_comercial",
                              "fecha_inscripcion", "fecha_inicio_actividades", "sistema_contabilidad",
                              "actividad_comercio_exterior", "actividad_economica",
                              "comprobantes_autorizados", "sistema_emision", "afiliado_ple",
                              "sistema_emision_electronica", "emisor_electronico_desde",
                              "comprobantes_electronicos", "padrones", "establecimientos"]:
                    val = data.get(campo)
                    if val:
                        setattr(emp, campo, val)
                if data.get("representante_legal"):
                    emp.representante_legal_dni = data["representante_legal"].get("dni") or emp.representante_legal_dni
                    emp.representante_legal_nombre = data["representante_legal"].get("nombre") or emp.representante_legal_nombre
                db.flush()
                _progreso_enriquecer["actualizadas"] += 1
            except Exception as e:
                _progreso_enriquecer["errores"].append({"ruc": emp.ruc, "error": str(e)[:80]})

            _progreso_enriquecer["mensaje"] = f"Procesando {i+1}/{total}..."

        db.commit()
        _progreso_enriquecer["activo"] = False
        a = _progreso_enriquecer["actualizadas"]
        e = len(_progreso_enriquecer["errores"])
        _progreso_enriquecer["mensaje"] = f"Completado: {a}/{total} empresas enriquecidas ({e} errores)"
        registrar_auditoria(db, user_id, user_username, "UPDATE", "Empresa", "TODAS",
                           {"accion": "enriquecer_todas_sunat", "procesadas": a, "errores": e})
    except Exception as ex:
        try:
            db.rollback()
        except Exception:
            pass
        _progreso_enriquecer["activo"] = False
        _progreso_enriquecer["mensaje"] = f"Error general: {ex}"
    finally:
        try:
            db.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTADOR UNIFICADO
# ═══════════════════════════════════════════════════════════════════════════════
# Un solo endpoint para todos los formatos de importacion (CSV, batch RUC,
# macro SUNAT 21 columnas, reporte LEDER individual, export Telegram LEDER).
# La logica vive en services/import_service.py para evitar la duplicacion
# que existia entre _batch_import, api_importar_empresas_inteligente y
# api_db_importar.

@app.post("/api/importar", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
def api_importar(
    datos: ImportarRequest,
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Importa datos en cualquiera de los formatos soportados.

    Si no se especifica `formato` (o se envia "auto"), se autodetecta:
    - `personas` presente               -> csv
    - contiene "[#LEDER_BOT]"           -> leder_telegram
    - cabecera de la macro SUNAT        -> sunat_macro
    - bloque con DNI/NOMBRES/APELLIDOS  -> leder_individual
    - listado tabulado RUC + nombre     -> ruc_batch
    """
    try:
        return ejecutar_importacion(db, datos, user.id, user.username)
    except HTTPException:
        raise
    except Exception as e:
        import traceback, io
        buf = io.StringIO()
        traceback.print_exc(file=buf)
        detalle = buf.getvalue()[:2000]
        raise HTTPException(status_code=500, detail=f"Error en importacion: {str(e)}\n---\n{detalle}")


@app.post("/api/importar/debug")
def api_importar_debug(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Herramienta de diagnostico: muestra como se ve un export de Telegram
    LEDER tras el preprocesamiento, sin escribir nada en la base de datos."""
    raw = body.get("texto", "")
    from services.leder_parser import _strip_html, _detectar_tipo, _es_continuacion, _dni_limpio, _bloques_personas
    limpio = _strip_html(raw)
    limpio = limpio.replace("\r\n", "\n").replace("\r", "\n")
    partes = re.split(r"(?=\[#LEDER_BOT\])", limpio)
    info = []
    for i, p in enumerate(partes):
        p = p.strip()
        if len(p) < 10: continue
        info.append({
            "idx": i, "len": len(p), "tipo": _detectar_tipo(p),
            "continuacion": _es_continuacion(p), "dni": _dni_limpio(p),
            "bloques_personas": len(_bloques_personas(p)), "preview": p[:120],
        })
    from collections import Counter
    tipos_count = Counter(p["tipo"] for p in info)
    metas_perdidas = [p for p in info if "META" in (p.get("preview") or "") and "|" not in (p.get("preview") or "")[:60]]
    return {
        "total_partes": len(partes),
        "partes_procesables": len(info),
        "conteo_tipos": dict(tipos_count.most_common()),
        "metas_no_detectadas": len(metas_perdidas),
        "ejemplo_meta_perdida": metas_perdidas[0]["preview"][:200] if metas_perdidas else None,
        "primeros_300_chars": limpio[:300],
        "partes": info[:25],
    }


@app.post("/api/persona-empresa", status_code=status.HTTP_201_CREATED)
def api_vincular_persona_empresa(datos: PersonaEmpresaCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    try:
        vinculo = vincular_persona_empresa(db, datos)
        registrar_auditoria(db, user.id, user.username, "CREATE", "PersonaEmpresa", f"{datos.persona_dni}/{datos.empresa_ruc}", datos.model_dump())
        return {
            "mensaje": f"{vinculo.persona.nombre_completo} vinculado a {vinculo.empresa.nombre} como '{vinculo.cargo}'",
            "id": vinculo.id,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.delete("/api/persona-empresa/{vinculo_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_desvincular_persona_empresa(vinculo_id: int, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    if not desvincular_persona_empresa(db, vinculo_id):
        raise HTTPException(status_code=404, detail="Vinculo no encontrado")
    registrar_auditoria(db, user.id, user.username, "DELETE", "PersonaEmpresa", str(vinculo_id))


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRESA ETIQUETAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/empresas/{ruc}/etiquetas", status_code=status.HTTP_201_CREATED)
def api_asignar_etiqueta_empresa(ruc: str, datos: EmpresaEtiquetaAssign, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    empresa = obtener_empresa_por_ruc(db, ruc)
    if not empresa: raise HTTPException(status_code=404, detail="Empresa no encontrada")
    try:
        asignacion = asignar_etiqueta_empresa(db, empresa.id, datos)
        registrar_auditoria(db, user.id, user.username, "CREATE", "EmpresaEtiqueta", f"{ruc}/{datos.etiqueta_nombre}")
        return {"mensaje": f"Etiqueta '{datos.etiqueta_nombre}' asignada a {empresa.nombre}", "id": asignacion.id}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/api/empresas/{ruc}/etiquetas/{etiqueta_nombre}", status_code=status.HTTP_204_NO_CONTENT)
def api_desasignar_etiqueta_empresa(ruc: str, etiqueta_nombre: str, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    empresa = obtener_empresa_por_ruc(db, ruc)
    if not empresa: raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if not desasignar_etiqueta_empresa(db, empresa.id, etiqueta_nombre):
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada en esta empresa")
    registrar_auditoria(db, user.id, user.username, "DELETE", "EmpresaEtiqueta", f"{ruc}/{etiqueta_nombre}")


# ═══════════════════════════════════════════════════════════════════════════════
# VISOR DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/db/todas", response_model=List[PersonaOut])
def api_db_todas(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    from models import Persona as P
    return db.query(P).filter(P.activo == True).order_by(P.apellido_paterno, P.nombres).all()

@app.post("/api/db/reset")
def api_db_reset(confirmacion: dict = Body(...), db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    """Elimina TODOS los datos de la base de datos."""
    if confirmacion.get("confirmacion") != "RESET":
        raise HTTPException(status_code=400, detail="Debe enviar confirmacion: 'RESET'")
    from sqlalchemy import text
    tablas = [
        "empresa_etiqueta", "persona_etiqueta", "persona_empresa",
        "empresas", "relaciones", "etiquetas", "personas", "auditoria",
    ]
    for tabla in tablas:
        db.execute(text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
    db.commit()
    registrar_auditoria(db, user.id, user.username, "DELETE", "Reset", "TODOS", {"accion": "reset_total"})
    return {"mensaje": "Base de datos reiniciada exitosamente. Todas las tablas han sido limpiadas."}


# ═══════════════════════════════════════════════════════════════════════════════
# STATS (actualizado con empresas)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/stats", response_model=StatsOut)
def api_stats(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    from sqlalchemy import text
    total_personas = db.query(Persona).filter(Persona.activo == True).count()
    total_relaciones = db.query(Relacion).count()
    total_empresas = db.query(Empresa).filter(Empresa.activo == True).count()
    total_persona_empresa = db.query(PersonaEmpresa).count()

    # Personas por etiqueta
    tags_data = db.execute(text("""
        SELECT e.nombre, COUNT(pe.id) as cnt FROM etiquetas e
        JOIN persona_etiqueta pe ON pe.etiqueta_id = e.id
        GROUP BY e.nombre ORDER BY cnt DESC LIMIT 10
    """)).fetchall()
    personas_por_etiqueta = [TagStats(nombre=r[0], cantidad=r[1]) for r in tags_data]

    # Personas por empresa (nuevo: desde persona_empresa)
    empresa_data = db.execute(text("""
        SELECT e.nombre, COUNT(pe.id) as cnt FROM empresas e
        JOIN persona_empresa pe ON pe.empresa_id = e.id
        GROUP BY e.nombre ORDER BY cnt DESC LIMIT 10
    """)).fetchall()
    personas_por_empresa = [EmpresaStats(empresa=r[0], cantidad=r[1]) for r in empresa_data]

    # Empresas por etiqueta
    emp_tags_data = db.execute(text("""
        SELECT e.nombre, COUNT(ee.id) as cnt FROM etiquetas e
        JOIN empresa_etiqueta ee ON ee.etiqueta_id = e.id
        GROUP BY e.nombre ORDER BY cnt DESC LIMIT 10
    """)).fetchall()
    empresas_por_etiqueta = [TagStats(nombre=r[0], cantidad=r[1]) for r in emp_tags_data]

    return StatsOut(
        total_personas=total_personas,
        total_relaciones=total_relaciones,
        total_empresas=total_empresas,
        total_persona_empresa=total_persona_empresa,
        personas_por_etiqueta=personas_por_etiqueta,
        personas_por_empresa=personas_por_empresa,
        empresas_por_etiqueta=empresas_por_etiqueta,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AUDITORIA
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/auditoria", response_model=AuditoriaLista)
def api_auditoria(
    entidad: Optional[str] = Query(None),
    accion: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    desde: Optional[str] = Query(None),
    limite: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
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
# CONSULTA DNI (apiperu.dev)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/consultar/dni")
def api_consultar_dni(dni: str = Query(..., min_length=8, max_length=8), user: Usuario = Depends(get_current_user)):
    """Consulta datos de una persona por DNI usando apiperu.dev."""
    try:
        from consultas.reniec_sunat import ConsultaPeru
        api = ConsultaPeru()
        return api.consultar_dni(dni)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# CONSULTA RUC (SunatScraper)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/consultar/ruc")
def api_consultar_ruc(ruc: str = Query(..., min_length=11, max_length=11), user: Usuario = Depends(get_current_user)):
    """
    Consulta datos de una empresa por RUC.

    Estrategia:
    1. Intenta SunatScraper (scraping directo de SUNAT, gratuito).
    2. Si SUNAT devuelve CAPTCHA, fallback a apiperu.dev (requiere token).
    3. Si apiperu tampoco funciona, devuelve error controlado.
    """
    from consultas.sunat_scraper import SunatScraper, SunatScraperError, CaptchaDetectedError

    # ── Intento 1: SunatScraper ──
    try:
        scraper = SunatScraper()
        return scraper.consultar_ruc(ruc)
    except CaptchaDetectedError:
        # SUNAT pide CAPTCHA → fallback
        pass
    except SunatScraperError as e:
        # Error de scraping (timeout, no encontrado, etc.)
        # Intentar fallback antes de fallar
        pass

    # ── Intento 2: Fallback a apiperu.dev ──
    try:
        from consultas.reniec_sunat import ConsultaPeru
        api = ConsultaPeru()
        data = api.consultar_ruc(ruc)
        # Normalizar campos para mantener compatibilidad
        data["representante_legal"] = None
        return data
    except Exception as e2:
        raise HTTPException(
            status_code=502,
            detail=f"SUNAT bloqueo la consulta (CAPTCHA) y el servicio alternativo tampoco esta disponible: {e2}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/search")
def api_search(q: str = Query(..., min_length=2), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    """Busqueda predictiva: personas + empresas en un solo endpoint."""
    patron = f"%{q}%"
    personas = db.query(Persona).filter(
        Persona.activo == True,
        or_(
            Persona.nombres.ilike(patron),
            Persona.apellido_paterno.ilike(patron),
            Persona.apellido_materno.ilike(patron),
            Persona.dni.ilike(patron),
        )
    ).limit(10).all()

    empresas = db.query(Empresa).filter(
        Empresa.activo == True,
        or_(
            Empresa.nombre.ilike(patron),
            Empresa.ruc.ilike(patron),
        )
    ).limit(10).all()

    results = []
    for p in personas:
        results.append({
            "id": p.id, "nombres": p.nombres,
            "apellido_paterno": p.apellido_paterno or "",
            "dni": p.dni, "tipo": "persona"
        })
    for e in empresas:
        results.append({
            "id": e.id, "nombres": e.nombre,
            "apellido_paterno": "",
            "dni": e.ruc, "tipo": "empresa"
        })
    return results[:10]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPARAR PERSONAS (detección de cruces)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/comparar", response_model=CompararResponse)
def api_comparar(
    datos: CompararRequest,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Compara 2-5 personas y detecta cruces: mismos parientes,
    cadenas familiares, empresas compartidas, etiquetas compartidas."""
    from services.comparar_service import CompararService
    try:
        service = CompararService(db)
        return service.comparar(datos.dnis)
    except HTTPException:
        raise
    except Exception as e:
        import traceback, io
        buf = io.StringIO()
        traceback.print_exc(file=buf)
        detalle = buf.getvalue()[:500]
        raise HTTPException(
            status_code=500,
            detail=f"Error al comparar personas: {str(e)}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICADOR DE CONSISTENCIA
# ═══════════════════════════════════════════════════════════════════════════════

_LIMITE_VERIFICADOR = 500
_CATEGORIAS = {
    "representante_no_vinculado": {"label": "Representantes legales", "icon": "👔"},
    "ruc10_sin_vinculo":          {"label": "RUC 10 sin vínculo",     "icon": "🔟"},
    "persona_huerfana":           {"label": "Personas huérfanas",     "icon": "👤"},
    "empresa_sin_vinculos":       {"label": "Empresas sin vínculos",  "icon": "🏢"},
    "relacion_duplicada":         {"label": "Relaciones duplicadas",  "icon": "🔁"},
    "relacion_auto":              {"label": "Relaciones auto-ref.",   "icon": "🔄"},
    "relacion_invertida":         {"label": "Relaciones invertidas",  "icon": "🔃"},
    "relacion_suelta":            {"label": "Relaciones LEDER sueltas","icon": "🧩"},
}


def _ejecutar_verificacion(db: Session, categorias: Optional[list[str]] = None):
    """Ejecuta verificaciones de consistencia. Si `categorias` no es None,
    solo ejecuta las categorías indicadas."""
    from sqlalchemy import text as sa_text

    CAT = set(categorias or [])
    L = _LIMITE_VERIFICADOR

    def _activa(*nombres):
        return not CAT or any(n in CAT for n in nombres)

    observaciones = []
    total_personas = 0

    # ── 1. Representantes legales no vinculados ──
    if _activa("representante_no_vinculado"):
        rows = db.execute(sa_text(f"""
            SELECT e.ruc, e.nombre, e.representante_legal_dni, e.representante_legal_nombre
            FROM empresas e
            WHERE e.representante_legal_dni IS NOT NULL
              AND e.activo = true
              AND NOT EXISTS (
                SELECT 1 FROM persona_empresa pe
                JOIN personas p ON p.id = pe.persona_id
                WHERE pe.empresa_id = e.id
                  AND p.dni = e.representante_legal_dni
                  AND pe.cargo = 'representante legal'
              )
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "representante_no_vinculado",
                "gravedad": "media",
                "mensaje": f"Empresa '{r[1]}' (RUC {r[0]}) tiene representante legal DNI {r[2]} ({r[3] or '?'}) sin vincular como 'representante legal'",
                "ruc": r[0],
                "dni": r[2],
            })

    # ── 2. RUC 10 sin persona vinculada ──
    if _activa("ruc10_sin_vinculo"):
        rows = db.execute(sa_text(f"""
            SELECT e.ruc, e.nombre FROM empresas e
            WHERE e.ruc LIKE '10%' AND e.activo = true
              AND NOT EXISTS (
                SELECT 1 FROM persona_empresa pe
                JOIN personas p ON p.id = pe.persona_id
                WHERE pe.empresa_id = e.id AND pe.cargo = 'proveedor'
              )
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "ruc10_sin_vinculo",
                "gravedad": "baja",
                "mensaje": f"Empresa RUC 10 '{r[1]}' (RUC {r[0]}) no tiene persona vinculada como proveedor",
                "ruc": r[0],
            })

    # ── 3. Personas sin ningún vínculo (huérfanas) ──
    if _activa("persona_huerfana"):
        total_personas = db.execute(sa_text("""
            SELECT COUNT(*) FROM personas WHERE activo = true
        """)).scalar()
        rows = db.execute(sa_text(f"""
            SELECT p.dni, p.nombres, p.apellido_paterno FROM personas p
            WHERE p.activo = true
              AND NOT EXISTS (SELECT 1 FROM relaciones r WHERE r.persona_origen_id = p.id OR r.persona_destino_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM persona_empresa pe WHERE pe.persona_id = p.id)
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            nombre = f"{r[1]} {r[2]}".strip()
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "persona_huerfana",
                "gravedad": "info",
                "mensaje": f"Persona '{nombre}' (DNI {r[0]}) no tiene relaciones ni empresas vinculadas",
                "dni": r[0],
            })

    # ── 4. Empresas sin personas vinculadas ──
    if _activa("empresa_sin_vinculos"):
        rows = db.execute(sa_text(f"""
            SELECT e.ruc, e.nombre FROM empresas e
            WHERE e.activo = true
              AND NOT EXISTS (SELECT 1 FROM persona_empresa pe WHERE pe.empresa_id = e.id)
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "empresa_sin_vinculos",
                "gravedad": "info",
                "mensaje": f"Empresa '{r[1]}' (RUC {r[0]}) no tiene personas vinculadas",
                "ruc": r[0],
            })

    # ── 5. Relaciones duplicadas ──
    if _activa("relacion_duplicada"):
        rows = db.execute(sa_text(f"""
            SELECT r1.persona_origen_id, r1.persona_destino_id, r1.tipo_relacion, COUNT(*) as cnt
            FROM relaciones r1
            GROUP BY r1.persona_origen_id, r1.persona_destino_id, r1.tipo_relacion
            HAVING COUNT(*) > 1
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            po = db.query(Persona).filter(Persona.id == r[0]).first()
            pd = db.query(Persona).filter(Persona.id == r[1]).first()
            nom_po = f"{po.nombres} {po.apellido_paterno}" if po else f"ID {r[0]}"
            nom_pd = f"{pd.nombres} {pd.apellido_paterno}" if pd else f"ID {r[1]}"
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "relacion_duplicada",
                "gravedad": "alta",
                "mensaje": f"Relacion duplicada ({r[2]}) entre {nom_po} y {nom_pd} — {r[3]} veces",
                "dni_origen": po.dni if po else None,
                "dni_destino": pd.dni if pd else None,
                "origen_id": r[0],
                "destino_id": r[1],
                "tipo_relacion": r[2],
            })

    # ── 6. Relaciones auto-referenciales ──
    if _activa("relacion_auto"):
        rows = db.execute(sa_text(f"""
            SELECT r.id, r.persona_origen_id, r.tipo_relacion FROM relaciones r
            WHERE r.persona_origen_id = r.persona_destino_id
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            p = db.query(Persona).filter(Persona.id == r[1]).first()
            nom = f"{p.nombres} {p.apellido_paterno}" if p else f"ID {r[1]}"
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "relacion_auto",
                "gravedad": "alta",
                "mensaje": f"Relacion auto-referencial ({r[2]}): {nom} consigo mismo",
                "dni": p.dni if p else None,
                "relacion_id": r[0],
            })

    # ── 7. Relaciones PADRE/MADRE invertidas (bug LEDER antiguo) ──
    if _activa("relacion_invertida"):
        rows = db.execute(sa_text(f"""
            SELECT r.id, r.persona_origen_id, r.persona_destino_id, r.tipo_relacion, r.notas
            FROM relaciones r
            WHERE r.tipo_relacion IN ('padre', 'madre')
              AND (r.notas LIKE '%LEDER: PADRE%' OR r.notas LIKE '%LEDER: MADRE%')
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            origen = db.query(Persona).filter(Persona.id == r[1]).first()
            destino = db.query(Persona).filter(Persona.id == r[2]).first()
            nom_origen = f"{origen.nombres} {origen.apellido_paterno}" if origen else f"ID {r[1]}"
            nom_destino = f"{destino.nombres} {destino.apellido_paterno}" if destino else f"ID {r[2]}"
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "relacion_invertida",
                "gravedad": "alta",
                "mensaje": f"Relacion '{r[3]}' invertida: {nom_origen} figura como padre/madre de {nom_destino} pero según LEDER deberia ser al reves",
                "relacion_id": r[0],
                "origen_id": r[1],
                "destino_id": r[2],
                "tipo_relacion": r[3],
            })

    # ── 8. Relaciones LEDER sueltas (importadas con dni_ctx incorrecto) ──
    if _activa("relacion_suelta"):
        rows = db.execute(sa_text(f"""
            SELECT r.id, r.persona_origen_id, r.persona_destino_id, r.tipo_relacion, r.notas
            FROM relaciones r
            WHERE r.notas LIKE '%LEDER:%'
              AND r.tipo_relacion NOT IN ('padre', 'madre')
            LIMIT {L}
        """)).fetchall()
        for r in rows:
            origen = db.query(Persona).filter(Persona.id == r[1]).first()
            destino = db.query(Persona).filter(Persona.id == r[2]).first()
            nom_origen = f"{origen.nombres} {origen.apellido_paterno}" if origen else f"ID {r[1]}"
            nom_destino = f"{destino.nombres} {destino.apellido_paterno}" if destino else f"ID {r[2]}"
            label_nota = (r[4] or "")[:50]
            observaciones.append({
                "id": len(observaciones) + 1,
                "tipo": "relacion_suelta",
                "gravedad": "media",
                "mensaje": f"Relacion '{r[3]}' de LEDER ({label_nota}) entre {nom_origen} y {nom_destino} — posible vinculacion incorrecta",
                "relacion_id": r[0],
                "origen_id": r[1],
                "destino_id": r[2],
                "dni_origen": origen.dni if origen else None,
                "dni_destino": destino.dni if destino else None,
                "tipo_relacion": r[3],
            })

    return {
        "total_observaciones": len(observaciones),
        "total_personas": total_personas,
        "observaciones": observaciones,
    }


@app.get("/api/verificar")
def api_verificar(
    categoria: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Verifica la consistencia de la base de datos.
    - `categoria` (opcional): filtrar por tipo específico.
    """
    cats = [categoria] if categoria else None
    return _ejecutar_verificacion(db, cats)


@app.get("/api/verificar/representantes")
def api_verificar_representantes(
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Solo verifica representantes legales no vinculados."""
    return _ejecutar_verificacion(db, ["representante_no_vinculado"])


@app.get("/api/verificar/personas")
def api_verificar_personas(
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Solo verifica personas huérfanas (sin relaciones ni empresas)."""
    return _ejecutar_verificacion(db, ["persona_huerfana"])


@app.get("/api/verificar/empresas")
def api_verificar_empresas(
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Solo verifica empresas sin vínculos y RUC 10 sin persona."""
    return _ejecutar_verificacion(db, ["ruc10_sin_vinculo", "empresa_sin_vinculos"])


@app.get("/api/verificar/relaciones")
def api_verificar_relaciones(
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Solo verifica relaciones duplicadas y auto-referenciales."""
    return _ejecutar_verificacion(db, ["relacion_duplicada", "relacion_auto"])


@app.post("/api/verificar/corregir")
def api_verificar_corregir(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Corrige una observacion del verificador."""
    from sqlalchemy import text as sa_text

    tipo = body.get("tipo", "")
    ruc = body.get("ruc")
    dni = body.get("dni")
    relacion_id = body.get("relacion_id")
    origen_id = body.get("origen_id")
    destino_id = body.get("destino_id")
    tipo_relacion = body.get("tipo_relacion")
    resultado = {"corregido": False, "mensaje": ""}

    if tipo == "representante_no_vinculado" and ruc and dni:
        empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
        persona = db.query(Persona).filter(Persona.dni == dni).first()
        if empresa and persona:
            existe = db.query(PersonaEmpresa).filter(
                PersonaEmpresa.persona_id == persona.id,
                PersonaEmpresa.empresa_id == empresa.id,
                PersonaEmpresa.cargo == "representante legal",
            ).first()
            if not existe:
                db.add(PersonaEmpresa(
                    persona_id=persona.id, empresa_id=empresa.id,
                    cargo="representante legal",
                ))
                db.commit()
                resultado["corregido"] = True
                resultado["mensaje"] = f"{persona.nombre_completo} vinculado como representante legal de {empresa.nombre}"
            else:
                resultado["mensaje"] = "Ya esta vinculado"
        else:
            resultado["mensaje"] = "Empresa o persona no encontrada"

    elif tipo == "ruc10_sin_vinculo" and ruc:
        from services.import_service import _obtener_o_crear_empresa, _obtener_o_crear_persona_legacy, _separar_nombre_completo, _vincular_si_no_existe
        empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
        if empresa:
            dni10 = ruc[2:10]
            nombres, ap_paterno, ap_materno = _separar_nombre_completo(empresa.nombre)
            persona, creada = _obtener_o_crear_persona_legacy(db, dni10, nombres, ap_paterno, ap_materno)
            vinculo_creado = _vincular_si_no_existe(db, persona.id, empresa.id, "proveedor")
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = f"{'Creada y v' if creada else 'V'}inculada persona {persona.nombre_completo} como proveedor de {empresa.nombre}"
        else:
            resultado["mensaje"] = "Empresa no encontrada"

    elif tipo == "persona_huerfana" and dni:
        persona = db.query(Persona).filter(Persona.dni == dni).first()
        if persona:
            persona.activo = False
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = f"Persona {persona.nombre_completo} desactivada (baja logica)"
        else:
            resultado["mensaje"] = "Persona no encontrada"

    elif tipo == "empresa_sin_vinculos" and ruc:
        empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
        if empresa:
            empresa.activo = False
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = f"Empresa {empresa.nombre} desactivada (baja logica)"
        else:
            resultado["mensaje"] = "Empresa no encontrada"

    elif tipo == "relacion_duplicada" and origen_id and destino_id and tipo_relacion:
        relaciones = db.query(Relacion).filter(
            Relacion.persona_origen_id == origen_id,
            Relacion.persona_destino_id == destino_id,
            Relacion.tipo_relacion == tipo_relacion,
        ).order_by(Relacion.id).all()
        if len(relaciones) > 1:
            for r in relaciones[1:]:
                db.delete(r)
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = f"Eliminadas {len(relaciones) - 1} relacion(es) duplicada(s), conservada la primera"
        else:
            resultado["mensaje"] = "No hay duplicados"

    elif tipo == "relacion_auto" and relacion_id:
        rel = db.query(Relacion).filter(Relacion.id == relacion_id).first()
        if rel:
            db.delete(rel)
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = "Relacion auto-referencial eliminada"
        else:
            resultado["mensaje"] = "Relacion no encontrada"

    elif tipo == "relacion_invertida" and relacion_id and origen_id and destino_id and tipo_relacion:
        rel = db.query(Relacion).filter(Relacion.id == relacion_id).first()
        if rel and rel.tipo_relacion in ("padre", "madre"):
            db.delete(rel)
            # Crear la relacion correcta sin la nota LEDER (para evitar
            # que el verificador la vuelva a detectar como invertida)
            db.add(Relacion(
                persona_origen_id=destino_id,
                persona_destino_id=origen_id,
                tipo_relacion=tipo_relacion,
                certeza="documento",
                notas=None,
            ))
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = f"Relacion '{tipo_relacion}' invertida correctamente"
        else:
            resultado["mensaje"] = "Relacion no encontrada o tipo no valido"

    elif tipo == "relacion_suelta" and relacion_id:
        rel = db.query(Relacion).filter(Relacion.id == relacion_id).first()
        if rel:
            db.delete(rel)
            db.commit()
            resultado["corregido"] = True
            resultado["mensaje"] = "Relacion LEDER suelta eliminada"
        else:
            resultado["mensaje"] = "Relacion no encontrada"

    return resultado


@app.post("/api/verificar/corregir-lote")
def api_verificar_corregir_lote(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Corrige multiples observaciones en un solo request (batch de 200)."""
    from services.import_service import _obtener_o_crear_empresa, _obtener_o_crear_persona_legacy, _separar_nombre_completo, _vincular_si_no_existe

    items = body.get("observaciones", [])
    if not items:
        return {"corregidas": 0, "errores": [], "mensaje": "Sin observaciones"}

    items = items[:200]
    corregidas = 0
    errores = []

    for item in items:
        tipo = item.get("tipo", "")
        ruc = item.get("ruc")
        dni = item.get("dni")
        relacion_id = item.get("relacion_id")
        origen_id = item.get("origen_id")
        destino_id = item.get("destino_id")
        tipo_relacion = item.get("tipo_relacion")

        try:
            if tipo == "representante_no_vinculado" and ruc and dni:
                empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
                persona = db.query(Persona).filter(Persona.dni == dni).first()
                if empresa and persona:
                    existe = db.query(PersonaEmpresa).filter(
                        PersonaEmpresa.persona_id == persona.id,
                        PersonaEmpresa.empresa_id == empresa.id,
                        PersonaEmpresa.cargo == "representante legal",
                    ).first()
                    if not existe:
                        db.add(PersonaEmpresa(
                            persona_id=persona.id, empresa_id=empresa.id,
                            cargo="representante legal",
                        ))
                        corregidas += 1

            elif tipo == "ruc10_sin_vinculo" and ruc:
                empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
                if empresa:
                    dni10 = ruc[2:10]
                    nombres, ap_paterno, ap_materno = _separar_nombre_completo(empresa.nombre)
                    persona, _ = _obtener_o_crear_persona_legacy(db, dni10, nombres, ap_paterno, ap_materno)
                    _vincular_si_no_existe(db, persona.id, empresa.id, "proveedor")
                    corregidas += 1

            elif tipo == "persona_huerfana" and dni:
                persona = db.query(Persona).filter(Persona.dni == dni).first()
                if persona:
                    persona.activo = False
                    corregidas += 1

            elif tipo == "empresa_sin_vinculos" and ruc:
                empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
                if empresa:
                    empresa.activo = False
                    corregidas += 1

            elif tipo == "relacion_duplicada" and origen_id and destino_id and tipo_relacion:
                relaciones = db.query(Relacion).filter(
                    Relacion.persona_origen_id == origen_id,
                    Relacion.persona_destino_id == destino_id,
                    Relacion.tipo_relacion == tipo_relacion,
                ).order_by(Relacion.id).all()
                if len(relaciones) > 1:
                    for r in relaciones[1:]:
                        db.delete(r)
                        corregidas += 1

            elif tipo == "relacion_auto" and relacion_id:
                rel = db.query(Relacion).filter(Relacion.id == relacion_id).first()
                if rel:
                    db.delete(rel)
                    corregidas += 1

            elif tipo == "relacion_invertida" and relacion_id and origen_id and destino_id and tipo_relacion:
                rel = db.query(Relacion).filter(Relacion.id == relacion_id).first()
                if rel and rel.tipo_relacion in ("padre", "madre"):
                    db.delete(rel)
                    db.add(Relacion(
                        persona_origen_id=destino_id,
                        persona_destino_id=origen_id,
                        tipo_relacion=tipo_relacion,
                        certeza="documento",
                        notas=None,
                    ))
                    corregidas += 1

        except Exception as e:
            errores.append({"idx": len(errores), "tipo": tipo, "error": str(e)[:100]})

    db.commit()
    mensaje = f"{corregidas} correccion(es) aplicadas"
    if errores:
        mensaje += f", {len(errores)} error(es)"
    return {"corregidas": corregidas, "errores": errores, "mensaje": mensaje}


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
@app.head("/health")
@app.get("/api/health")
@app.head("/api/health")
def health_check():
    return {"status": "ok", "app": "Datero", "version": "0.3.0"}
