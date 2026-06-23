"""
persona_service.py — Lógica de negocio para personas.

Orquesta operaciones complejas: crear persona + etiquetas,
eliminar con auditoría, etc. Delega CRUD atómico a crud.py.
"""

from typing import Optional, List
from sqlalchemy.orm import Session

from models import Persona, PersonaEtiqueta, Etiqueta
from schemas import PersonaCreate, PersonaUpdate, PersonaEtiquetaAssign
from crud import (
    crear_persona as crud_crear_persona,
    obtener_persona_por_dni,
    buscar_personas,
    actualizar_persona as crud_actualizar_persona,
    eliminar_persona as crud_eliminar_persona,
    crear_o_obtener_etiqueta,
    asignar_etiqueta,
    desasignar_etiqueta,
    personas_por_etiqueta,
    registrar_auditoria,
)


def crear_persona_con_etiqueta(
    db: Session,
    datos: PersonaCreate,
    usuario_id: int,
    usuario_username: str,
    etiqueta_nombre: Optional[str] = None,
    etiqueta_obs: Optional[str] = None,
) -> Persona:
    """
    Crea una persona y opcionalmente le asigna una etiqueta
    en una sola transacción atómica.
    """
    try:
        persona = crud_crear_persona(db, datos)

        if etiqueta_nombre:
            assign_data = PersonaEtiquetaAssign(
                etiqueta_nombre=etiqueta_nombre,
                observacion=etiqueta_obs,
            )
            asignar_etiqueta(db, persona.id, assign_data)

        registrar_auditoria(
            db, usuario_id, usuario_username,
            "CREATE", "Persona", persona.dni, datos.model_dump(),
        )
        db.commit()
        db.refresh(persona)
        return persona
    except Exception:
        db.rollback()
        raise


def eliminar_persona_con_auditoria(
    db: Session,
    dni: str,
    usuario_id: int,
    usuario_username: str,
) -> bool:
    """Elimina (soft delete) una persona y registra auditoría."""
    eliminado = crud_eliminar_persona(db, dni)
    if eliminado:
        registrar_auditoria(
            db, usuario_id, usuario_username,
            "DELETE", "Persona", dni,
        )
        db.commit()
    return eliminado


def actualizar_persona_con_auditoria(
    db: Session,
    dni: str,
    datos: PersonaUpdate,
    usuario_id: int,
    usuario_username: str,
) -> Optional[Persona]:
    """Actualiza una persona y registra auditoría."""
    persona = crud_actualizar_persona(db, dni, datos)
    if persona:
        registrar_auditoria(
            db, usuario_id, usuario_username,
            "UPDATE", "Persona", dni, datos.model_dump(exclude_unset=True),
        )
        db.commit()
    return persona
