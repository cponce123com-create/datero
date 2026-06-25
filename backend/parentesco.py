"""
parentesco.py — Motor de inferencia de parentescos via CTE Recursiva (PostgreSQL).

ALGORITMO:
  1. CTE recursiva bidireccional con deteccion de ciclos (ARRAY path_ids).
  2. UNION de 5 subconsultas: directos, tios, sobrinos, cunados, primos.
  3. Suegros y yernos/nueras se infieren via conyuges + ascendentes.
  4. Cache LRU invalidable via invalidar_cache_parentesco().

Uso tipico:
  resultado = calcular_parentesco(db, "12345678")
  for r in resultado:
      print(r["tipo_parentesco"], r["nombres"])

Invalidacion de cache:
  invalidar_cache_parentesco()  # Al crear/eliminar una relacion
"""

from functools import lru_cache
from typing import List, Dict, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Persona


# ═══════════════════════════════════════════════════════════════════════════════
# INVALIDACION DE CACHE
# ═══════════════════════════════════════════════════════════════════════════════

def invalidar_cache_parentesco():
    """
    Limpia el cache LRU de la CTE.
    Llamar despues de crear, modificar o eliminar relaciones/personas.
    """
    _cte_cached.cache_clear()


# ═══════════════════════════════════════════════════════════════════════════════
# CTE RECURSIVA PRINCIPAL (con deteccion de ciclos)
# ═══════════════════════════════════════════════════════════════════════════════

# Constante: maximo de pasos para evitar arboles demasiado profundos
_MAX_PASOS = 10


