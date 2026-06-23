"""
crud.py — Funciones de acceso a datos (Create, Read, Update, Delete).

Cada función recibe una sesión de SQLAlchemy (db) y los parámetros necesarios.
Todas las consultas usan parámetros enlazados para prevenir inyección SQL.
"""

from datetime import date, datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import Persona, Relacion, Etiqueta, PersonaEtiqueta, PersonaTrabajo, Auditoria
from schemas import (
    PersonaCreate, PersonaUpdate,
    RelacionCreate, PersonaEtiquetaAssign,
)


def registrar_auditoria(
    db: Session, usuario_id: Optional[int], usuario_username: Optional[str],
    accion: str, entidad: str, entidad_id: Optional[str] = None,
    detalle: Optional[dict] = None,
):
    """Registra un cambio en la tabla de auditoría."""
    audit = Auditoria(
        usuario_id=usuario_id,
        usuario_username=usuario_username,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=detalle,
    )
    db.add(audit)
    db.commit()



# ═══════════════════════════════════════════════════════════════════════════════
# PERSONAS
# ═══════════════════════════════════════════════════════════════════════════════

def crear_persona(db: Session, datos: PersonaCreate) -> Persona:
    """Crea una nueva persona. Lanza ValueError si el DNI ya existe."""
    existente = db.query(Persona).filter(Persona.dni == datos.dni).first()
    if existente:
        raise ValueError(f"Ya existe una persona con DNI {datos.dni}")

    persona = Persona(
        dni=datos.dni,
        nombres=datos.nombres,
        apellido_paterno=datos.apellido_paterno,
        apellido_materno=datos.apellido_materno,
        fecha_nacimiento=datos.fecha_nacimiento,
        foto_url=datos.foto_url,
        notas=datos.notas,
    )
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona


def obtener_persona_por_dni(db: Session, dni: str) -> Optional[Persona]:
    """Busca una persona por DNI exacto. Retorna None si no existe."""
    return (
        db.query(Persona)
        .filter(Persona.dni == dni, Persona.activo == True)
        .first()
    )


def buscar_personas(db: Session, query: str, limite: int = 20) -> List[Persona]:
    """
    Busca personas cuyo nombre, apellido o DNI contengan el texto.
    El parámetro 'query' se busca con ILIKE para búsqueda sin distinción
    de mayúsculas/minúsculas.
    """
    patron = f"%{query}%"
    return (
        db.query(Persona)
        .filter(
            Persona.activo == True,
            or_(
                Persona.dni.ilike(patron),
                Persona.nombres.ilike(patron),
                Persona.apellido_paterno.ilike(patron),
                Persona.apellido_materno.ilike(patron),
            ),
        )
        .limit(limite)
        .all()
    )


def actualizar_persona(db: Session, dni: str, datos: PersonaUpdate) -> Optional[Persona]:
    """Actualiza campos de una persona. Retorna None si no existe."""
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        return None

    # Solo actualiza los campos que vienen en la petición
    update_data = datos.model_dump(exclude_unset=True)
    for campo, valor in update_data.items():
        setattr(persona, campo, valor)

    db.commit()
    db.refresh(persona)
    return persona


def eliminar_persona(db: Session, dni: str) -> bool:
    """
    Baja lógica: marca activo=False. Las relaciones se mantienen.
    Retorna True si se eliminó, False si no existía.
    """
    persona = obtener_persona_por_dni(db, dni)
    if not persona:
        return False
    persona.activo = False
    db.commit()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# RELACIONES
# ═══════════════════════════════════════════════════════════════════════════════

def crear_relacion(db: Session, datos: RelacionCreate) -> Relacion:
    """
    Crea una relación dirigida entre dos personas.
    Valida que ambas personas existan y que no haya duplicados.
    """
    origen = obtener_persona_por_dni(db, datos.persona_origen_dni)
    destino = obtener_persona_por_dni(db, datos.persona_destino_dni)

    if not origen:
        raise ValueError(f"No existe persona con DNI {datos.persona_origen_dni}")
    if not destino:
        raise ValueError(f"No existe persona con DNI {datos.persona_destino_dni}")
    if origen.id == destino.id:
        raise ValueError("No se puede crear una relación de una persona consigo misma")

    # Verificar que no exista ya esta misma relación
    existente = (
        db.query(Relacion)
        .filter(
            Relacion.persona_origen_id == origen.id,
            Relacion.persona_destino_id == destino.id,
            Relacion.tipo_relacion == datos.tipo_relacion,
        )
        .first()
    )
    if existente:
        raise ValueError(
            f"Ya existe una relación '{datos.tipo_relacion}' entre "
            f"{origen.nombre_completo} y {destino.nombre_completo}"
        )

    relacion = Relacion(
        persona_origen_id=origen.id,
        persona_destino_id=destino.id,
        tipo_relacion=datos.tipo_relacion,
        certeza=datos.certeza,
        notas=datos.notas,
    )
    db.add(relacion)
    db.commit()
    db.refresh(relacion)
    return relacion


