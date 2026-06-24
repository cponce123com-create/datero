"""
backend/tests/test_parentesco.py — Tests unitarios del motor de parentescos.

Cubre:
  - Persona sin familiares
  - Familiares directos (padres, hijos)
  - Familiares lejanos (abuelos, tios, primos)
  - Ciclos (A es padre de B, B es padre de A)
  - Auto-relaciones
  - Cache invalidation
  - Contradicciones (dos madres)
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Persona, Relacion
from parentesco import calcular_parentesco, invalidar_cache_parentesco


@pytest.fixture(scope="function")
def db():
    """Crea BD en memoria para cada test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


def _crear_persona(db, dni, nombres, apellido, genero=None):
    p = Persona(dni=dni, nombres=nombres, apellido_paterno=apellido, genero=genero)
    db.add(p)
    db.flush()
    return p


def _crear_relacion(db, origen, destino, tipo):
    r = Relacion(persona_origen_id=origen.id, persona_destino_id=destino.id,
                 tipo_relacion=tipo, certeza="confirmado")
    db.add(r)
    db.flush()
    return r


class TestParentescoBasico:
    """Casos base: persona sola, padres, hijos."""

    def test_persona_sin_familiares(self, db):
        p = _crear_persona(db, "00000001", "SOLA", "PERSONA", "MASCULINO")
        db.commit()
        invalidar_cache_parentesco()
        res = calcular_parentesco(db, "00000001")
        assert res == [], f"Persona sola deberia tener 0 parientes, obtuvo {len(res)}"

    def test_padres_directos(self, db):
        hijo = _crear_persona(db, "00000002", "HIJO", "PRUEBA", "MASCULINO")
        padre = _crear_persona(db, "00000003", "PADRE", "PRUEBA", "MASCULINO")
        madre = _crear_persona(db, "00000004", "MADRE", "PRUEBA", "FEMENINO")
        _crear_relacion(db, padre, hijo, "padre")
        _crear_relacion(db, madre, hijo, "madre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "00000002")
        tipos = {r["tipo_parentesco"] for r in res}
        assert "padre" in tipos, "Deberia encontrar padre"
        assert "madre" in tipos, "Deberia encontrar madre"

    def test_hijos(self, db):
        padre = _crear_persona(db, "00000005", "PADRE", "PRUEBA", "MASCULINO")
        hijo1 = _crear_persona(db, "00000006", "HIJO1", "PRUEBA", "MASCULINO")
        hijo2 = _crear_persona(db, "00000007", "HIJO2", "PRUEBA", "FEMENINO")
        _crear_relacion(db, padre, hijo1, "padre")
        _crear_relacion(db, padre, hijo2, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "00000005")
        tipos = {r["tipo_parentesco"] for r in res}
        assert "hijo" in tipos or "hija" in tipos, "Deberia encontrar hijos"


class TestParentescoAvanzado:
    """Abuelos, tios, primos, hermanos."""

    def test_abuelos(self, db):
        abuelo = _crear_persona(db, "A001", "ABUELO", "TEST", "MASCULINO")
        padre = _crear_persona(db, "A002", "PADRE", "TEST", "MASCULINO")
        hijo = _crear_persona(db, "A003", "HIJO", "TEST", "MASCULINO")
        _crear_relacion(db, abuelo, padre, "padre")
        _crear_relacion(db, padre, hijo, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "A003")
        abuelos = [r for r in res if r["tipo_parentesco"] == "abuelo"]
        assert len(abuelos) == 1, f"Deberia encontrar 1 abuelo, encontro {len(abuelos)}"
        assert abuelos[0]["dni"] == "A001"

    def test_hermanos(self, db):
        padre = _crear_persona(db, "B001", "PADRE", "TEST", "MASCULINO")
        h1 = _crear_persona(db, "B002", "HIJO1", "TEST", "MASCULINO")
        h2 = _crear_persona(db, "B003", "HIJO2", "TEST", "MASCULINO")
        _crear_relacion(db, padre, h1, "padre")
        _crear_relacion(db, padre, h2, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "B002")
        hermanos = [r for r in res if r["tipo_parentesco"] == "hermano"]
        assert len(hermanos) == 1
        assert hermanos[0]["dni"] == "B003"

    def test_tios(self, db):
        abuelo = _crear_persona(db, "C001", "ABUELO", "TEST", "MASCULINO")
        padre = _crear_persona(db, "C002", "PADRE", "TEST", "MASCULINO")
        tio = _crear_persona(db, "C003", "TIO", "TEST", "MASCULINO")
        hijo = _crear_persona(db, "C004", "HIJO", "TEST", "MASCULINO")
        _crear_relacion(db, abuelo, padre, "padre")
        _crear_relacion(db, abuelo, tio, "padre")
        _crear_relacion(db, padre, hijo, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "C004")
        tios = [r for r in res if r["tipo_parentesco"] == "tio"]
        assert len(tios) == 1
        assert tios[0]["dni"] == "C003"

    def test_primos(self, db):
        abuelo = _crear_persona(db, "D001", "ABUELO", "TEST", "MASCULINO")
        p1 = _crear_persona(db, "D002", "PADRE1", "TEST", "MASCULINO")
        p2 = _crear_persona(db, "D003", "PADRE2", "TEST", "MASCULINO")
        h1 = _crear_persona(db, "D004", "HIJO1", "TEST", "MASCULINO")
        h2 = _crear_persona(db, "D005", "HIJO2", "TEST", "MASCULINO")
        _crear_relacion(db, abuelo, p1, "padre")
        _crear_relacion(db, abuelo, p2, "padre")
        _crear_relacion(db, p1, h1, "padre")
        _crear_relacion(db, p2, h2, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "D004")
        primos = [r for r in res if r["tipo_parentesco"] in ("primo", "prima")]
        assert len(primos) == 1
        assert primos[0]["dni"] == "D005"


class TestRobustez:
    """Ciclos, auto-relaciones, duplicados."""

    def test_no_auto_relacion(self, db):
        """Una persona no puede ser su propio pariente."""
        p = _crear_persona(db, "E001", "PRUEBA", "CICLO", "MASCULINO")
        # Auto-relacion (no deberia existir, pero si aparece, ignorarla)
        _crear_relacion(db, p, p, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "E001")
        assert res == [], "No deberia encontrarse a si mismo"

    def test_ciclo_simple(self, db):
        """A es padre de B, B es padre de A → ciclo, no colgar."""
        a = _crear_persona(db, "F001", "PERSONA_A", "CICLO", "MASCULINO")
        b = _crear_persona(db, "F002", "PERSONA_B", "CICLO", "MASCULINO")
        _crear_relacion(db, a, b, "padre")
        _crear_relacion(db, b, a, "padre")
        db.commit()
        invalidar_cache_parentesco()

        # No debe colgar ni lanzar excepcion
        res_a = calcular_parentesco(db, "F001")
        res_b = calcular_parentesco(db, "F002")
        assert isinstance(res_a, list)
        assert isinstance(res_b, list)
        # Puede detectar el ciclo y retornar lo que tenga sentido
        print(f"Ciclo A→B: {len(res_a)} parientes")
        print(f"Ciclo B→A: {len(res_b)} parientes")

    def test_dos_madres(self, db):
        """Dos madres (contradiccion) no debe romper el algoritmo."""
        hijo = _crear_persona(db, "G001", "HIJO", "POLI", "MASCULINO")
        m1 = _crear_persona(db, "G002", "MADRE1", "POLI", "FEMENINO")
        m2 = _crear_persona(db, "G003", "MADRE2", "POLI", "FEMENINO")
        padre = _crear_persona(db, "G004", "PADRE", "POLI", "MASCULINO")
        _crear_relacion(db, m1, hijo, "madre")
        _crear_relacion(db, m2, hijo, "madre")
        _crear_relacion(db, padre, hijo, "padre")
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "G001")
        madres = [r for r in res if r["tipo_parentesco"] == "madre"]
        assert len(madres) == 2, f"Deberia encontrar 2 madres, encontro {len(madres)}"

    def test_relacion_duplicada(self, db):
        """Relacion duplicada no debe duplicar resultados."""
        hijo = _crear_persona(db, "H001", "HIJO", "DUP", "MASCULINO")
        padre = _crear_persona(db, "H002", "PADRE", "DUP", "MASCULINO")
        _crear_relacion(db, padre, hijo, "padre")
        _crear_relacion(db, padre, hijo, "padre")  # Duplicado
        db.commit()
        invalidar_cache_parentesco()

        res = calcular_parentesco(db, "H001")
        padres = [r for r in res if r["tipo_parentesco"] == "padre"]
        assert len(padres) == 1, f"Padre duplicado, encontro {len(padres)}"


class TestCache:
    """Invalidacion de cache."""

    def test_cache_invalidation(self, db):
        p = _crear_persona(db, "I001", "PRUEBA", "CACHE", "MASCULINO")
        db.commit()
        invalidar_cache_parentesco()

        res1 = calcular_parentesco(db, "I001")
        assert res1 == []

        # Agregar padre sin invalidar cache
        padre = _crear_persona(db, "I002", "PADRE", "CACHE", "MASCULINO")
        _crear_relacion(db, padre, p, "padre")
        db.commit()

        # Cache aun no invalidado → resultado viejo
        res2 = calcular_parentesco(db, "I001")
        # Podria ser [] si cache no se invalido
        print(f"Cache sin invalidar: {len(res2)} parientes")

        # Invalidar
        invalidar_cache_parentesco()
        res3 = calcular_parentesco(db, "I001")
        padres = [r for r in res3 if r["tipo_parentesco"] == "padre"]
        assert len(padres) == 1, "Cache deberia reflejar nuevo padre"
