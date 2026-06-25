"""
relacion_service.py — Lógica de negocio para relaciones.

Implementa relaciones bidireccionales: al crear una relación,
se crea automáticamente su inversa en la misma transacción.
Al eliminar, se elimina también la inversa.

Al crear o eliminar relaciones, invalida automáticamente el
caché de parentescos para reflejar los cambios en la próxima consulta.
"""

from typing import Optional, List
from sqlalchemy.orm import Session

from models import Persona, Relacion
from schemas import RelacionCreate
from crud import (
    obtener_persona_por_dni,
    registrar_auditoria,
)
from parentesco import invalidar_cache_parentesco

# Mapeo de tipos de relación a sus inversos
INVERSO = {
    "padre": "hijo",
    "madre": "hija",
    "hijo": "padre",
    "hija": "madre",
    "hermano": "hermano",
    "hermana": "hermana",
    "conyuge": "conyuge",
}


def _crear_relacion_unica(
    db: Session,
    origen_id: int,
    destino_id: int,
    tipo: str,
    certeza: str,
    notas: Optional[str],
) -> Relacion:
    """Crea una relación si no existe duplicado."""
    existente = (
        db.query(Relacion)
        .filter(
            Relacion.persona_origen_id == origen_id,
            Relacion.persona_destino_id == destino_id,
            Relacion.tipo_relacion == tipo,
        )
        .first()
    )
    if existente:
        return existente  # Ya existe, no duplicar

    rel = Relacion(
        persona_origen_id=origen_id,
        persona_destino_id=destino_id,
        tipo_relacion=tipo,
        certeza=certeza,
        notas=notas,
    )
    db.add(rel)
    db.flush()
    return rel


def crear_relacion_bidireccional(
    db: Session,
    datos: RelacionCreate,
    usuario_id: int,
    usuario_username: str,
) -> dict:
    """
    Crea una relación y su inversa en una sola transacción.

    Ejemplo: usuario crea "Juan es PADRE de Pedro"
    → Crea: Juan → padre → Pedro
    → Crea: Pedro → hijo → Juan

    Retorna dict con mensaje y IDs.
    """
    origen = obtener_persona_por_dni(db, datos.persona_origen_dni)
    destino = obtener_persona_por_dni(db, datos.persona_destino_dni)

    if not origen:
        raise ValueError(f"No existe persona con DNI {datos.persona_origen_dni}")
    if not destino:
        raise ValueError(f"No existe persona con DNI {datos.persona_destino_dni}")
    if origen.id == destino.id:
        raise ValueError("No se puede crear una relación de una persona consigo misma")

    tipo_directo = datos.tipo_relacion
    tipo_inverso = INVERSO.get(tipo_directo)

    if not tipo_inverso:
        raise ValueError(f"Tipo de relación no soportado: {tipo_directo}")

    # Detectar ciclos antes de insertar (para relaciones padre/madre)
    if tipo_directo in ("padre", "madre"):
        from utils.graph_utils import detectar_ciclo_por_dni
        if detectar_ciclo_por_dni(db, datos.persona_origen_dni, datos.persona_destino_dni):
            raise ValueError(
                f"No se puede crear la relación: {origen.nombre_completo} ya es "
                f"descendiente de {destino.nombre_completo} (crearía un ciclo)"
            )

    try:
        # Crear relación directa
        rel_directa = _crear_relacion_unica(
            db, origen.id, destino.id, tipo_directo,
            datos.certeza, datos.notas,
        )

        # Crear relación inversa (misma certeza y notas)
        rel_inversa = _crear_relacion_unica(
            db, destino.id, origen.id, tipo_inverso,
            datos.certeza, datos.notas,
        )

        registrar_auditoria(
            db, usuario_id, usuario_username,
            "CREATE", "Relacion", str(rel_directa.id),
            {"tipo": tipo_directo, "origen": origen.nombre_completo, "destino": destino.nombre_completo},
        )

        db.commit()
        invalidar_cache_parentesco()

        return {
            "mensaje": f"Relación '{tipo_directo}' creada: {origen.nombre_completo} → {destino.nombre_completo}",
            "id": rel_directa.id,
            "inversa_id": rel_inversa.id if rel_inversa.id != rel_directa.id else None,
            "origen": origen.nombre_completo,
            "tipo": tipo_directo,
            "destino": destino.nombre_completo,
        }
    except Exception:
        db.rollback()
        raise


def eliminar_relacion_bidireccional(
    db: Session,
    relacion_id: int,
    usuario_id: int,
    usuario_username: str,
) -> bool:
    """
    Elimina una relación y su inversa (si existe) en una sola transacción.
    """
    relacion = db.query(Relacion).filter(Relacion.id == relacion_id).first()
    if not relacion:
        return False

    try:
        tipo_inverso = INVERSO.get(relacion.tipo_relacion)
        origen_id = relacion.persona_origen_id
        destino_id = relacion.persona_destino_id

        # Eliminar relación directa
        db.delete(relacion)

        # Eliminar relación inversa si existe
        if tipo_inverso:
            inversa = (
                db.query(Relacion)
                .filter(
                    Relacion.persona_origen_id == destino_id,
                    Relacion.persona_destino_id == origen_id,
                    Relacion.tipo_relacion == tipo_inverso,
                )
                .first()
            )
            if inversa:
                db.delete(inversa)

        registrar_auditoria(
            db, usuario_id, usuario_username,
            "DELETE", "Relacion", str(relacion_id),
        )
        db.commit()
        invalidar_cache_parentesco()
        return True
    except Exception:
        db.rollback()
        raise
