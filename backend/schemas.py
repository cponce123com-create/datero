"""
schemas.py — Esquemas Pydantic para validación de datos en la API.

Define las estructuras de entrada/salida para cada endpoint.
Pydantic garantiza que los datos que llegan al backend tengan el formato correcto.
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ─── Persona ──────────────────────────────────────────────────────────────────

class PersonaCreate(BaseModel):
    dni: str = Field(..., min_length=1, max_length=20)
    nombres: str = Field(..., min_length=1, max_length=200)
    apellido_paterno: str = Field(..., min_length=1, max_length=100)
    apellido_materno: Optional[str] = Field(None, max_length=100)
    fecha_nacimiento: Optional[date] = None
    foto_url: Optional[str] = None
    notas: Optional[str] = None

class PersonaUpdate(BaseModel):
    nombres: Optional[str] = Field(None, min_length=1, max_length=200)
    apellido_paterno: Optional[str] = Field(None, min_length=1, max_length=100)
    apellido_materno: Optional[str] = Field(None, max_length=100)
    fecha_nacimiento: Optional[date] = None
    foto_url: Optional[str] = None
    notas: Optional[str] = None

class PersonaOut(BaseModel):
    id: int
    dni: str
    nombres: str
    apellido_paterno: str
    apellido_materno: Optional[str] = None
    nombre_completo: str
    fecha_nacimiento: Optional[date] = None
    foto_url: Optional[str] = None
    notas: Optional[str] = None
    activo: bool
    creado_en: Optional[datetime] = None
    model_config = {"from_attributes": True}

class PersonaBrief(BaseModel):
    id: int
    dni: str
    nombre_completo: str
    model_config = {"from_attributes": True}


# ─── Relación ─────────────────────────────────────────────────────────────────

class RelacionCreate(BaseModel):
    persona_origen_dni: str = Field(..., description="DNI de la persona origen")
    persona_destino_dni: str = Field(..., description="DNI de la persona destino")
    tipo_relacion: str = Field(..., pattern="^(padre|madre|conyuge|hermano|hermana)$")
    certeza: str = Field(default="confirmado", pattern="^(confirmado|rumor|documento)$")
    notas: Optional[str] = None

class RelacionOut(BaseModel):
    id: int
    tipo_relacion: str
    certeza: str
    notas: Optional[str] = None
    persona_relacionada: PersonaBrief
    model_config = {"from_attributes": True}


# ─── Etiquetas ────────────────────────────────────────────────────────────────

class EtiquetaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)

class EtiquetaOut(BaseModel):
    id: int
    nombre: str
    model_config = {"from_attributes": True}

class PersonaEtiquetaAssign(BaseModel):
    etiqueta_nombre: str = Field(..., description="Nombre de la etiqueta")
    observacion: Optional[str] = None

class PersonaEtiquetaOut(BaseModel):
    id: int
    etiqueta: EtiquetaOut
    observacion: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ─── Parentesco ───────────────────────────────────────────────────────────────

class ParentescoOut(BaseModel):
    tipo_parentesco: str
    persona: PersonaBrief
    camino: str
    certeza: str = "inferido"

class ParentescoLista(BaseModel):
    dni: str
    nombre_completo: str
    parentescos: List[ParentescoOut]


# ─── Árbol ────────────────────────────────────────────────────────────────────

class ArbolNodo(BaseModel):
    persona: PersonaBrief
    tipo_relacion: Optional[str] = None
    hijos: List["ArbolNodo"] = []

class ArbolOut(BaseModel):
    raiz: PersonaBrief
    profundidad: int
    ascendentes: List[ArbolNodo] = []
    descendentes: List[ArbolNodo] = []


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRESAS
# ═══════════════════════════════════════════════════════════════════════════════

class EmpresaCreate(BaseModel):
    ruc: str = Field(..., min_length=11, max_length=11)
    nombre: str = Field(..., min_length=1, max_length=300)
    direccion: Optional[str] = None
    estado: Optional[str] = None
    condicion: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    nombre_comercial: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    fecha_inicio_actividades: Optional[str] = None
    sistema_contabilidad: Optional[str] = None
    actividad_comercio_exterior: Optional[str] = None
    actividad_economica: Optional[str] = None
    comprobantes_autorizados: Optional[str] = None
    sistema_emision: Optional[str] = None
    afiliado_ple: Optional[str] = None
    sistema_emision_electronica: Optional[str] = None
    emisor_electronico_desde: Optional[str] = None
    comprobantes_electronicos: Optional[str] = None
    padrones: Optional[str] = None
    establecimientos: Optional[str] = None
    representante_legal_dni: Optional[str] = None
    representante_legal_nombre: Optional[str] = None
    notas: Optional[str] = None

class EmpresaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=300)
    direccion: Optional[str] = None
    estado: Optional[str] = None
    condicion: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    nombre_comercial: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    fecha_inicio_actividades: Optional[str] = None
    sistema_contabilidad: Optional[str] = None
    actividad_comercio_exterior: Optional[str] = None
    actividad_economica: Optional[str] = None
    comprobantes_autorizados: Optional[str] = None
    sistema_emision: Optional[str] = None
    afiliado_ple: Optional[str] = None
    sistema_emision_electronica: Optional[str] = None
    emisor_electronico_desde: Optional[str] = None
    comprobantes_electronicos: Optional[str] = None
    padrones: Optional[str] = None
    establecimientos: Optional[str] = None
    representante_legal_dni: Optional[str] = None
    representante_legal_nombre: Optional[str] = None
    notas: Optional[str] = None

class EmpresaOut(BaseModel):
    id: int
    ruc: str
    nombre: str
    direccion: Optional[str] = None
    estado: Optional[str] = None
    condicion: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    nombre_comercial: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    fecha_inicio_actividades: Optional[str] = None
    sistema_contabilidad: Optional[str] = None
    actividad_comercio_exterior: Optional[str] = None
    actividad_economica: Optional[str] = None
    comprobantes_autorizados: Optional[str] = None
    sistema_emision: Optional[str] = None
    afiliado_ple: Optional[str] = None
    sistema_emision_electronica: Optional[str] = None
    emisor_electronico_desde: Optional[str] = None
    comprobantes_electronicos: Optional[str] = None
    padrones: Optional[str] = None
    establecimientos: Optional[str] = None
    representante_legal_dni: Optional[str] = None
    representante_legal_nombre: Optional[str] = None
    notas: Optional[str] = None
    activo: bool
    creado_en: Optional[datetime] = None
    model_config = {"from_attributes": True}

class EmpresaBrief(BaseModel):
    id: int
    ruc: str
    nombre: str
    estado: Optional[str] = None
    model_config = {"from_attributes": True}


# ─── PersonaEmpresa ───────────────────────────────────────────────────────────

class PersonaEmpresaCreate(BaseModel):
    persona_dni: str
    empresa_ruc: str
    cargo: Optional[str] = "trabajador"
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    observacion: Optional[str] = None

class PersonaEmpresaOut(BaseModel):
    id: int
    persona: PersonaBrief
    empresa: EmpresaBrief
    cargo: Optional[str] = None
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    observacion: Optional[str] = None
    model_config = {"from_attributes": True}

class PersonaEmpresaPersonaOut(BaseModel):
    id: int
    empresa: EmpresaBrief
    cargo: Optional[str] = None
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    observacion: Optional[str] = None
    model_config = {"from_attributes": True}

class PersonaEmpresaEmpresaOut(BaseModel):
    id: int
    persona: PersonaBrief
    cargo: Optional[str] = None
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    observacion: Optional[str] = None
    model_config = {"from_attributes": True}


# ─── EmpresaEtiqueta ─────────────────────────────────────────────────────────

class EmpresaEtiquetaAssign(BaseModel):
    etiqueta_nombre: str
    observacion: Optional[str] = None

class EmpresaEtiquetaOut(BaseModel):
    id: int
    etiqueta: EtiquetaOut
    observacion: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ─── Fichas ───────────────────────────────────────────────────────────────────

class FichaEmpresaOut(BaseModel):
    empresa: EmpresaOut
    personas_vinculadas: List[PersonaEmpresaEmpresaOut] = []
    etiquetas: List[EmpresaEtiquetaOut] = []

class FichaPersonaOut(BaseModel):
    persona: PersonaOut
    relaciones_directas: List[RelacionOut]
    parentescos_inferidos: List[ParentescoOut]
    etiquetas: List[PersonaEtiquetaOut]
    empresas: List[PersonaEmpresaPersonaOut] = []


# ─── Búsqueda ─────────────────────────────────────────────────────────────────

class BusquedaPersonaOut(BaseModel):
    resultados: List[PersonaBrief]
    total: int

class BusquedaEmpresaOut(BaseModel):
    resultados: List[EmpresaBrief]
    total: int


# ─── Importador unificado ───────────────────────────────────────────────────
# Reemplaza a los antiguos SmartImportOut / EmpresaImportOut y a los endpoints
# /api/db/importar, /api/db/importar-inteligente, /api/empresas/importar-inteligente,
# /api/importar/leder-telegram. Ver services/import_service.py.

FORMATOS_IMPORTACION = (
    "auto", "csv", "ruc_batch", "sunat_macro", "leder_individual", "leder_telegram",
    "transparencia",
)

class ImportarRequest(BaseModel):
    texto: Optional[str] = None
    personas: Optional[List[PersonaCreate]] = None
    etiqueta: Optional[str] = None
    formato: Optional[str] = Field(
        "auto",
        description="auto | csv | ruc_batch | sunat_macro | leder_individual | leder_telegram | transparencia",
    )


class ImportOut(BaseModel):
    mensaje: str
    formato_detectado: Optional[str] = None
    persona_dni: Optional[str] = None
    total_procesadas: int = 0
    personas_creadas: int = 0
    empresas_creadas: int = 0
    empresas_actualizadas: int = 0
    vinculos_creados: int = 0
    representantes_vinculados: int = 0
    relaciones_creadas: int = 0
    etiquetados: int = 0
    empresa_registrada: Optional[str] = None
    errores: List[str] = []


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    rol: str

class UsuarioOut(BaseModel):
    id: int
    username: str
    rol: str
    activo: bool
    creado_en: Optional[datetime] = None
    model_config = {"from_attributes": True}

class AuditoriaOut(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    usuario_username: Optional[str] = None
    accion: str
    entidad: str
    entidad_id: Optional[str] = None
    detalle: Optional[dict] = None
    timestamp: Optional[datetime] = None
    model_config = {"from_attributes": True}

class AuditoriaLista(BaseModel):
    resultados: List[AuditoriaOut]
    total: int


# ─── Stats ────────────────────────────────────────────────────────────────────

class TagStats(BaseModel):
    nombre: str
    cantidad: int

class EmpresaStats(BaseModel):
    empresa: str
    cantidad: int

class StatsOut(BaseModel):
    total_personas: int
    total_relaciones: int
    total_empresas: int
    total_persona_empresa: int
    personas_por_etiqueta: List[TagStats] = []
    personas_por_empresa: List[EmpresaStats] = []
    empresas_por_etiqueta: List[TagStats] = []


# ─── Comparar Personas ─────────────────────────────────────────────────────────

class CompararRequest(BaseModel):
    dnis: List[str] = Field(..., min_length=2, max_length=5, description="DNIs de personas a comparar (2-5)")

class CruceMismoPariente(BaseModel):
    tipo: str = "mismo_pariente"
    descripcion: str
    pariente_dni: str
    pariente_nombre: str
    parentesco_con_a: str
    parentesco_con_b: str

class CruceCadena(BaseModel):
    tipo: str = "cadena_familiar"
    descripcion: str
    persona_a_dni: str
    persona_b_dni: str
    pasos: List[dict]

class CruceEmpresa(BaseModel):
    tipo: str = "misma_empresa"
    descripcion: str
    empresa_ruc: str
    empresa_nombre: str
    personas: List[str]

class CruceEtiqueta(BaseModel):
    tipo: str = "misma_etiqueta"
    descripcion: str
    etiqueta: str
    personas: List[str]

class CruceUbicacion(BaseModel):
    tipo: str = "misma_ubicacion"
    descripcion: str
    ubicacion: str

class PersonaConParentescos(BaseModel):
    dni: str
    nombre_completo: str
    parentescos: List[dict] = []
    empresas: List[dict] = []
    etiquetas: List[str] = []

class CompararResponse(BaseModel):
    personas: List[PersonaConParentescos]
    cruces: List[dict] = []
    estadisticas: dict = {}