def _cte_parentesco_completo(db: Session, persona_id: int) -> List[Dict]:
    """
    Ejecuta una CTE recursiva que recorre el grafo familiar en ambas direcciones.

    Incluye:
      - Ascendentes: padres, abuelos, bisabuelos
      - Descendentes: hijos, nietos, bisnietos
      - Hermanos (por padre/madre comun)
      - Conyuges
      - Tios: hermanos de los padres
      - Sobrinos: hijos de los hermanos
      - Primos: hijos de los tios
      - Cunados: conyuge del hermano O hermano del conyuge
      - Suegros: padres del conyuge
      - Yernos/Nueras: conyuges de los hijos

    Retorna lista de dicts con: pariente_id, tipo, pasos.
    La persona consultada (:pid) nunca aparece en los resultados.
    Los ciclos se detectan via ARRAY path_ids.
    """
    sql = text("""
    WITH RECURSIVE
    -- 1. Arbol ascendente (de la persona a sus ancestros)
    ascendente AS (
        SELECT
            r.persona_origen_id AS ancestro_id,
            r.persona_destino_id AS descendiente_id,
            r.tipo_relacion,
            1 AS profundidad,
            ARRAY[:pid] AS path_ids,
            FALSE AS ciclo
        FROM relaciones r
        WHERE r.persona_destino_id = :pid
          AND r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_origen_id != :pid

        UNION ALL

        SELECT
            r.persona_origen_id,
            r.persona_destino_id,
            r.tipo_relacion,
            a.profundidad + 1,
            a.path_ids || a.ancestro_id,
            (r.persona_origen_id = ANY(a.path_ids) OR a.profundidad >= :maxp) AS ciclo
        FROM relaciones r
        JOIN ascendente a ON r.persona_destino_id = a.ancestro_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_origen_id != r.persona_destino_id
          AND NOT ciclo
    ),
    -- 2. Arbol descendente (de la persona a sus descendientes)
    descendente AS (
        SELECT
            r.persona_destino_id AS descendiente_id,
            r.persona_origen_id AS ancestro_id,
            r.tipo_relacion,
            1 AS profundidad,
            ARRAY[:pid] AS path_ids,
            FALSE AS ciclo
        FROM relaciones r
        WHERE r.persona_origen_id = :pid
          AND r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_destino_id != :pid

        UNION ALL

        SELECT
            r.persona_destino_id,
            r.persona_origen_id,
            r.tipo_relacion,
            d.profundidad + 1,
            d.path_ids || d.descendiente_id,
            (r.persona_destino_id = ANY(d.path_ids) OR d.profundidad >= :maxp) AS ciclo
        FROM relaciones r
        JOIN descendente d ON r.persona_origen_id = d.descendiente_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_destino_id != r.persona_origen_id
          AND NOT ciclo
    ),
    -- 3. Hermanos (comparten al menos un progenitor O relacion directa)
    hermanos AS (
        SELECT DISTINCT
            r2.persona_destino_id AS hermano_id
        FROM relaciones r1
        JOIN relaciones r2 ON r1.persona_origen_id = r2.persona_origen_id
                           AND r2.persona_destino_id != :pid
        WHERE r1.persona_destino_id = :pid
          AND r1.tipo_relacion IN ('padre', 'madre')
          AND r2.tipo_relacion IN ('padre', 'madre')
        UNION
        SELECT DISTINCT
            CASE WHEN r.persona_origen_id = :pid THEN r.persona_destino_id
                 ELSE r.persona_origen_id END AS hermano_id
        FROM relaciones r
        WHERE (r.persona_origen_id = :pid OR r.persona_destino_id = :pid)
          AND r.tipo_relacion IN ('hermano', 'hermana')
          AND r.persona_origen_id != r.persona_destino_id
    ),
    -- 4. Conyuges (relacion directa simetrica)
    conyuges AS (
        SELECT DISTINCT
            CASE
                WHEN r.persona_origen_id = :pid THEN r.persona_destino_id
                ELSE r.persona_origen_id
            END AS conyuge_id
        FROM relaciones r
        WHERE (r.persona_origen_id = :pid OR r.persona_destino_id = :pid)
          AND r.tipo_relacion = 'conyuge'
          AND r.persona_origen_id != r.persona_destino_id
    ),
    -- 5. Parientes directos (linea recta)
    parientes_directos AS (
        SELECT :pid AS persona_id, a.ancestro_id AS pariente_id,
               CASE
                 WHEN a.tipo_relacion = 'padre' AND a.profundidad = 1 THEN 'PADRE'
                 WHEN a.tipo_relacion = 'madre' AND a.profundidad = 1 THEN 'MADRE'
                 WHEN a.tipo_relacion = 'padre' AND a.profundidad = 2 THEN 'ABUELO'
                 WHEN a.tipo_relacion = 'madre' AND a.profundidad = 2 THEN 'ABUELA'
                 WHEN a.tipo_relacion = 'padre' AND a.profundidad >= 3 THEN 'BISABUELO'
                 WHEN a.tipo_relacion = 'madre' AND a.profundidad >= 3 THEN 'BISABUELA'
               END AS tipo, a.profundidad AS pasos
        FROM ascendente a WHERE NOT a.ciclo
        UNION ALL
        SELECT :pid, d.descendiente_id,
               CASE
                 WHEN d.tipo_relacion = 'padre' AND d.profundidad = 1 THEN 'HIJO'
                 WHEN d.tipo_relacion = 'madre' AND d.profundidad = 1 THEN 'HIJA'
                 WHEN d.tipo_relacion = 'padre' AND d.profundidad = 2 THEN 'NIETO'
                 WHEN d.tipo_relacion = 'madre' AND d.profundidad = 2 THEN 'NIETA'
                 WHEN d.tipo_relacion = 'padre' AND d.profundidad >= 3 THEN 'BISNIETO'
                 WHEN d.tipo_relacion = 'madre' AND d.profundidad >= 3 THEN 'BISNIETA'
               END AS tipo, d.profundidad
        FROM descendente d WHERE NOT d.ciclo
        UNION ALL
        SELECT :pid, h.hermano_id, 'HERMANO' AS tipo, 1 FROM hermanos h
        UNION ALL
        SELECT :pid, c.conyuge_id, 'CONYUGE' AS tipo, 1 FROM conyuges c
    ),
    -- 6. Inferencia de parentescos compuestos
    tios AS (
        SELECT DISTINCT :pid AS persona_id, h.hermano_id AS pariente_id,
               'TIO' AS tipo, 2 AS pasos
        FROM ascendente a
        JOIN hermanos h ON h.hermano_id != a.ancestro_id
        WHERE a.profundidad = 1
          AND NOT EXISTS (
              SELECT 1 FROM relaciones r
              WHERE r.persona_origen_id = h.hermano_id
                AND r.persona_destino_id = a.ancestro_id
                AND r.tipo_relacion IN ('padre', 'madre')
          )
    ),
    sobrinos AS (
        SELECT DISTINCT :pid AS persona_id, r.persona_destino_id AS pariente_id,
               'SOBRINO' AS tipo, 2 AS pasos
        FROM hermanos h
        JOIN relaciones r ON r.persona_origen_id = h.hermano_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_destino_id != :pid
    ),
    cuniados AS (
        SELECT DISTINCT :pid AS persona_id,
               CASE WHEN c.conyuge_id = h.hermano_id THEN c.conyuge_id ELSE h.hermano_id END AS pariente_id,
               'CUNIADO' AS tipo, 2 AS pasos
        FROM hermanos h
        JOIN conyuges c ON c.conyuge_id != :pid
        WHERE h.hermano_id = c.conyuge_id
    ),
    primos AS (
        SELECT DISTINCT :pid AS persona_id, r.persona_destino_id AS pariente_id,
               'PRIMO' AS tipo, 3 AS pasos
        FROM ascendente a
        JOIN hermanos h ON h.hermano_id != a.ancestro_id
        JOIN relaciones r ON r.persona_origen_id = h.hermano_id
        WHERE a.profundidad = 1 AND r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_destino_id != :pid
    ),
    -- 7. Suegros: padres del conyuge
    suegros AS (
        SELECT DISTINCT :pid AS persona_id,
               r.persona_origen_id AS pariente_id,
               CASE WHEN r.tipo_relacion = 'padre' THEN 'SUEGRO' ELSE 'SUEGRA' END AS tipo,
               2 AS pasos
        FROM conyuges c
        JOIN relaciones r ON r.persona_destino_id = c.conyuge_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
          AND r.persona_origen_id != :pid
    ),
    -- 8. Yernos/Nueras: conyuges de los hijos
    yernos_nueras AS (
        SELECT DISTINCT :pid AS persona_id,
               CASE WHEN r.persona_origen_id = d.descendiente_id THEN r.persona_destino_id
                    ELSE r.persona_origen_id END AS pariente_id,
               'YERNO_NUERA' AS tipo, 2 AS pasos
        FROM descendente d
        JOIN relaciones r ON (r.persona_origen_id = d.descendiente_id OR r.persona_destino_id = d.descendiente_id)
        WHERE d.profundidad = 1
          AND r.tipo_relacion = 'conyuge'
          AND (CASE WHEN r.persona_origen_id = d.descendiente_id THEN r.persona_destino_id
                    ELSE r.persona_origen_id END) != :pid
    )
    -- 9. RESULTADO FINAL: pariente unico con menor profundidad
    SELECT DISTINCT ON (pariente_id) pariente_id, tipo, pasos
    FROM (
        SELECT * FROM parientes_directos UNION ALL
        SELECT * FROM tios UNION ALL
        SELECT * FROM sobrinos UNION ALL
        SELECT * FROM cuniados UNION ALL
        SELECT * FROM primos UNION ALL
        SELECT * FROM suegros UNION ALL
        SELECT * FROM yernos_nueras
    ) todos
    WHERE pariente_id != :pid AND tipo IS NOT NULL
    ORDER BY pariente_id, pasos ASC;
    """)

    rows = db.execute(sql, {"pid": persona_id, "maxp": _MAX_PASOS}).fetchall()
    return [{"pariente_id": row[0], "tipo": row[1], "pasos": row[2]} for row in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# INFERENCIA DE GENERO (fallback cuando Persona.genero es NULL)
# ═══════════════════════════════════════════════════════════════════════════════

def _inferir_genero(db: Session, persona_id: int) -> str:
    """Infers genero desde relaciones padre/madre."""
    row = db.execute(
        text("SELECT tipo_relacion FROM relaciones WHERE persona_origen_id = :pid "
             "AND tipo_relacion IN ('padre','madre') LIMIT 1"),
        {"pid": persona_id}
    ).first()
    if row:
        return "MASCULINO" if row[0] == "padre" else "FEMENINO"
    return "DESCONOCIDO"


# ═══════════════════════════════════════════════════════════════════════════════
# MAPEO DE TIPO A TEXTO SEGUN GENERO
# ═══════════════════════════════════════════════════════════════════════════════

_TIPO_MAPA = {
    "PADRE": ("padre", "madre"),
    "ABUELO": ("abuelo", "abuela"),
    "BISABUELO": ("bisabuelo", "bisabuela"),
    "HIJO": ("hijo", "hija"),
    "NIETO": ("nieto", "nieta"),
    "BISNIETO": ("bisnieto", "bisnieta"),
    "HERMANO": ("hermano", "hermana"),
    "TIO": ("tio", "tia"),
    "SOBRINO": ("sobrino", "sobrina"),
    "CUNIADO": ("cunado", "cunada"),
    "PRIMO": ("primo", "prima"),
    "CONYUGE": ("conyuge", "conyuge"),
    "SUEGRO": ("suegro", "suegra"),
    "YERNO_NUERA": ("yerno", "nuera"),
}


def _parentesco_a_texto(tipo_base: str, genero: str) -> str:
    masc, fem = _TIPO_MAPA.get(tipo_base, (tipo_base.lower(), tipo_base.lower()))
    return masc if genero.upper() == "MASCULINO" else fem


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCION PRINCIPAL (con cache)
# ═══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=256)
def _cte_cached(persona_id: int) -> Tuple[Tuple[int, str, int], ...]:
    """
    Version cacheada de la CTE (invalida al reiniciar la app).
    """
    from database import SessionLocal
    session = SessionLocal()
    try:
        result = _cte_parentesco_completo(session, persona_id)
        return tuple(sorted(
            (r["pariente_id"], r["tipo"], r["pasos"]) for r in result
        ))
    finally:
        session.close()


def calcular_parentesco(db: Session, dni: str) -> List[Dict]:
    """
    Punto de entrada principal.
    Retorna lista de dicts con: dni, apellidos, nombres, tipo_parentesco, pasos.
    """
    persona = db.query(Persona).filter(Persona.dni == dni, Persona.activo == True).first()
    if not persona:
        return []

    resultados_cte = _cte_cached(persona.id)
    if not resultados_cte:
        return []

    # Obtener personas en una sola consulta IN
    ids_parientes = [r[0] for r in resultados_cte]
    parientes = db.query(Persona).filter(
        Persona.id.in_(ids_parientes), Persona.activo == True
    ).all()
    parientes_dict = {p.id: p for p in parientes}

    # Cache de genero para no consultar repetidamente
    genero_cache: Dict[int, str] = {}

    salida = []
    for pariente_id, tipo_base, pasos in resultados_cte:
        pariente = parientes_dict.get(pariente_id)
        if not pariente:
            continue

        # Genero: del campo o inferido
        gen = "DESCONOCIDO"
        try:
            gen = pariente.genero
        except Exception:
            pass
        if not gen:
            if pariente_id not in genero_cache:
                genero_cache[pariente_id] = _inferir_genero(db, pariente_id)
            gen = genero_cache[pariente_id]

        salida.append({
            "dni": pariente.dni,
            "apellidos": f"{pariente.apellido_paterno} {pariente.apellido_materno or ''}".strip(),
            "nombres": pariente.nombres,
            "tipo_parentesco": _parentesco_a_texto(tipo_base, gen),
            "pasos": pasos,
        })

    return salida


# ═══════════════════════════════════════════════════════════════════════════════
# API COMPATIBLE (firmas esperadas por main.py)
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_todos_parentescos(db: Session, persona: Persona) -> List[Dict]:
    """Version compatible con API anterior: retorna tipo_parentesco, persona, camino."""
    resultados = calcular_parentesco(db, persona.dni)
    salida = []
    for r in resultados:
        p = db.query(Persona).filter(Persona.dni == r["dni"]).first()
        if p:
            salida.append({
                "tipo_parentesco": r["tipo_parentesco"],
                "persona": p,
                "camino": f"CTE ({r['tipo_parentesco']}, {r['pasos']} pasos)",
            })
    return salida


def inferir_parentesco_especifico(db: Session, persona: Persona, tipo: str) -> List[Dict]:
    """Filtra por tipo especifico."""
    todos = inferir_todos_parentescos(db, persona)
    tipo_lower = tipo.lower().strip()
    return [r for r in todos if r["tipo_parentesco"] == tipo_lower]


def _obtener_conyuges(db: Session, persona_id: int) -> List[Persona]:
    """Helper: obtiene conyuges."""
    conyuges = []
    rows = db.execute(
        text("""
        SELECT DISTINCT CASE
            WHEN r.persona_origen_id = :pid THEN r.persona_destino_id
            ELSE r.persona_origen_id
        END AS conyuge_id
        FROM relaciones r
        WHERE (r.persona_origen_id = :pid OR r.persona_destino_id = :pid)
          AND r.tipo_relacion = 'conyuge'
        """),
        {"pid": persona_id}
    ).fetchall()
    for row in rows:
        p = db.query(Persona).filter(Persona.id == row[0]).first()
        if p:
            conyuges.append(p)
    return conyuges
