"""
main.py — Aplicación principal de RedCorruptela (FastAPI).

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
    AuditoriaOut, AuditoriaLista, SmartImportOut, EmpresaImportOut,
    EmpresaCreate, EmpresaUpdate, EmpresaOut, EmpresaBrief,
    PersonaEmpresaCreate, PersonaEmpresaOut,
    PersonaEmpresaPersonaOut, PersonaEmpresaEmpresaOut,
    EmpresaEtiquetaAssign, EmpresaEtiquetaOut,
    FichaEmpresaOut, BusquedaEmpresaOut,
    TagStats, EmpresaStats, StatsOut,
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
from services.leder_parser import procesar_texto_leder

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = next(get_db())
    try:
        seed_usuario_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="RedCorruptela API",
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
def api_crear_persona(datos: PersonaCreate, db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    try:
        persona = crear_persona_con_etiqueta(db, datos, user.id, user.username)
        return persona
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.get("/api/personas", response_model=BusquedaPersonaOut)
def api_buscar_personas(q: str = Query(..., min_length=1), limite: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
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
        tipo = "hijo" if (rel and rel.tipo_relacion == "padre") else "hija" if rel else "hijo"
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

    # SUNAT usa reCAPTCHA v3 que requests no puede resolver.
    # Intentamos apiperu.dev primero (requiere CONSULTA_TOKEN).
    # El scraper directo queda como respaldo por si SUNAT cambia.
    from consultas.reniec_sunat import ConsultaPeru
    try:
        api = ConsultaPeru()
        data = api.consultar_ruc(ruc)
        data["representante_legal"] = None
    except Exception:
        # Fallback: intentar scraper directo
        try:
            scraper = SunatScraper()
            data = scraper.consultar_ruc(ruc)
        except (CaptchaDetectedError, SunatScraperError) as e2:
            raise HTTPException(status_code=422, detail=str(e2))

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
                # Intentar apiperu.dev primero (funciona, requiere token)
                try:
                    api = ConsultaPeru()
                    data = api.consultar_ruc(emp.ruc)
                    data["representante_legal"] = None
                except Exception:
                    # Fallback: scraper directo SUNAT
                    scraper = SunatScraper()
                    data = scraper.consultar_ruc(emp.ruc)
                if data.get("nombre_o_razon_social"):
                    emp.nombre = data["nombre_o_razon_social"]
                if data.get("direccion"):
                    emp.direccion = data["direccion"]
                for campo in ["estado", "condicion", "tipo_contribuyente", "nombre_comercial",
                              "fecha_inscripcion", "fecha_inicio_actividades", "sistema_contabilidad",
                              "actividad_comercio_exterior", "actividad_economica",
                              "comprobantes_autorizados", "sistema_emision", "afiliado_ple"]:
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
# LEDER DATA TELEGRAM IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/importar/leder-telegram", status_code=status.HTTP_201_CREATED)
def api_importar_leder_telegram(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Importa datos desde exportacion Telegram de LEDER DATA BOT.

    El texto debe contener los mensajes del bot @LEDER_DATA_BOT con formato:
    - META [PREMIUM] → crea/actualiza persona
    - META | FAMILIA [1|2] [PREMIUM] → crea personas + relaciones familiares
    - META | EMPRESAS [PREMIUM] → crea empresas + vinculos persona→empresa
    - META | SUNAT [PREMIUM] → crea/actualiza empresa
    - META | SUELDOS/TELEFONOS/CORREOS/VEHICULOS → agrega notas a persona
    """
    raw = body.get("texto", "")
    if not raw.strip():
        raise HTTPException(status_code=400, detail="No hay datos para importar")

    result = procesar_texto_leder(db, raw)

    partes = []
    if result.p:
        partes.append(f"{result.p} persona(s)")
    if result.r:
        partes.append(f"{result.r} relacion(es)")
    if result.e:
        partes.append(f"{result.e} empresa(s)")
    if result.v:
        partes.append(f"{result.v} vinculo(s)")

    errores_str = f" ({len(result.err)} error(es))" if result.err else ""
    mensaje = f"Importacion completada: {', '.join(partes) if partes else 'sin cambios'}{errores_str}"

    return {
        "mensaje": mensaje,
        "personas": result.p,
        "relaciones": result.r,
        "empresas": result.e,
        "vinculos": result.v,
        "errores": result.err[:5] if result.err else [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRESA SMART IMPORT (SUNAT macro 21 columnas)
# ═══════════════════════════════════════════════════════════════════════════════

SUNAT_COLUMNAS = [
    "ruc_raw", "ruc_nombre", "tipo_contribuyente", "nombre_comercial",
    "fecha_inscripcion", "fecha_inicio_actividades", "estado", "condicion",
    "domicilio_fiscal", "sistema_emision", "actividad_comercio_exterior",
    "sistema_contabilidad", "actividad_economica", "comprobantes_autorizados",
    "sistema_emision_electronica", "emisor_electronico_desde",
    "comprobantes_electronicos", "afiliado_ple", "padrones",
    "representantes_legales", "establecimientos",
]


def _parsear_nombre_apellidos_ruc10(texto: str):
    """Parsea el campo 'Número de RUC:' de un RUC 10.
    Formato: 'RUC - APELLIDO1 APELLIDO2 NOMBRES...'
    Retorna (nombres, apellido_paterno, apellido_materno)
    """
    if " - " in texto:
        texto = texto.split(" - ", 1)[1].strip()
    partes = texto.split()
    if len(partes) >= 3:
        ap_p = partes[0]
        ap_m = partes[1]
        nom = " ".join(partes[2:])
        return nom, ap_p, ap_m
    elif len(partes) == 2:
        return "", partes[0], partes[1]
    elif len(partes) == 1:
        return "", partes[0], None
    return "", "", None


def _parsear_representante_legal(texto: str):
    """Parsea el campo 'Representates legales'.
    Formato: 'NOMBRE APELLIDOS - CARGO'
    o 'No se encontraron representantes legales'
    Retorna (nombre_completo, cargo) o None.
    """
    texto = texto.strip()
    if not texto or texto.lower().startswith("no se encontr"):
        return None, None
    if " - " in texto:
        nombre, cargo = texto.split(" - ", 1)
        return nombre.strip(), cargo.strip()
    # Sin separador, probablemente solo nombre
    return texto, "representante legal"


@app.post("/api/empresas/importar-inteligente", response_model=EmpresaImportOut, status_code=status.HTTP_201_CREATED)
def api_importar_empresas_inteligente(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(requiere_rol("admin")),
):
    """Importa datos de empresas desde el formato tabulado de la macro SUNAT (21 columnas).

    Soporta:
    - RUC 20/30: crea/actualiza Empresa con todos los campos SUNAT
    - RUC 10: crea Persona + Empresa RUC10 + vinculo automatico
    - Representante legal: parsea y vincula como 'representante legal'
    - Etiqueta opcional: asigna a todas las entidades creadas
    """
    raw = body.get("texto", "")
    etiqueta_nombre = body.get("etiqueta", "").strip()

    lineas = [l.strip() for l in raw.strip().split("\n") if l.strip()]
    if not lineas:
        raise HTTPException(status_code=400, detail="No hay datos para importar")

    # Detectar si tiene cabecera de columnas SUNAT
    tiene_header = "INGRESAR EL NUMERO DE RUC" in lineas[0].upper()
    inicio = 1 if tiene_header else 0

    result = EmpresaImportOut(mensaje="", total_procesadas=0)

    # Preparar etiqueta si se especifico
    etiqueta_id = None
    if etiqueta_nombre:
        e_existente = db.query(Etiqueta).filter(Etiqueta.nombre == etiqueta_nombre).first()
        if not e_existente:
            e_existente = Etiqueta(nombre=etiqueta_nombre)
            db.add(e_existente)
            db.flush()
        etiqueta_id = e_existente.id

    for i in range(inicio, len(lineas)):
        partes = lineas[i].split("\t")
        if len(partes) < 2:
            continue

        ruc = partes[0].strip()
        if len(ruc) != 11 or not ruc.isdigit():
            result.errores.append(f"Línea {i+1}: RUC inválido '{ruc}'")
            continue

        result.total_procesadas += 1
        tipo_ruc = ruc[0]

        try:
            if tipo_ruc == "1":
                # ── RUC 10: Persona Natural con Negocio ──
                dni = ruc[2:10]  # 8 dígitos
                # Extraer nombre del campo 'Número de RUC:'
                nombre_texto = partes[1].strip() if len(partes) > 1 else ""
                nom, ap_p, ap_m = _parsear_nombre_apellidos_ruc10(nombre_texto)

                # Buscar o crear persona
                persona = db.query(Persona).filter(Persona.dni == dni).first()
                if not persona:
                    persona = Persona(
                        dni=dni,
                        nombres=nom or "PENDIENTE",
                        apellido_paterno=ap_p or "PENDIENTE",
                        apellido_materno=ap_m,
                    )
                    db.add(persona)
                    db.flush()
                    result.personas_creadas += 1
                    if etiqueta_id:
                        db.add(PersonaEtiqueta(persona_id=persona.id, etiqueta_id=etiqueta_id))
                        result.etiquetados += 1

                # Buscar o crear empresa RUC 10
                empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
                if empresa:
                    result.empresas_actualizadas += 1
                else:
                    empresa = Empresa(ruc=ruc, nombre=persona.nombre_completo)
                    db.add(empresa)
                    db.flush()
                    result.empresas_creadas += 1
                    if etiqueta_id:
                        db.add(EmpresaEtiqueta(empresa_id=empresa.id, etiqueta_id=etiqueta_id))
                        result.etiquetados += 1

                # Vincular persona -> empresa si no existe ya
                vinculo_existente = db.query(PersonaEmpresa).filter(
                    PersonaEmpresa.persona_id == persona.id,
                    PersonaEmpresa.empresa_id == empresa.id,
                ).first()
                if not vinculo_existente:
                    db.add(PersonaEmpresa(
                        persona_id=persona.id,
                        empresa_id=empresa.id,
                        cargo="titular - persona natural con negocio",
                    ))
                    result.vinculos_creados += 1

                # Llenar datos SUNAT desde las columnas
                _aplicar_campos_sunat(empresa, partes)

            elif tipo_ruc in ("2", "3"):
                # ── RUC 20/30: Empresa Juridica ──
                # Extraer nombre del campo 'Número de RUC:'
                nombre_empresa = ""
                if len(partes) > 1:
                    txt = partes[1].strip()
                    if " - " in txt:
                        nombre_empresa = txt.split(" - ", 1)[1].strip()
                    else:
                        nombre_empresa = txt

                empresa = db.query(Empresa).filter(Empresa.ruc == ruc).first()
                if empresa:
                    result.empresas_actualizadas += 1
                else:
                    empresa = Empresa(ruc=ruc, nombre=nombre_empresa or f"EMPRESA {ruc}")
                    db.add(empresa)
                    db.flush()
                    result.empresas_creadas += 1
                    if etiqueta_id:
                        db.add(EmpresaEtiqueta(empresa_id=empresa.id, etiqueta_id=etiqueta_id))
                        result.etiquetados += 1

                _aplicar_campos_sunat(empresa, partes)

                # Procesar representante legal
                if len(partes) > 19:
                    rep_texto = partes[19].strip()
                    rep_nombre, rep_cargo = _parsear_representante_legal(rep_texto)
                    if rep_nombre:
                        empresa.representante_legal_nombre = rep_nombre
                        empresa.representante_legal_dni = ""

                        # Buscar persona por nombre (aproximado)
                        rep_persona = None
                        if rep_nombre:
                            rep_like = db.query(Persona).filter(
                                Persona.activo == True,
                                Persona.nombres.ilike(f"%{rep_nombre.split()[-1]}%")
                            ).first()
                            rep_persona = rep_like

                        if not rep_persona:
                            # Crear persona con datos pendientes
                            nombre_partes = rep_nombre.split()
                            if len(nombre_partes) >= 2:
                                rep_nom = " ".join(nombre_partes[:-2]) if len(nombre_partes) > 2 else nombre_partes[0]
                                rep_ap = nombre_partes[-2] if len(nombre_partes) >= 2 else ""
                                rep_am = nombre_partes[-1] if len(nombre_partes) >= 2 else None
                            else:
                                rep_nom = rep_nombre
                                rep_ap = "PENDIENTE"
                                rep_am = None

                            rep_persona = Persona(
                                dni=f"REP-{ruc}",
                                nombres=rep_nom or "PENDIENTE",
                                apellido_paterno=rep_ap or "PENDIENTE",
                                apellido_materno=rep_am,
                            )
                            db.add(rep_persona)
                            db.flush()
                            result.personas_creadas += 1
                            if etiqueta_id:
                                db.add(PersonaEtiqueta(persona_id=rep_persona.id, etiqueta_id=etiqueta_id))
                                result.etiquetados += 1

                        cargo_real = rep_cargo or "representante legal"
                        vinculo_rep = db.query(PersonaEmpresa).filter(
                            PersonaEmpresa.persona_id == rep_persona.id,
                            PersonaEmpresa.empresa_id == empresa.id,
                            PersonaEmpresa.cargo == cargo_real,
                        ).first()
                        if not vinculo_rep:
                            db.add(PersonaEmpresa(
                                persona_id=rep_persona.id,
                                empresa_id=empresa.id,
                                cargo=cargo_real,
                            ))
                            result.representantes_vinculados += 1
                            result.vinculos_creados += 1

            else:
                result.errores.append(f"RUC {ruc}: tipo no soportado ({tipo_ruc})")

        except Exception as e:
            import traceback
            traceback.print_exc()
            result.errores.append(f"RUC {ruc}: {str(e)[:100]}")

    db.commit()

    partes_msg = []
    if result.empresas_creadas > 0:
        partes_msg.append(f"{result.empresas_creadas} empresa(s) creada(s)")
    if result.empresas_actualizadas > 0:
        partes_msg.append(f"{result.empresas_actualizadas} actualizada(s)")
    if result.personas_creadas > 0:
        partes_msg.append(f"{result.personas_creadas} persona(s) creada(s)")
    if result.vinculos_creados > 0:
        partes_msg.append(f"{result.vinculos_creados} vinculo(s)")
    if result.representantes_vinculados > 0:
        partes_msg.append(f"{result.representantes_vinculados} rep. legal(es)")
    if result.etiquetados > 0:
        partes_msg.append(f"{result.etiquetados} etiquetado(s)")

    if not partes_msg:
        partes_msg.append("Todo ya existia en BD")

    errores_str = f" ({len(result.errores)} error(es))" if result.errores else ""
    result.mensaje = f"Importacion completada: {', '.join(partes_msg)}{errores_str}"

    return result


def _aplicar_campos_sunat(empresa, partes):
    """Aplica los campos SUNAT desde las columnas tabuladas al modelo Empresa.

    Mapeo por indice:
    0=ruc, 1=nombre, 2=tipo_contribuyente, 3=nombre_comercial,
    4=fecha_inscripcion, 5=fecha_inicio, 6=estado, 7=condicion,
    8=direccion, 9=sistema_emision, 10=act_comercio_ext,
    11=sistema_contabilidad, 12=actividad_economica,
    13=comprobantes_autorizados, 14=sistema_emision_electronica,
    15=emisor_electronico_desde, 16=comprobantes_electronicos,
    17=afiliado_ple, 18=padrones, 19=representantes, 20=establecimientos
    """
    def v(idx):
        return partes[idx].strip() if len(partes) > idx and partes[idx].strip() else None

    if v(2): empresa.tipo_contribuyente = v(2)
    if v(3): empresa.nombre_comercial = v(3)
    if v(4): empresa.fecha_inscripcion = v(4)
    if v(5): empresa.fecha_inicio_actividades = v(5)
    if v(6): empresa.estado = v(6)
    if v(7): empresa.condicion = v(7)
    if v(8): empresa.direccion = v(8)
    if v(9): empresa.sistema_emision = v(9)
    if v(10): empresa.actividad_comercio_exterior = v(10)
    if v(11): empresa.sistema_contabilidad = v(11)
    if v(12): empresa.actividad_economica = v(12)
    if v(13): empresa.comprobantes_autorizados = v(13)
    if v(14): empresa.sistema_emision_electronica = v(14)
    if v(15): empresa.emisor_electronico_desde = v(15)
    if v(16): empresa.comprobantes_electronicos = v(16)
    if v(17): empresa.afiliado_ple = v(17)
    if v(18): empresa.padrones = v(18)
    if v(20): empresa.establecimientos = v(20)


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
    return {"mensaje": f"Importacion completada: {creados} creados, {len(errores)} errores", "creados": creados, "errores": errores}


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
# SMART IMPORTER
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/db/importar-inteligente", status_code=status.HTTP_201_CREATED)
def api_importar_inteligente(texto: dict = Body(...), db: Session = Depends(get_db), user: Usuario = Depends(requiere_rol("admin"))):
    from models import PersonaEtiqueta as PE, Etiqueta as ET
    try:
        return _batch_import(texto, db, user)
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

def _batch_import(texto, db, user):
    from models import PersonaEtiqueta as PE, Etiqueta as ET, PersonaEmpresa as PEM, Empresa as EMP
    raw = texto.get("texto", "")
    etiqueta_nombre = texto.get("etiqueta", "").strip()

    primera_linea = raw.strip().split("\n")[0] if raw.strip() else ""
    es_batch = "	" in primera_linea or (len(primera_linea) >= 11 and primera_linea[2:10].isdigit())

    if es_batch:
        errores = []
        etiqueta_id = None
        if etiqueta_nombre:
            e_existente = db.query(ET).filter(ET.nombre == etiqueta_nombre).first()
            if not e_existente:
                e_existente = ET(nombre=etiqueta_nombre)
                db.add(e_existente)
                db.flush()
            etiqueta_id = e_existente.id

        # Clasificar por tipo de RUC
        personas_data = {}
        empresas_data = {}
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            ruc = parts[0].strip() if len(parts) > 0 else ""
            nombre_completo = parts[1].strip() if len(parts) > 1 else ""
            if not nombre_completo:
                m = re.match(r"^(\d{11})\s+(.+)", line)
                if m:
                    ruc = m.group(1)
                    nombre_completo = m.group(2).strip()
            if not nombre_completo:
                continue
            if len(ruc) != 11 or not ruc.isdigit():
                errores.append(f"RUC invalido ({ruc}): {nombre_completo}")
                continue

            pd = ruc[0]
            if pd == "1":
                dni = ruc[2:10]
                if not dni.isdigit():
                    errores.append(f"DNI invalido en RUC {ruc}: {nombre_completo}")
                    continue
                nombre_parts = nombre_completo.split()
                if len(nombre_parts) >= 3:
                    ap_p = nombre_parts[0]; ap_m = nombre_parts[1]; nom = " ".join(nombre_parts[2:])
                elif len(nombre_parts) == 2:
                    ap_p = nombre_parts[0]; ap_m = nombre_parts[1]; nom = ""
                else:
                    ap_p = nombre_parts[0] if nombre_parts else ""; ap_m = None; nom = ""
                personas_data[dni] = (nom, ap_p, ap_m)
            elif pd in ("2", "3"):
                empresas_data[ruc] = nombre_completo
            else:
                errores.append(f"Tipo RUC no reconocido ({pd}): {nombre_completo}")

        tp = len(personas_data)
        te = len(empresas_data)
        if tp == 0 and te == 0:
            return SmartImportOut(mensaje="No se encontraron datos validos", persona_dni=None, errores=errores)

        # PERSONAS (RUC 10)
        pc = 0; pet = 0
        if personas_data:
            dnis_exist = set(row[0] for row in db.query(Persona.dni).filter(Persona.dni.in_(list(personas_data.keys()))).all())
            dnis_exist_tag = set()
            if etiqueta_id and dnis_exist:
                dnis_exist_tag = set(row[0] for row in db.query(Persona.dni).join(PE, PE.persona_id == Persona.id).filter(Persona.dni.in_(list(dnis_exist)), PE.etiqueta_id == etiqueta_id).all())
            objs = []; dni_id_map = {}
            for dni, (nom, ap_p, ap_m) in personas_data.items():
                if dni not in dnis_exist:
                    objs.append(Persona(dni=dni, nombres=nom, apellido_paterno=ap_p, apellido_materno=ap_m))
                    pc += 1
            if objs:
                db.add_all(objs); db.flush()
                for p in objs: dni_id_map[p.dni] = p.id
            tag_objs = []
            if etiqueta_id:
                for dni, _ in personas_data.items():
                    pid = dni_id_map.get(dni)
                    if not pid and dni in dnis_exist and dni not in dnis_exist_tag:
                        pid_row = db.query(Persona.id).filter(Persona.dni == dni).first()
                        pid = pid_row[0] if pid_row else None
                    if pid:
                        tag_objs.append(PE(persona_id=pid, etiqueta_id=etiqueta_id))
                        pet += 1
                if tag_objs: db.add_all(tag_objs)

        # EMPRESAS (RUC 20/30)
        ec = 0; eet = 0
        if empresas_data:
            rucs_exist = set(row[0] for row in db.query(EMP.ruc).filter(EMP.ruc.in_(list(empresas_data.keys()))).all())
            rucs_exist_tag = set()
            if etiqueta_id and rucs_exist:
                rucs_exist_tag = set(row[0] for row in db.query(EMP.ruc).join(EmpresaEtiqueta, EmpresaEtiqueta.empresa_id == EMP.id).filter(EMP.ruc.in_(list(rucs_exist)), EmpresaEtiqueta.etiqueta_id == etiqueta_id).all())
            e_objs = []; ruc_id_map = {}
            for ruc, nombre in empresas_data.items():
                if ruc not in rucs_exist:
                    e_objs.append(EMP(ruc=ruc, nombre=nombre))
                    ec += 1
            if e_objs:
                db.add_all(e_objs); db.flush()
                for e in e_objs: ruc_id_map[e.ruc] = e.id
            etag_objs = []
            if etiqueta_id:
                for ruc, _ in empresas_data.items():
                    eid = ruc_id_map.get(ruc)
                    if not eid and ruc in rucs_exist and ruc not in rucs_exist_tag:
                        eid_row = db.query(EMP.id).filter(EMP.ruc == ruc).first()
                        eid = eid_row[0] if eid_row else None
                    if eid:
                        etag_objs.append(EmpresaEtiqueta(empresa_id=eid, etiqueta_id=etiqueta_id))
                        eet += 1
                if etag_objs: db.add_all(etag_objs)

        db.commit()
        tet = pet + eet
        partes = []
        if pc > 0: partes.append(f"{pc} persona(s) creada(s)")
        if ec > 0: partes.append(f"{ec} empresa(s) creada(s)")
        if tet > 0: partes.append(f"{tet} etiquetado(s) como '{etiqueta_nombre}'")
        if not partes: partes.append("Todo ya existia")
        return SmartImportOut(
            mensaje=f"Batch: {', '.join(partes)}",
            persona_dni=None,
            personas_creadas=pc,
            empresas_creadas=ec,
            etiquetados=tet,
            errores=errores,
        )
    # ── MODO LEDER DATA (individual) ──
    errores = []
    persona = None
    trabajo_reg = None
    familiares_creados = 0

    etiqueta_id = None
    if etiqueta_nombre:
        e_existente = db.query(ET).filter(ET.nombre == etiqueta_nombre).first()
        if not e_existente:
            e_existente = ET(nombre=etiqueta_nombre)
            db.add(e_existente)
            db.flush()
        etiqueta_id = e_existente.id

    m = re.search(r'DNI\s*:\s*(\d+)', raw)
    dni = m.group(1).strip() if m else None
    if not dni:
        raise HTTPException(status_code=400, detail="No se encontro DNI en el texto")

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

    from models import Persona as P
    existente = db.query(P).filter(P.dni == dni).first()
    if existente: persona = existente
    else:
        persona = P(dni=dni, nombres=nombres, apellido_paterno=ap_paterno, apellido_materno=ap_materno, fecha_nacimiento=fecha_nac)
        db.add(persona)
        db.flush()
        if etiqueta_id:
            db.add(PE(persona_id=persona.id, etiqueta_id=etiqueta_id))

    m_trabajo_rs = re.search(r'RAZON SOCIAL\s*:\s*(.+)', raw)
    if m_trabajo_rs:
        empresa_nombre = m_trabajo_rs.group(1).strip()
        if empresa_nombre and empresa_nombre != "No se encontro":
            emp_existente = db.query(EMP).filter(EMP.nombre == empresa_nombre, EMP.activo == True).first()
            if not emp_existente:
                emp_existente = EMP(ruc=f"AUTO-{persona.dni}", nombre=empresa_nombre)
                db.add(emp_existente)
                db.flush()
            vinculo_existente = db.query(PEM).filter(PEM.persona_id == persona.id, PEM.empresa_id == emp_existente.id, PEM.cargo == "trabajador").first()
            if not vinculo_existente:
                db.add(PEM(persona_id=persona.id, empresa_id=emp_existente.id, cargo="trabajador"))
                trabajo_reg = empresa_nombre

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
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "RedCorruptela", "version": "0.3.0"}
