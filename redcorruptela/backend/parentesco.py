"""
parentesco.py — Motor de inferencia de parentescos.

Implementa consultas que deducen relaciones familiares complejas
(abuelo, tío, cuñado, etc.) a partir de las relaciones directas almacenadas.

Todas las inferencias se calculan en tiempo real; nada se almacena en caché.
Cada función retorna una lista de resultados con la persona inferida y el
"camino lógico" que explica por qué se dedujo ese parentesco.
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Persona, Relacion


def _nombre(p: Persona) -> str:
    """Helper: retorna el nombre completo de una persona."""
    return p.nombre_completo


# ═══════════════════════════════════════════════════════════════════════════════
# ABUELO / ABUELA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_abuelos(db: Session, persona: Persona) -> List[dict]:
    """
    Abuelo/a: padre o madre del padre o de la madre.

    Camino: dos pasos subiendo por la jerarquía padre/madre.
    """
    resultados = []

    # 1. Encontrar los padres de la persona objetivo
    padres = (
        db.query(Persona)
        .join(Relacion, Persona.id == Relacion.persona_origen_id)
        .filter(
            Relacion.persona_destino_id == persona.id,
            Relacion.tipo_relacion.in_(["padre", "madre"]),
        )
        .all()
    )

    # 2. Para cada padre/madre, encontrar sus propios padres
    for padre in padres:
        tipo_parent = "padre"  # default
        # Determinar si es padre o madre consultando la relación
        rel_parent = (
            db.query(Relacion)
            .filter(
                Relacion.persona_origen_id == padre.id,
                Relacion.persona_destino_id == persona.id,
            )
            .first()
        )
        tipo_parent = rel_parent.tipo_relacion if rel_parent else "padre"

        abuelos = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_origen_id)
            .filter(
                Relacion.persona_destino_id == padre.id,
                Relacion.tipo_relacion.in_(["padre", "madre"]),
            )
            .all()
        )

        for abuelo in abuelos:
            rel_abuelo = (
                db.query(Relacion)
                .filter(
                    Relacion.persona_origen_id == abuelo.id,
                    Relacion.persona_destino_id == padre.id,
                )
                .first()
            )
            tipo_abuelo = rel_abuelo.tipo_relacion if rel_abuelo else "padre"

            # Nombre del parentesco: abuelo o abuela
            parentesco = "abuelo" if tipo_abuelo == "padre" else "abuela"

            camino = (
                f"{_nombre(abuelo)} es {tipo_abuelo} de {_nombre(padre)}, "
                f"y {_nombre(padre)} es {tipo_parent} de {_nombre(persona)}."
            )

            resultados.append({
                "tipo_parentesco": parentesco,
                "persona": abuelo,
                "camino": camino,
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# NIETO / NIETA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_nietos(db: Session, persona: Persona) -> List[dict]:
    """
    Nieto/a: hijo o hija del hijo o de la hija.

    Camino: dos pasos bajando por la jerarquía (la persona es padre/madre
    de alguien, quien a su vez es padre/madre del nieto).
    """
    resultados = []

    # 1. Encontrar los hijos de la persona (personas donde la persona es origen
    #    de una relación padre/madre)
    hijos = (
        db.query(Persona)
        .join(Relacion, Persona.id == Relacion.persona_destino_id)
        .filter(
            Relacion.persona_origen_id == persona.id,
            Relacion.tipo_relacion.in_(["padre", "madre"]),
        )
        .all()
    )

    # 2. Para cada hijo, encontrar sus propios hijos
    for hijo in hijos:
        rel_hijo = (
            db.query(Relacion)
            .filter(
                Relacion.persona_origen_id == persona.id,
                Relacion.persona_destino_id == hijo.id,
            )
            .first()
        )
        tipo_hijo = rel_hijo.tipo_relacion if rel_hijo else "padre"

        nietos = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_destino_id)
            .filter(
                Relacion.persona_origen_id == hijo.id,
                Relacion.tipo_relacion.in_(["padre", "madre"]),
            )
            .all()
        )

        for nieto in nietos:
            rel_nieto = (
                db.query(Relacion)
                .filter(
                    Relacion.persona_origen_id == hijo.id,
                    Relacion.persona_destino_id == nieto.id,
                )
                .first()
            )
            tipo_nieto_rel = rel_nieto.tipo_relacion if rel_nieto else "padre"

            parentesco = "nieto" if tipo_nieto_rel == "padre" else "nieta"

            camino = (
                f"{_nombre(persona)} es {tipo_hijo} de {_nombre(hijo)}, "
                f"y {_nombre(hijo)} es {tipo_nieto_rel} de {_nombre(nieto)}."
            )

            resultados.append({
                "tipo_parentesco": parentesco,
                "persona": nieto,
                "camino": camino,
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# HERMANO / HERMANA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_hermanos(db: Session, persona: Persona) -> List[dict]:
    """
    Hermano/a: persona que comparte al menos un padre o madre con el objetivo.

    Se excluyen relaciones directas de tipo 'hermano'/'hermana' ya registradas,
    pues ésas aparecen en "relaciones directas". Aquí solo inferimos las que
    surgen por compartir padres.
    """
    resultados = []

    # IDs de los padres de la persona
    padres_ids = [
        r.persona_origen_id
        for r in persona.relaciones_destino
        if r.tipo_relacion in ("padre", "madre")
    ]

    if not padres_ids:
        return resultados

    # Otras personas que también tienen esos padres
    hermanos = (
        db.query(Persona)
        .join(Relacion, Persona.id == Relacion.persona_destino_id)
        .filter(
            Relacion.persona_origen_id.in_(padres_ids),
            Relacion.tipo_relacion.in_(["padre", "madre"]),
            Persona.id != persona.id,
            Persona.activo == True,
        )
        .distinct()
        .all()
    )

    # Excluir los que ya tienen relación directa de hermano/hermana
    hermanos_directos_ids = set()
    for r in persona.relaciones_origen:
        if r.tipo_relacion in ("hermano", "hermana"):
            hermanos_directos_ids.add(r.persona_destino_id)
    for r in persona.relaciones_destino:
        if r.tipo_relacion in ("hermano", "hermana"):
            hermanos_directos_ids.add(r.persona_origen_id)

    for h in hermanos:
        if h.id in hermanos_directos_ids:
            continue  # Ya aparece en relaciones directas

        # Determinar qué padre comparten
        padres_compartidos = []
        for pid in padres_ids:
            rel = (
                db.query(Relacion)
                .filter(
                    Relacion.persona_origen_id == pid,
                    Relacion.persona_destino_id == h.id,
                    Relacion.tipo_relacion.in_(["padre", "madre"]),
                )
                .first()
            )
            if rel:
                padre_obj = db.query(Persona).filter(Persona.id == pid).first()
                padres_compartidos.append(_nombre(padre_obj))

        nombres_padres = " y ".join(padres_compartidos) if padres_compartidos else "un progenitor"
        camino = (
            f"{_nombre(h)} comparte a {nombres_padres} "
            f"como progenitor(es) con {_nombre(persona)}."
        )

        resultados.append({
            "tipo_parentesco": "hermano",
            "persona": h,
            "camino": camino,
        })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# TÍO / TÍA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_tios(db: Session, persona: Persona) -> List[dict]:
    """
    Tío/a: hermano o hermana del padre o de la madre.

    Camino: subir al padre/madre, luego bajar a los hermanos de éste
    (personas que comparten padre/madre con el padre/madre de la persona).
    """
    resultados = []

    # 1. Padres de la persona
    padres = (
        db.query(Persona)
        .join(Relacion, Persona.id == Relacion.persona_origen_id)
        .filter(
            Relacion.persona_destino_id == persona.id,
            Relacion.tipo_relacion.in_(["padre", "madre"]),
        )
        .all()
    )

    for padre in padres:
        # 2. Abuelos (padres del padre)
        abuelos_ids = [
            r.persona_origen_id
            for r in (
                db.query(Relacion)
                .filter(
                    Relacion.persona_destino_id == padre.id,
                    Relacion.tipo_relacion.in_(["padre", "madre"]),
                )
                .all()
            )
        ]

        if not abuelos_ids:
            continue

        # 3. Hermanos del padre: otras personas que comparten esos abuelos
        tios = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_destino_id)
            .filter(
                Relacion.persona_origen_id.in_(abuelos_ids),
                Relacion.tipo_relacion.in_(["padre", "madre"]),
                Persona.id != padre.id,
                Persona.activo == True,
            )
            .distinct()
            .all()
        )

        # Relación del padre con la persona
        rel_padre = (
            db.query(Relacion)
            .filter(
                Relacion.persona_origen_id == padre.id,
                Relacion.persona_destino_id == persona.id,
            )
            .first()
        )
        tipo_padre = rel_padre.tipo_relacion if rel_padre else "padre"

        for tio in tios:
            # Ver si ya existe relación directa de tío (hermano del padre)
            ya_registrado = any(
                (r.persona_origen_id == tio.id and r.tipo_relacion in ("hermano", "hermana"))
                or (r.persona_destino_id == tio.id and r.tipo_relacion in ("hermano", "hermana"))
                for r in persona.relaciones_origen
            )

            # Determinar si el abuelo común es padre o madre
            parentesco = "tío"  # genérico

            camino = (
                f"{_nombre(tio)} es hermano/a de {_nombre(padre)}, "
                f"quien es {tipo_padre} de {_nombre(persona)}."
            )

            resultados.append({
                "tipo_parentesco": parentesco,
                "persona": tio,
                "camino": camino,
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# SOBRINO / SOBRINA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_sobrinos(db: Session, persona: Persona) -> List[dict]:
    """
    Sobrino/a: hijo o hija del hermano o hermana.

    Camino: encontrar hermanos, luego encontrar sus hijos.
    """
    resultados = []

    # 1. Encontrar hermanos (por padre común y por relación directa)
    hermanos_ids = set()

    # Hermanos por padre común
    padres_ids = [
        r.persona_origen_id
        for r in persona.relaciones_destino
        if r.tipo_relacion in ("padre", "madre")
    ]
    if padres_ids:
        hermanos_por_sangre = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_destino_id)
            .filter(
                Relacion.persona_origen_id.in_(padres_ids),
                Relacion.tipo_relacion.in_(["padre", "madre"]),
                Persona.id != persona.id,
            )
            .distinct()
            .all()
        )
        for h in hermanos_por_sangre:
            hermanos_ids.add(h.id)

    # Hermanos por relación directa
    for r in persona.relaciones_origen:
        if r.tipo_relacion in ("hermano", "hermana"):
            hermanos_ids.add(r.persona_destino_id)
    for r in persona.relaciones_destino:
        if r.tipo_relacion in ("hermano", "hermana"):
            hermanos_ids.add(r.persona_origen_id)

    # 2. Para cada hermano, encontrar sus hijos
    for hermano_id in hermanos_ids:
        hermano = db.query(Persona).filter(Persona.id == hermano_id).first()
        if not hermano or not hermano.activo:
            continue

        sobrinos = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_destino_id)
            .filter(
                Relacion.persona_origen_id == hermano_id,
                Relacion.tipo_relacion.in_(["padre", "madre"]),
                Persona.activo == True,
            )
            .all()
        )

        for sobrino in sobrinos:
            rel_sobrino = (
                db.query(Relacion)
                .filter(
                    Relacion.persona_origen_id == hermano_id,
                    Relacion.persona_destino_id == sobrino.id,
                )
                .first()
            )
            tipo_rel = rel_sobrino.tipo_relacion if rel_sobrino else "padre"

            parentesco = "sobrino" if tipo_rel == "padre" else "sobrina"

            camino = (
                f"{_nombre(sobrino)} es hijo/a de {_nombre(hermano)}, "
                f"quien es hermano/a de {_nombre(persona)}."
            )

            resultados.append({
                "tipo_parentesco": parentesco,
                "persona": sobrino,
                "camino": camino,
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# CUÑADO / CUÑADA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_cunados(db: Session, persona: Persona) -> List[dict]:
    """
    Cuñado/a: dos caminos posibles:
      A) Cónyuge de un hermano/a.
      B) Hermano/a del cónyuge.

    Se buscan ambos caminos y se unifican los resultados.
    """
    resultados = []
    visto_ids = set()

    # --- Camino A: cónyuge del hermano/a ---
    hermanos_ids = set()

    # Hermanos por sangre
    padres_ids = [
        r.persona_origen_id
        for r in persona.relaciones_destino
        if r.tipo_relacion in ("padre", "madre")
    ]
    if padres_ids:
        hs = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_destino_id)
            .filter(
                Relacion.persona_origen_id.in_(padres_ids),
                Relacion.tipo_relacion.in_(["padre", "madre"]),
                Persona.id != persona.id,
            )
            .distinct()
            .all()
        )
        for h in hs:
            hermanos_ids.add(h.id)

    # Hermanos por relación directa
    for r in persona.relaciones_origen:
        if r.tipo_relacion in ("hermano", "hermana"):
            hermanos_ids.add(r.persona_destino_id)
    for r in persona.relaciones_destino:
        if r.tipo_relacion in ("hermano", "hermana"):
            hermanos_ids.add(r.persona_origen_id)

    for hermano_id in hermanos_ids:
        hermano = db.query(Persona).filter(Persona.id == hermano_id).first()
        if not hermano or not hermano.activo:
            continue

        # Cónyuges del hermano
        conyuges = _obtener_conyuges(db, hermano.id)
        for c in conyuges:
            if c.id == persona.id or c.id in visto_ids:
                continue
            visto_ids.add(c.id)
            camino = (
                f"{_nombre(c)} es cónyuge de {_nombre(hermano)}, "
                f"quien es hermano/a de {_nombre(persona)}."
            )
            resultados.append({
                "tipo_parentesco": "cuñado",
                "persona": c,
                "camino": camino,
            })

    # --- Camino B: hermano/a del cónyuge ---
    conyuges_persona = _obtener_conyuges(db, persona.id)
    for conyuge in conyuges_persona:
        # Hermanos del cónyuge
        conyuge_padres_ids = [
            r.persona_origen_id
            for r in (
                db.query(Relacion)
                .filter(
                    Relacion.persona_destino_id == conyuge.id,
                    Relacion.tipo_relacion.in_(["padre", "madre"]),
                )
                .all()
            )
        ]
        if conyuge_padres_ids:
            hermanos_conyuge = (
                db.query(Persona)
                .join(Relacion, Persona.id == Relacion.persona_destino_id)
                .filter(
                    Relacion.persona_origen_id.in_(conyuge_padres_ids),
                    Relacion.tipo_relacion.in_(["padre", "madre"]),
                    Persona.id != conyuge.id,
                    Persona.activo == True,
                )
                .distinct()
                .all()
            )
            for hc in hermanos_conyuge:
                if hc.id == persona.id or hc.id in visto_ids:
                    continue
                visto_ids.add(hc.id)
                camino = (
                    f"{_nombre(hc)} es hermano/a de {_nombre(conyuge)}, "
                    f"quien es cónyuge de {_nombre(persona)}."
                )
                resultados.append({
                    "tipo_parentesco": "cuñado",
                    "persona": hc,
                    "camino": camino,
                })

        # También considerar hermanos por relación directa del cónyuge
        for r in conyuge.relaciones_origen:
            if r.tipo_relacion in ("hermano", "hermana"):
                hc = r.destino
                if hc.id == persona.id or hc.id in visto_ids:
                    continue
                visto_ids.add(hc.id)
                camino = (
                    f"{_nombre(hc)} es hermano/a de {_nombre(conyuge)}, "
                    f"quien es cónyuge de {_nombre(persona)}."
                )
                resultados.append({
                    "tipo_parentesco": "cuñado",
                    "persona": hc,
                    "camino": camino,
                })
        for r in conyuge.relaciones_destino:
            if r.tipo_relacion in ("hermano", "hermana"):
                hc = r.origen
                if hc.id == persona.id or hc.id in visto_ids:
                    continue
                visto_ids.add(hc.id)
                camino = (
                    f"{_nombre(hc)} es hermano/a de {_nombre(conyuge)}, "
                    f"quien es cónyuge de {_nombre(persona)}."
                )
                resultados.append({
                    "tipo_parentesco": "cuñado",
                    "persona": hc,
                    "camino": camino,
                })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# SUEGRO / SUEGRA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_suegros(db: Session, persona: Persona) -> List[dict]:
    """
    Suegro/a: padre o madre del cónyuge.

    Camino: encontrar cónyuge, luego subir a sus padres.
    """
    resultados = []

    conyuges = _obtener_conyuges(db, persona.id)

    for conyuge in conyuges:
        suegros = (
            db.query(Persona)
            .join(Relacion, Persona.id == Relacion.persona_origen_id)
            .filter(
                Relacion.persona_destino_id == conyuge.id,
                Relacion.tipo_relacion.in_(["padre", "madre"]),
            )
            .all()
        )

        for suegro in suegros:
            rel_suegro = (
                db.query(Relacion)
                .filter(
                    Relacion.persona_origen_id == suegro.id,
                    Relacion.persona_destino_id == conyuge.id,
                )
                .first()
            )
            tipo = rel_suegro.tipo_relacion if rel_suegro else "padre"
            parentesco = "suegro" if tipo == "padre" else "suegra"

            camino = (
                f"{_nombre(suegro)} es {tipo} de {_nombre(conyuge)}, "
                f"quien es cónyuge de {_nombre(persona)}."
            )

            resultados.append({
                "tipo_parentesco": parentesco,
                "persona": suegro,
                "camino": camino,
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# YERNO / NUERA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_yernos_nueras(db: Session, persona: Persona) -> List[dict]:
    """
    Yerno/nuera: cónyuge de un hijo o hija.

    Camino: encontrar hijos, luego sus cónyuges.
    """
    resultados = []

    hijos = (
        db.query(Persona)
        .join(Relacion, Persona.id == Relacion.persona_destino_id)
        .filter(
            Relacion.persona_origen_id == persona.id,
            Relacion.tipo_relacion.in_(["padre", "madre"]),
            Persona.activo == True,
        )
        .all()
    )

    for hijo in hijos:
        conyuges = _obtener_conyuges(db, hijo.id)
        for c in conyuges:
            if c.id == persona.id:
                continue
            camino = (
                f"{_nombre(c)} es cónyuge de {_nombre(hijo)}, "
                f"quien es hijo/a de {_nombre(persona)}."
            )
            resultados.append({
                "tipo_parentesco": "yerno/nuera",
                "persona": c,
                "camino": camino,
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _obtener_conyuges(db: Session, persona_id: int) -> List[Persona]:
    """
    Retorna todas las personas que son cónyuges de la persona dada.
    La relación 'conyuge' es simétrica: si A es cónyuge de B, B lo es de A.
    """
    conyuges = []

    # Como origen
    for r in (
        db.query(Relacion)
        .filter(
            Relacion.persona_origen_id == persona_id,
            Relacion.tipo_relacion == "conyuge",
        )
        .all()
    ):
        p = db.query(Persona).filter(Persona.id == r.persona_destino_id).first()
        if p and p.activo:
            conyuges.append(p)

    # Como destino
    for r in (
        db.query(Relacion)
        .filter(
            Relacion.persona_destino_id == persona_id,
            Relacion.tipo_relacion == "conyuge",
        )
        .all()
    ):
        p = db.query(Persona).filter(Persona.id == r.persona_origen_id).first()
        if p and p.activo:
            conyuges.append(p)

    return conyuges


# ═══════════════════════════════════════════════════════════════════════════════
# INFERENCIA COMPLETA
# ═══════════════════════════════════════════════════════════════════════════════

def inferir_todos_parentescos(db: Session, persona: Persona) -> List[dict]:
    """
    Ejecuta todas las inferencias de parentesco para una persona
    y retorna una lista combinada de resultados.

    Cada elemento del resultado es un dict con:
      - tipo_parentesco: str (abuelo, nieto, hermano, tío, sobrino, cuñado, suegro, yerno/nuera)
      - persona: objeto Persona
      - camino: str (explicación textual)
    """
    todos = []
    todos.extend(inferir_abuelos(db, persona))
    todos.extend(inferir_nietos(db, persona))
    todos.extend(inferir_hermanos(db, persona))
    todos.extend(inferir_tios(db, persona))
    todos.extend(inferir_sobrinos(db, persona))
    todos.extend(inferir_cunados(db, persona))
    todos.extend(inferir_suegros(db, persona))
    todos.extend(inferir_yernos_nueras(db, persona))
    return todos


def inferir_parentesco_especifico(
    db: Session, persona: Persona, tipo: str
) -> List[dict]:
    """
    Infiere un tipo específico de parentesco.
    'tipo' puede ser: abuelo, abuela, nieto, nieta, hermano, hermana,
                       tio, tia, sobrino, sobrina, cunado, cunada,
                       suegro, suegra, yerno, nuera.
    """
    tipo_lower = tipo.lower().strip()

    if tipo_lower in ("abuelo", "abuela"):
        resultados = inferir_abuelos(db, persona)
        if tipo_lower == "abuelo":
            return [r for r in resultados if r["tipo_parentesco"] == "abuelo"]
        else:
            return [r for r in resultados if r["tipo_parentesco"] == "abuela"]

    elif tipo_lower in ("nieto", "nieta"):
        resultados = inferir_nietos(db, persona)
        if tipo_lower == "nieto":
            return [r for r in resultados if r["tipo_parentesco"] == "nieto"]
        else:
            return [r for r in resultados if r["tipo_parentesco"] == "nieta"]

    elif tipo_lower in ("hermano", "hermana"):
        return inferir_hermanos(db, persona)

    elif tipo_lower in ("tio", "tia"):
        return inferir_tios(db, persona)

    elif tipo_lower in ("sobrino", "sobrina"):
        resultados = inferir_sobrinos(db, persona)
        if tipo_lower == "sobrino":
            return [r for r in resultados if r["tipo_parentesco"] == "sobrino"]
        else:
            return [r for r in resultados if r["tipo_parentesco"] == "sobrina"]

    elif tipo_lower in ("cunado", "cunada", "cuñado", "cuñada"):
        return inferir_cunados(db, persona)

    elif tipo_lower in ("suegro", "suegra"):
        resultados = inferir_suegros(db, persona)
        if tipo_lower == "suegro":
            return [r for r in resultados if r["tipo_parentesco"] == "suegro"]
        else:
            return [r for r in resultados if r["tipo_parentesco"] == "suegra"]

    elif tipo_lower in ("yerno", "nuera"):
        return inferir_yernos_nueras(db, persona)

    else:
        return []