def obtener_relaciones_directas(db: Session, persona_id: int) -> List[dict]:
    """
    Devuelve todas las relaciones directas (como origen y como destino)
    de una persona, con el tipo ajustado según la dirección.

    Para relaciones donde la persona es destino de 'padre' o 'madre',
    se muestra como 'hijo'/'hija' según corresponda pero con tipo genérico 'hijo'.
    Para 'conyuge', 'hermano', 'hermana' se mantiene el tipo tal cual
    (son simétricas en la práctica).
    """
    resultados = []

    # Relaciones donde la persona es ORIGEN
    for rel in (
        db.query(Relacion)
        .filter(Relacion.persona_origen_id == persona_id)
        .all()
    ):
        # Invertir el tipo: si la persona es padre/madre del otro,
        # mostrar que el otro es hijo (perspectiva del familiar)
        tipo_invertido = rel.tipo_relacion
        if rel.tipo_relacion in ("padre", "madre"):
            tipo_invertido = "hijo"

        resultados.append({
            "relacion_id": rel.id,
            "tipo_relacion": tipo_invertido,
            "certeza": rel.certeza,
            "notas": rel.notas,
            "persona_relacionada_id": rel.persona_destino_id,
            "direccion": "origen",
        })

    # Relaciones donde la persona es DESTINO
    for rel in (
        db.query(Relacion)
        .filter(Relacion.persona_destino_id == persona_id)
        .all()
    ):
        # NO invertir: mostrar el tipo original (padre/madre/hermano)
        # porque describe la relación del familiar hacia la persona
        resultados.append({
            "relacion_id": rel.id,
            "tipo_relacion": rel.tipo_relacion,
            "certeza": rel.certeza,
            "notas": rel.notas,
            "persona_relacionada_id": rel.persona_origen_id,
            "direccion": "destino",
        })

    return resultados


def eliminar_relacion(db: Session, relacion_id: int) -> bool:
    """Elimina una relación por su ID. Retorna True si existía."""
    relacion = db.query(Relacion).filter(Relacion.id == relacion_id).first()
    if not relacion:
        return False
    db.delete(relacion)
    db.commit()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# ETIQUETAS
# ═══════════════════════════════════════════════════════════════════════════════

def crear_o_obtener_etiqueta(db: Session, nombre: str) -> Etiqueta:
    """Crea una etiqueta nueva o retorna la existente."""
    etiqueta = db.query(Etiqueta).filter(Etiqueta.nombre == nombre).first()
    if not etiqueta:
        etiqueta = Etiqueta(nombre=nombre)
        db.add(etiqueta)
        db.commit()
        db.refresh(etiqueta)
    return etiqueta


def listar_etiquetas(db: Session) -> List[Etiqueta]:
    """Lista todas las etiquetas disponibles."""
    return db.query(Etiqueta).order_by(Etiqueta.nombre).all()


def asignar_etiqueta(
    db: Session, persona_id: int, datos: PersonaEtiquetaAssign
) -> PersonaEtiqueta:
    """Asigna una etiqueta a una persona (crea la etiqueta si no existe)."""
    etiqueta = crear_o_obtener_etiqueta(db, datos.etiqueta_nombre)

    # Verificar que no esté ya asignada
    existente = (
        db.query(PersonaEtiqueta)
        .filter(
            PersonaEtiqueta.persona_id == persona_id,
            PersonaEtiqueta.etiqueta_id == etiqueta.id,
        )
        .first()
    )
    if existente:
        raise ValueError(
            f"La persona ya tiene la etiqueta '{datos.etiqueta_nombre}'"
        )

    asignacion = PersonaEtiqueta(
        persona_id=persona_id,
        etiqueta_id=etiqueta.id,
        observacion=datos.observacion,
    )
    db.add(asignacion)
    db.commit()
    db.refresh(asignacion)
    return asignacion


def desasignar_etiqueta(db: Session, persona_id: int, etiqueta_nombre: str) -> bool:
    """Quita una etiqueta de una persona. Retorna True si existía."""
    etiqueta = db.query(Etiqueta).filter(Etiqueta.nombre == etiqueta_nombre).first()
    if not etiqueta:
        return False

    asignacion = (
        db.query(PersonaEtiqueta)
        .filter(
            PersonaEtiqueta.persona_id == persona_id,
            PersonaEtiqueta.etiqueta_id == etiqueta.id,
        )
        .first()
    )
    if not asignacion:
        return False

    db.delete(asignacion)
    db.commit()
    return True


def personas_por_etiqueta(db: Session, etiqueta_nombre: str) -> List[Persona]:
    """Lista todas las personas que tienen una etiqueta determinada."""
    return (
        db.query(Persona)
        .join(PersonaEtiqueta)
        .join(Etiqueta)
        .filter(
            Etiqueta.nombre == etiqueta_nombre,
            Persona.activo == True,
        )
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TRABAJOS
# ═══════════════════════════════════════════════════════════════════════════════

def registrar_trabajo(db: Session, persona_id: int, empresa_nombre: str) -> PersonaTrabajo:
    """Registra un lugar de trabajo para una persona (evita duplicados)."""
    existente = db.query(PersonaTrabajo).filter(
        PersonaTrabajo.persona_id == persona_id,
        PersonaTrabajo.empresa_nombre == empresa_nombre,
    ).first()
    if existente:
        return existente
    t = PersonaTrabajo(persona_id=persona_id, empresa_nombre=empresa_nombre)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t
