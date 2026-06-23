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
    """Datos requeridos para crear una nueva persona."""
    dni: str = Field(..., min_length=1, max_length=20, description="DNI único")
    nombres: str = Field(..., min_length=1, max_length=200)
    apellido_paterno: str = Field(..., min_length=1, max_length=100)
    apellido_materno: Optional[str] = Field(None, max_length=100)
    fecha_nacimiento: Optional[date] = None
    foto_url: Optional[str] = None
    notas: Optional[str] = None


class PersonaUpdate(BaseModel):
    """Campos editables de una persona (todos opcionales)."""
    nombres: Optional[str] = Field(None, min_length=1, max_length=200)
    apellido_paterno: Optional[str] = Field(None, min_length=1, max_length=100)
    apellido_materno: Optional[str] = Field(None, max_length=100)
    fecha_nacimiento: Optional[date] = None
    foto_url: Optional[str] = None
    notas: Optional[str] = None


class PersonaOut(BaseModel):
    """Datos que devuelve la API al consultar una persona."""
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
    """Versión resumida para listados y búsquedas."""
    id: int
    dni: str
    nombre_completo: str

    model_config = {"from_attributes": True}


# ─── Relación ─────────────────────────────────────────────────────────────────

class RelacionCreate(BaseModel):
    """Datos para crear una relación entre dos personas existentes."""
    persona_origen_dni: str = Field(..., description="DNI de la persona origen")
    persona_destino_dni: str = Field(..., description="DNI de la persona destino")
    tipo_relacion: str = Field(
        ..., pattern="^(padre|madre|conyuge|hermano|hermana)$",
        description="Tipo de relación dirigida"
    )
    certeza: str = Field(default="confirmado", pattern="^(confirmado|rumor|documento)$")
    notas: Optional[str] = None


class RelacionOut(BaseModel):
    """Relación vista desde la perspectiva de una persona."""
    id: int
    tipo_relacion: str
    certeza: str
    notas: Optional[str] = None
    persona_relacionada: PersonaBrief

    model_config = {"from_attributes": True}


# ─── Etiquetas ────────────────────────────────────────────────────────────────

class EtiquetaCreate(BaseModel):
    """Crear una nueva categoría/etiqueta."""
    nombre: str = Field(..., min_length=1, max_length=100)


class EtiquetaOut(BaseModel):
    id: int
    nombre: str

    model_config = {"from_attributes": True}


class PersonaEtiquetaAssign(BaseModel):
    """Asignar una etiqueta a una persona."""
    etiqueta_nombre: str = Field(..., description="Nombre de la etiqueta (se crea si no existe)")
    observacion: Optional[str] = None


class PersonaEtiquetaOut(BaseModel):
    """Etiqueta asignada con su observación."""
    id: int
    etiqueta: EtiquetaOut
    observacion: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Parentesco (inferencia) ──────────────────────────────────────────────────

class ParentescoOut(BaseModel):
    """Resultado de una consulta de parentesco inferido."""
    tipo_parentesco: str
    persona: PersonaBrief
    camino: str  # Ej: "Pedro Olano es padre de Juan Olano, y Juan es padre de Dubal"
    certeza: str = "inferido"


class ParentescoLista(BaseModel):
    """Lista de todos los parentescos inferidos para una persona."""
    dni: str
    nombre_completo: str
    parentescos: List[ParentescoOut]


# ─── Árbol genealógico ────────────────────────────────────────────────────────

class ArbolNodo(BaseModel):
    """Nodo del árbol genealógico (estructura recursiva)."""
    persona: PersonaBrief
    tipo_relacion: Optional[str] = None  # Cómo se relaciona con la raíz
    hijos: List["ArbolNodo"] = []


class ArbolOut(BaseModel):
    """Árbol genealógico centrado en una persona."""
    raiz: PersonaBrief
    profundidad: int
    ascendentes: List[ArbolNodo] = []   # Padres, abuelos...
    descendentes: List[ArbolNodo] = []  # Hijos, nietos...


# ─── Ficha completa ───────────────────────────────────────────────────────────

# ─── Trabajo ──────────────────────────────────────────────────────────────────

class TrabajoOut(BaseModel):
    """Lugar de trabajo de una persona."""
    id: int
    empresa_nombre: str

    model_config = {"from_attributes": True}


# ─── Smart Import ─────────────────────────────────────────────────────────────

class SmartImportOut(BaseModel):
    """Resultado de la importación inteligente."""
    mensaje: str
    persona_dni: Optional[str] = None
    familiares_creados: int = 0
    empresa_registrada: Optional[str] = None
    errores: List[str] = []


# ─── Ficha completa ───────────────────────────────────────────────────────────

class FichaPersonaOut(BaseModel):
    """Ficha completa de una persona: datos, relaciones, parentescos, etiquetas y trabajos."""
    persona: PersonaOut
    relaciones_directas: List[RelacionOut]
    parentescos_inferidos: List[ParentescoOut]
    etiquetas: List[PersonaEtiquetaOut]
    trabajos: List[TrabajoOut] = []


# ─── Búsqueda ─────────────────────────────────────────────────────────────────

class BusquedaPersonaOut(BaseModel):
    """Resultado de búsqueda textual."""
    resultados: List[PersonaBrief]
    total: int


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
