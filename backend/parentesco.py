"""
parentesco.py — Motor de inferencia de parentescos via CTE Recursiva (PostgreSQL).

ANTES: 15+ consultas SQL anidadas (una por tipo: abuelos, tios, sobrinos, etc.)
AHORA: UNA unica CTE recursiva que recorre el grafo en ambas direcciones
       y deduce TODOS los parentescos en 1-2 queries.

ALGORITMO:
  1. CTE base: recoge las relaciones directas (padre/madre/hermano/conyuge).
  2. PASO RECURSIVO (subida): de hijo → padre → abuelo → bisabuelo...
  3. PASO RECURSIVO (bajada): de padre → hijo → nieto → bisnieto...
  4. DEDUCCION: cruza los caminos para inferir tios, primos, cuñados, etc.

La CTE retorna filas con (persona_id, pariente_id, tipo_parentesco, pasos).
La funcion Python traduce estos IDs a objetos Persona para la API.

Ejemplo de consulta SQL generada:
  WITH RECURSIVE arbol AS (
    SELECT ... FROM relaciones WHERE persona_origen_id = :pid
    UNION
    SELECT ... FROM relaciones r JOIN arbol a ON ...
  )
  SELECT * FROM arbol;
"""

from functools import lru_cache
from typing import List, Dict, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Persona


# ═══════════════════════════════════════════════════════════════════════════════
# CTE RECURSIVA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

# Mapeo de tipos de relacion directa a su inversa
_INVERSA = {"padre": "hijo", "madre": "hija", "hermano": "hermano",
            "hermana": "hermana", "conyuge": "conyuge"}


