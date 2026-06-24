"""
scripts/seed_prueba_parentesco.py

Genera datos de prueba basados en el arbol genealogico Prolog de
Maxmuthee/Family-tree-Prolog para validar el motor de parentescos.

Uso:
  cd backend && python ../scripts/seed_prueba_parentesco.py

Estructura del arbol (del Prolog original):

  gitahi ── wambui        (pareja)
     ├── peter ── grace   (pareja)
     │    ├── edmund ── sarah (pareja)
     │    │    ├── maxwell
     │    │    ├── ian
     │    │    └── neema
     │    └── kenneth ── carol (pareja)
     │         ├── tracy
     │         └── noah
     └── solomon ── faith  (pareja)
          ├── patrick ── esther (pareja)
          │    ├── nissy
          │    └── nadia
          └── nelly ── alfy  (pareja)
               ├── jabali
               └── jelani
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import SessionLocal, engine
from models import Persona, Relacion
from sqlalchemy import text


# ═══════════════════════════════════════════════════════════════════════════════
# DATOS DEL ARBOL PROLOG
# ═══════════════════════════════════════════════════════════════════════════════

PERSONAS = [
    # (dni, nombres, ap_paterno, genero)
    ("GITAHI",  "GITAHI",  "ROOT",     "MASCULINO"),
    ("WAMBUI",  "WAMBUI",  "ROOT",     "FEMENINO"),
    ("PETER",   "PETER",   "GITAHI",   "MASCULINO"),
    ("SOLOMON", "SOLOMON", "GITAHI",   "MASCULINO"),
    ("GRACE",   "GRACE",   "GITAHI",   "FEMENINO"),
    ("FAITH",   "FAITH",   "GITAHI",   "FEMENINO"),
    ("EDMUND",  "EDMUND",  "PETER",    "MASCULINO"),
    ("KENNETH", "KENNETH", "PETER",    "MASCULINO"),
    ("SARAH",   "SARAH",   "PETER",    "FEMENINO"),
    ("MAXWELL", "MAXWELL", "EDMUND",   "MASCULINO"),
    ("IAN",     "IAN",     "EDMUND",   "MASCULINO"),
    ("NEEMA",   "NEEMA",   "EDMUND",   "FEMENINO"),
    ("CAROL",   "CAROL",   "PETER",    "FEMENINO"),
    ("TRACY",   "TRACY",   "KENNETH",  "FEMENINO"),
    ("NOAH",    "NOAH",    "KENNETH",  "MASCULINO"),
    ("PATRICK", "PATRICK", "SOLOMON",  "MASCULINO"),
    ("NELLY",   "NELLY",   "SOLOMON",  "FEMENINO"),
    ("ESTHER",  "ESTHER",  "SOLOMON",  "FEMENINO"),
    ("NISSY",   "NISSY",   "PATRICK",  "FEMENINO"),
    ("NADIA",   "NADIA",   "PATRICK",  "FEMENINO"),
    ("ALFY",    "ALFY",    "SOLOMON",  "MASCULINO"),
    ("JABALI",  "JABALI",  "NELLY",    "MASCULINO"),
    ("JELANI",  "JELANI",  "NELLY",    "MASCULINO"),
]

# Relaciones: (dni_origen, tipo, dni_destino)
# Se almacena SOLO la relacion directa (padre/madre)
# El resto se infiere via CTE
RELACIONES = [
    # gitahi + wambui → peter, solomon
    ("GITAHI",  "padre",  "PETER"),
    ("WAMBUI",  "madre",  "PETER"),
    ("GITAHI",  "padre",  "SOLOMON"),
    ("WAMBUI",  "madre",  "SOLOMON"),

    # peter + grace → edmund, kenneth
    ("PETER",   "padre",  "EDMUND"),
    ("GRACE",   "madre",  "EDMUND"),
    ("PETER",   "padre",  "KENNETH"),
    ("GRACE",   "madre",  "KENNETH"),

    # solomon + faith → patrick, nelly
    ("SOLOMON", "padre",  "PATRICK"),
    ("FAITH",   "madre",  "PATRICK"),
    ("SOLOMON", "padre",  "NELLY"),
    ("FAITH",   "madre",  "NELLY"),

    # edmund + sarah → maxwell, ian, neema
    ("EDMUND",  "padre",  "MAXWELL"),
    ("SARAH",   "madre",  "MAXWELL"),
    ("EDMUND",  "padre",  "IAN"),
    ("SARAH",   "madre",  "IAN"),
    ("EDMUND",  "padre",  "NEEMA"),
    ("SARAH",   "madre",  "NEEMA"),

    # kenneth + carol → tracy, noah
    ("KENNETH", "padre",  "TRACY"),
    ("CAROL",   "madre",  "TRACY"),
    ("KENNETH", "padre",  "NOAH"),
    ("CAROL",   "madre",  "NOAH"),

    # patrick + esther → nissy, nadia
    ("PATRICK", "padre",  "NISSY"),
    ("ESTHER",  "madre",  "NISSY"),
    ("PATRICK", "padre",  "NADIA"),
    ("ESTHER",  "madre",  "NADIA"),

    # nelly + alfy → jabali, jelani
    ("NELLY",   "madre",  "JABALI"),
    ("ALFY",    "padre",  "JABALI"),
    ("NELLY",   "madre",  "JELANI"),
    ("ALFY",    "padre",  "JELANI"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# RELACIONES ESPERADAS (para validacion)
# ═══════════════════════════════════════════════════════════════════════════════

# Formato: (dni_consulta, dni_pariente, tipo_esperado, pasos)
# Solo cubre los casos mas representativos
VALIDACIONES = [
    # MAXWELL: hijo de EDMUND y SARAH
    ("MAXWELL", "EDMUND",  "padre",   1),
    ("MAXWELL", "SARAH",   "madre",   1),
    ("MAXWELL", "PETER",   "abuelo",  2),
    ("MAXWELL", "GRACE",   "abuela",  2),
    ("MAXWELL", "GITAHI",  "bisabuelo", 3),
    ("MAXWELL", "WAMBUI",  "bisabuela", 3),
    ("MAXWELL", "KENNETH", "tio",     2),
    ("MAXWELL", "CAROL",   "tia",     2),
    ("MAXWELL", "IAN",     "hermano", 1),
    ("MAXWELL", "NEEMA",   "hermana", 1),
    ("MAXWELL", "TRACY",   "prima",   3),
    ("MAXWELL", "NOAH",    "primo",   3),

    # PATRICK: hijo de SOLOMON y FAITH
    ("PATRICK", "SOLOMON", "padre",   1),
    ("PATRICK", "FAITH",   "madre",   1),
    ("PATRICK", "GITAHI",  "abuelo",  2),
    ("PATRICK", "WAMBUI",  "abuela",  2),
    ("PATRICK", "PETER",   "tio",     2),
    ("PATRICK", "GRACE",   "tia",     2),
    ("PATRICK", "NELLY",   "hermana", 1),
    ("PATRICK", "NISSY",   "hija",    1),
    ("PATRICK", "NADIA",   "hija",    1),

    # PETER: padre de EDMUND y KENNETH
    ("PETER",   "GITAHI",  "padre",   1),
    ("PETER",   "WAMBUI",  "madre",   1),
    ("PETER",   "SOLOMON", "hermano", 1),
    ("PETER",   "GRACE",   "conyuge", 1),
    ("PETER",   "EDMUND",  "hijo",    1),
    ("PETER",   "KENNETH", "hijo",    1),
    ("PETER",   "MAXWELL", "nieto",   2),
    ("PETER",   "IAN",     "nieto",   2),
    ("PETER",   "TRACY",   "nieta",  2),
    ("PETER",   "NOAH",    "nieto",   2),
    ("PETER",   "PATRICK", "sobrino", 2),
    ("PETER",   "NELLY",   "sobrina", 2),

    # GITAHI: raiz del arbol
    ("GITAHI",  "WAMBUI",  "conyuge", 1),
    ("GITAHI",  "PETER",   "hijo",    1),
    ("GITAHI",  "SOLOMON", "hijo",    1),
    ("GITAHI",  "EDMUND",  "nieto",   2),
    ("GITAHI",  "KENNETH", "nieto",   2),
    ("GITAHI",  "PATRICK", "nieto",   2),
    ("GITAHI",  "NELLY",   "nieta",   2),
    ("GITAHI",  "MAXWELL", "bisnieto", 3),

    # EDMUND + SARAH: conyuges
    ("EDMUND",  "SARAH",   "conyuge", 1),
    ("EDMUND",  "KENNETH", "hermano", 1),
    ("EDMUND",  "CAROL",   "cunada",  2),
]


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES
# ═══════════════════════════════════════════════════════════════════════════════

def seed_database(db):
    """Inserta datos de prueba en la BD."""
    print("Limpiando datos existentes...")
    for tabla in ["relaciones", "personas"]:
        db.execute(text(f"DELETE FROM {tabla}"))
    db.commit()

    print(f"Insertando {len(PERSONAS)} personas...")
    for dni, nombres, apellido, genero in PERSONAS:
        db.add(Persona(
            dni=dni, nombres=nombres,
            apellido_paterno=apellido, genero=genero,
        ))
    db.flush()

    # Mapa DNI → ID
    pers_map = {p.dni: p.id for p in db.query(Persona).all()}

    print(f"Insertando {len(RELACIONES)} relaciones...")
    for odni, tipo, ddni in RELACIONES:
        db.add(Relacion(
            persona_origen_id=pers_map[odni],
            persona_destino_id=pers_map[ddni],
            tipo_relacion=tipo,
            certeza="confirmado",
        ))
    db.commit()
    print("Seed completado.
")


def run_validaciones(db):
    """Ejecuta validaciones contra parentesco.py."""
    from parentesco import calcular_parentesco

    ok = 0
    fail = 0
    for dni_q, dni_p, tipo_esp, pasos_esp in VALIDACIONES:
        resultados = calcular_parentesco(db, dni_q)
        encontrado = [r for r in resultados if r["dni"] == dni_p]

        if not encontrado:
            print(f"  ❌ {dni_q} → {dni_p}: NO ENCONTRADO (esperado {tipo_esp})")
            fail += 1
            continue

        r = encontrado[0]
        if r["tipo_parentesco"] == tipo_esp:
            if r["pasos"] == pasos_esp:
                print(f"  ✅ {dni_q} → {dni_p}: {tipo_esp} ({pasos_esp})")
                ok += 1
            else:
                print(f"  ⚠️  {dni_q} → {dni_p}: tipo OK ({r['tipo_parentesco']}) "
                      f"pero pasos {r['pasos']} != {pasos_esp}")
                fail += 1
        else:
            print(f"  ❌ {dni_q} → {dni_p}: esperado '{tipo_esp}' "
                  f"obtenido '{r['tipo_parentesco']}'")
            fail += 1

    print(f"
Total: {ok} ✅, {fail} ❌ de {len(VALIDACIONES)}")
    return fail == 0


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_database(db)
        print("=" * 60)
        print("VALIDACIONES DE PARENTESCO (contra Prolog)")
        print("=" * 60)
        exito = run_validaciones(db)
        sys.exit(0 if exito else 1)
    finally:
        db.close()
