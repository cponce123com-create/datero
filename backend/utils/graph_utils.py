"""
utils/graph_utils.py — Detección de ciclos en el grafo familiar.

Usa la CTE recursiva de parentesco.py para verificar si
una nueva relación crearía un ciclo en el grafo.

Un ciclo ocurre cuando A es ascendiente de B y B es ascendiente
de A (ej: A padre de B, B padre de A).
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Persona


def detectar_ciclo(
    db: Session,
    origen_id: int,
    destino_id: int,
    max_depth: int = 20,
) -> bool:
    """
    Verifica si agregar una relacion origen→destino crearia un ciclo.

    La CTE busca si 'destino' ya es ascendiente de 'origen' en el arbol
    actual (sin la nueva relacion). Si lo es, agregar 'origen→padre→destino'
    crearia un ciclo.

    Retorna True si se detecta ciclo.
    """
    sql = text("""
    WITH RECURSIVE ascendente AS (
        SELECT r.persona_origen_id AS ancestro_id,
               r.persona_destino_id AS descendiente_id,
               1 AS profundidad,
               ARRAY[:origen_id] AS path_ids,
               FALSE AS ciclo
        FROM relaciones r
        WHERE r.persona_destino_id = :origen_id
          AND r.tipo_relacion IN ('padre', 'madre')

        UNION ALL

        SELECT r.persona_origen_id,
               r.persona_destino_id,
               a.profundidad + 1,
               a.path_ids || a.ancestro_id,
               (r.persona_origen_id = ANY(a.path_ids) OR a.profundidad >= :maxp)
        FROM relaciones r
        JOIN ascendente a ON r.persona_destino_id = a.ancestro_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
          AND NOT a.ciclo
    )
    SELECT COUNT(*) AS encontrado
    FROM ascendente
    WHERE ancestro_id = :destino_id
      AND NOT ciclo
    LIMIT 1;
    """)

    row = db.execute(sql, {
        "origen_id": origen_id,
        "destino_id": destino_id,
        "maxp": max_depth,
    }).first()

    return (row and row[0] > 0) if row else False


def detectar_ciclo_por_dni(
    db: Session,
    dni_origen: str,
    dni_destino: str,
) -> bool:
    """Version con DNI en lugar de IDs internos."""
    origen = db.query(Persona).filter(Persona.dni == dni_origen).first()
    destino = db.query(Persona).filter(Persona.dni == dni_destino).first()
    if not origen or not destino:
        return False
    return detectar_ciclo(db, origen.id, destino.id)