def _cte_parentesco_completo(db: Session, persona_id: int) -> List[Dict]:
    """
    Ejecuta una CTE recursiva que recorre el arbol familiar.

    La CTE tiene DOS brazos:
      - ASCENDENTE: del individuo hacia padres/abuelos/bisabuelos
      - DESCENDENTE: del individuo hacia hijos/nietos/bisnietos

    Cada fila retorna:
      pariente_id: ID de la persona encontrada
      tipo_parentesco: etiqueta textual del vinculo
      pasos: profundidad en el arbol (1=directo, 2=abuelo, etc.)

    La CTE usa indices compuestos idx_relaciones_origen_destino
    e idx_relaciones_destino_origen para eficiencia O(log n).
    """
    sql = text("""
    WITH RECURSIVE
    -- 1. Relaciones directas del individuo
    directas AS (
        SELECT r.persona_origen_id AS a_id,
               r.persona_destino_id AS b_id,
               r.tipo_relacion
        FROM relaciones r
        WHERE r.persona_origen_id = :pid
           OR r.persona_destino_id = :pid
    ),
    -- 2. Arbol ascendente: del individuo hacia ancestros
    ascendente AS (
        -- Base: padres directos
        SELECT r.persona_origen_id AS ancestro_id,
               r.persona_destino_id AS descendiente_id,
               r.tipo_relacion,
               1 AS profundidad
        FROM relaciones r
        WHERE r.persona_destino_id = :pid
          AND r.tipo_relacion IN ('padre', 'madre')

        UNION ALL

        -- Recursivo: abuelos, bisabuelos...
        SELECT r.persona_origen_id,
               r.persona_destino_id,
               r.tipo_relacion,
               a.profundidad + 1
        FROM relaciones r
        JOIN ascendente a ON r.persona_destino_id = a.ancestro_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
    ),
    -- 3. Arbol descendente: del individuo hacia descendientes
    descendente AS (
        -- Base: hijos directos
        SELECT r.persona_destino_id AS descendiente_id,
               r.persona_origen_id AS ancestro_id,
               r.tipo_relacion,
               1 AS profundidad
        FROM relaciones r
        WHERE r.persona_origen_id = :pid
          AND r.tipo_relacion IN ('padre', 'madre')

        UNION ALL

        -- Recursivo: nietos, bisnietos...
        SELECT r.persona_destino_id,
               r.persona_origen_id,
               r.tipo_relacion,
               d.profundidad + 1
        FROM relaciones r
        JOIN descendente d ON r.persona_origen_id = d.descendiente_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
    ),
    -- 4. Hermanos: personas que comparten al menos un padre
    hermanos AS (
        SELECT DISTINCT
            r2.persona_destino_id AS hermano_id,
            'hermano' AS tipo,
            1 AS prof
        FROM relaciones r1
        JOIN relaciones r2 ON r1.persona_origen_id = r2.persona_origen_id
                           AND r2.persona_destino_id != :pid
        WHERE r1.persona_destino_id = :pid
          AND r1.tipo_relacion IN ('padre', 'madre')
          AND r2.tipo_relacion IN ('padre', 'madre')
    ),
    -- 5. Conyuges: relaciones directas de tipo conyuge
    conyuges AS (
        SELECT CASE
                 WHEN r.persona_origen_id = :pid THEN r.persona_destino_id
                 ELSE r.persona_origen_id
               END AS conyuge_id,
               'conyuge' AS tipo,
               1 AS prof
        FROM relaciones r
        WHERE (r.persona_origen_id = :pid OR r.persona_destino_id = :pid)
          AND r.tipo_relacion = 'conyuge'
    ),
    -- 6. UNION de todos los parientes directos
    parientes_directos AS (
        SELECT :pid AS persona_id,
               a.ancestro_id AS pariente_id,
               CASE
                 WHEN a.tipo_relacion = 'padre' AND a.profundidad = 1 THEN 'PADRE'
                 WHEN a.tipo_relacion = 'madre' AND a.profundidad = 1 THEN 'MADRE'
                 WHEN a.tipo_relacion = 'padre' AND a.profundidad = 2 THEN 'ABUELO'
                 WHEN a.tipo_relacion = 'madre' AND a.profundidad = 2 THEN 'ABUELA'
                 WHEN a.tipo_relacion = 'padre' AND a.profundidad >= 3 THEN 'BISABUELO'
                 WHEN a.tipo_relacion = 'madre' AND a.profundidad >= 3 THEN 'BISABUELA'
               END AS tipo,
               a.profundidad AS pasos
        FROM ascendente a

        UNION ALL

        SELECT :pid,
               d.descendiente_id,
               CASE
                 WHEN d.tipo_relacion = 'padre' AND d.profundidad = 1 THEN 'HIJO'
                 WHEN d.tipo_relacion = 'madre' AND d.profundidad = 1 THEN 'HIJA'
                 WHEN d.tipo_relacion = 'padre' AND d.profundidad = 2 THEN 'NIETO'
                 WHEN d.tipo_relacion = 'madre' AND d.profundidad = 2 THEN 'NIETA'
                 WHEN d.tipo_relacion = 'padre' AND d.profundidad >= 3 THEN 'BISNIETO'
                 WHEN d.tipo_relacion = 'madre' AND d.profundidad >= 3 THEN 'BISNIETA'
               END AS tipo,
               d.profundidad
        FROM descendente d

        UNION ALL

        SELECT :pid, h.hermano_id, CASE WHEN h.tipo = 'hermano'
          THEN (SELECT CASE WHEN p.genero = 'MASCULINO' THEN 'HERMANO' ELSE 'HERMANA' END
                FROM (VALUES('MASCULINO')) AS p(genero)
                WHERE EXISTS (SELECT 1 FROM personas WHERE id = h.hermano_id))
          ELSE 'HERMANO' END, 1
        FROM hermanos h

        UNION ALL

        SELECT :pid, c.conyuge_id, 'CONYUGE', 1
        FROM conyuges c
    ),
    -- 7. DEDUCCION de parentescos compuestos:
    --    Tios: hermanos de los padres
    tios AS (
        SELECT DISTINCT :pid AS persona_id,
               h.hermano_id AS pariente_id,
               'TIO' AS tipo,
               2 AS pasos
        FROM ascendente a
        JOIN hermanos h ON a.ancestro_id IN (
            SELECT r.persona_destino_id
            FROM relaciones r
            WHERE r.persona_origen_id IN (
                SELECT r2.persona_origen_id
                FROM relaciones r2
                WHERE r2.persona_destino_id = h.hermano_id
                  AND r2.tipo_relacion IN ('padre', 'madre')
            )
        )
        WHERE a.profundidad = 1
    ),
    --    Sobrinos: hijos de los hermanos
    sobrinos AS (
        SELECT DISTINCT :pid AS persona_id,
               r.persona_destino_id AS pariente_id,
               'SOBRINO' AS tipo,
               2 AS pasos
        FROM hermanos h
        JOIN relaciones r ON r.persona_origen_id = h.hermano_id
        WHERE r.tipo_relacion IN ('padre', 'madre')
    ),
    --    Cuniados: conyuges de hermanos, y hermanos del conyuge
    cuniados AS (
        SELECT DISTINCT :pid AS persona_id,
               c.conyuge_id AS pariente_id,
               'CUNIADO' AS tipo,
               2 AS pasos
        FROM hermanos h
        JOIN conyuges c ON c.conyuge_id != :pid
                       AND c.conyuge_id != h.hermano_id
        WHERE h.hermano_id = c.conyuge_id
    ),
    --    Primos: hijos de los tios (hermanos de los padres)
    primos AS (
        SELECT DISTINCT :pid AS persona_id,
               r.persona_destino_id AS pariente_id,
               'PRIMO' AS tipo,
               3 AS pasos
        FROM ascendente a
        JOIN hermanos h ON h.hermano_id != a.ancestro_id
        JOIN relaciones r ON r.persona_origen_id = h.hermano_id
        WHERE a.profundidad = 1
          AND r.tipo_relacion IN ('padre', 'madre')
    )
    -- 8. RESULTADO FINAL: todos los parientes unicos
    SELECT DISTINCT ON (pariente_id) pariente_id, tipo, pasos
    FROM (
        SELECT * FROM parientes_directos
        UNION ALL
        SELECT * FROM tios
        UNION ALL
        SELECT * FROM sobrinos
        UNION ALL
        SELECT * FROM cuniados
        UNION ALL
        SELECT * FROM primos
    ) todos
    WHERE pariente_id != :pid
    ORDER BY pariente_id, pasos ASC;
    """)

    rows = db.execute(sql, {"pid": persona_id}).fetchall()
    return [{"pariente_id": r[0], "tipo": r[1], "pasos": r[2]} for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCION PRINCIPAL (con cache)
# ═══════════════════════════════════════════════════════════════════════════════

_RESULTADO_CACHE: Dict[int, Tuple[List[Dict], List[Dict]]] = {}
_CACHE_TTL = 300  # 5 minutos


def _genero(db: Session, persona_id: int) -> str:
    """Determina genero de una persona por su tipo de relacion como padre/madre."""
    row = db.execute(
        text("SELECT tipo_relacion FROM relaciones WHERE persona_origen_id = :pid "
             "AND tipo_relacion IN ('padre','madre') LIMIT 1"),
        {"pid": persona_id}
    ).first()
    if row and row[0] == "padre":
        return "MASCULINO"
    return "FEMENINO" if (row and row[0] == "madre") else "DESCONOCIDO"


def _parentesco_a_texto(tipo: str, genero: str) -> str:
    """Convierte tipo base a texto legible segun genero."""
    mapa = {
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
    }
    masc, fem = mapa.get(tipo, (tipo.lower(), tipo.lower()))
    return masc if genero == "MASCULINO" else fem


@lru_cache(maxsize=128)
def _cte_cached(db_id: int, persona_id: int) -> Tuple[Tuple, ...]:
    """
    Version cacheable de la CTE.
    db_id es un hash del id de sesion (para invalidar por sesion).
    """
    # No podemos cachear objetos db, asi que creamos una sesion nueva
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
    Retorna lista de dicts: {dni, apellidos, nombres, tipo_parentesco}.

    Uso:
      resultados = calcular_parentesco(db, "47435679")
      for r in resultados:
          print(r["tipo_parentesco"], "-", r["nombres"])
    """
    persona = db.query(Persona).filter(Persona.dni == dni, Persona.activo == True).first()
    if not persona:
        return []

    # Obtener resultados via CTE
    resultados_cte = _cte_parentesco_completo(db, persona.id)

    # Convertir a formato API
    salida = []
    for r in resultados_cte:
        pariente = db.query(Persona).filter(
            Persona.id == r["pariente_id"], Persona.activo == True
        ).first()
        if not pariente:
            continue

        gen = _genero(db, pariente.id)
        tipo_texto = _parentesco_a_texto(r["tipo"], gen)

        salida.append({
            "dni": pariente.dni,
            "apellidos": f"{pariente.apellido_paterno} {pariente.apellido_materno or ''}".strip(),
            "nombres": pariente.nombres,
            "tipo_parentesco": tipo_texto,
            "pasos": r["pasos"],
        })

    return salida


# ═══════════════════════════════════════════════════════════════════════════════
# API COMPATIBLE (mantiene firma con las funciones anteriores)
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_todos_parentescos(db: Session, persona: Persona) -> List[Dict]:
    """
    Version compatible con la API anterior.
    Retorna lista de dicts con keys: tipo_parentesco, persona (objeto), camino.
    """
    resultados = calcular_parentesco(db, persona.dni)
    salida = []
    for r in resultados:
        p = db.query(Persona).filter(Persona.dni == r["dni"]).first()
        if not p:
            continue
        salida.append({
            "tipo_parentesco": r["tipo_parentesco"],
            "persona": p,
            "camino": f"Inferido por CTE ({r['tipo_parentesco']}, {r['pasos']} pasos)",
        })
    return salida


def inferir_parentesco_especifico(
    db: Session, persona: Persona, tipo: str
) -> List[Dict]:
    """
    Version compatible: filtra por tipo especifico.
    tipo puede ser: padre, madre, abuelo, abuela, hijo, hija, etc.
    """
    todos = inferir_todos_parentescos(db, persona)
    tipo_lower = tipo.lower().strip()
    return [r for r in todos if r["tipo_parentesco"] == tipo_lower]


def _obtener_conyuges(db: Session, persona_id: int) -> List[Persona]:
    """Helper: obtiene los conyuges de una persona (para compatibilidad)."""
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
