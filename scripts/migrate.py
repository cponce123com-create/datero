"""
migrate.py — Script de migraciones para RedCorruptela.

Ejecuta:
1. Creación de tablas (Base.metadata.create_all)
2. Migraciones de datos idempotentes

Uso:
    cd backend && python ../scripts/migrate.py

Requiere DATABASE_URL en el entorno o archivo .env.
"""

import os
import sys

# Cargar .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

# Añadir el directorio backend al path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from models import Base


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL no está definida")
    sys.exit(1)

print(f"Conectando a: {DATABASE_URL[:50]}...")

engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"} if "neon" in DATABASE_URL or "ssl" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def step_create_tables():
    """Paso 1: Crear tablas si no existen."""
    print("[1/4] Creando tablas...")
    Base.metadata.create_all(bind=engine)
    print("  ✓ Tablas creadas/verificadas")


def step_remove_duplicates():
    """Paso 2: Eliminar duplicados en persona_etiqueta."""
    print("[2/4] Eliminando duplicados en persona_etiqueta...")
    conn = engine.connect()
    try:
        conn.execute(text("""
            DELETE FROM persona_etiqueta pe1 USING persona_etiqueta pe2
            WHERE pe1.id < pe2.id
              AND pe1.persona_id = pe2.persona_id
              AND pe1.etiqueta_id = pe2.etiqueta_id
        """))
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_persona_etiqueta'
                ) THEN
                    ALTER TABLE persona_etiqueta
                    ADD CONSTRAINT uq_persona_etiqueta
                    UNIQUE (persona_id, etiqueta_id);
                END IF;
            END $$;
        """))
        conn.commit()
        print("  ✓ Duplicados eliminados y constraints agregados")
    except Exception as e:
        conn.rollback()
        print(f"  ⚠ Advertencia: {e}")
    finally:
        conn.close()


def step_migrate_persona_trabajo():
    """Paso 3: Migrar PersonaTrabajo → Empresas + PersonaEmpresa."""
    print("[3/4] Migrando PersonaTrabajo a Empresas...")
    conn = engine.connect()
    try:
        result = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'persona_trabajo')"
        ))
        tabla_existe = result.scalar()

        if tabla_existe:
            result = conn.execute(text("SELECT COUNT(*) FROM persona_trabajo"))
            count = result.scalar()

            if count and count > 0:
                print(f"  → {count} registros encontrados en persona_trabajo")

                conn.execute(text("""
                    INSERT INTO empresas (ruc, nombre, activo)
                    SELECT
                        'PEND-' || row_number() OVER (ORDER BY empresa_nombre),
                        empresa_nombre,
                        true
                    FROM (
                        SELECT DISTINCT empresa_nombre
                        FROM persona_trabajo
                        WHERE empresa_nombre IS NOT NULL AND empresa_nombre != ''
                    ) sub
                    ON CONFLICT DO NOTHING
                """))

                conn.execute(text("""
                    INSERT INTO persona_empresa (persona_id, empresa_id, cargo, observacion)
                    SELECT
                        pt.persona_id,
                        e.id,
                        'trabajador',
                        'Migrado de PersonaTrabajo'
                    FROM persona_trabajo pt
                    JOIN empresas e ON e.nombre = pt.empresa_nombre
                    ON CONFLICT (persona_id, empresa_id, cargo) DO NOTHING
                """))

                conn.commit()
                print(f"  ✓ Migración completada")
            else:
                print("  → Sin datos en persona_trabajo")

            conn.execute(text("DROP TABLE IF EXISTS persona_trabajo"))
            conn.commit()
            print("  ✓ Tabla persona_trabajo eliminada")
        else:
            print("  → Tabla persona_trabajo no existe, saltando")
    except Exception as e:
        conn.rollback()
        print(f"  ⚠ Advertencia: {e}")
    finally:
        conn.close()


def step_add_empresa_columns():
    """Paso 4: Agregar columnas SUNAT a tabla empresas."""
    print("[4/5] Agregando columnas SUNAT a empresas...")
    conn = engine.connect()
    try:
        from sqlalchemy import text as sa_text
        columnas = [
            ("estado", "VARCHAR(50)"),
            ("condicion", "VARCHAR(50)"),
            ("tipo_contribuyente", "VARCHAR(100)"),
            ("nombre_comercial", "VARCHAR(300)"),
            ("fecha_inscripcion", "VARCHAR(20)"),
            ("fecha_inicio_actividades", "VARCHAR(20)"),
            ("sistema_contabilidad", "VARCHAR(100)"),
            ("actividad_comercio_exterior", "VARCHAR(100)"),
            ("actividad_economica", "VARCHAR(300)"),
            ("comprobantes_autorizados", "VARCHAR(300)"),
            ("sistema_emision", "VARCHAR(100)"),
            ("afiliado_ple", "VARCHAR(5)"),
            ("representante_legal_dni", "VARCHAR(20)"),
            ("representante_legal_nombre", "VARCHAR(300)"),
            ("sistema_emision_electronica", "TEXT"),
            ("emisor_electronico_desde", "VARCHAR(20)"),
            ("comprobantes_electronicos", "TEXT"),
            ("padrones", "TEXT"),
            ("establecimientos", "TEXT"),
            ("actualizado_en", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ]
        for col_name, col_type in columnas:
            try:
                conn.execute(sa_text(
                    f"ALTER TABLE empresas ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                print(f"  ✓ Columna '{col_name}' agregada/verificada")
            except Exception as e:
                print(f"  ⚠ Columna '{col_name}': {e}")
        conn.commit()
        # Indice para representante legal
        try:
            conn.execute(sa_text(
                "CREATE INDEX IF NOT EXISTS idx_empresas_rep_legal_dni "
                "ON empresas (representante_legal_dni)"
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
        print("  ✓ Columnas SUNAT agregadas exitosamente")
    except Exception as e:
        conn.rollback()
        print(f"  ⚠ Error: {e}")
    finally:
        conn.close()


def step_create_indexes():
    """Paso 5: Crear índices de búsqueda textual (opcional, requiere pg_trgm)."""
    print("[5/5] Creando índices de búsqueda...")
    conn = engine.connect()
    try:
        # Intentar crear extensión pg_trgm (puede fallar si no hay permisos)
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.commit()
        except Exception:
            conn.rollback()
            print("  ⚠ pg_trgm no disponible, índices GIN no creados (búsqueda seguirá funcionando con ILIKE)")
            return

        # Índice para búsqueda en nombres de personas
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_personas_nombre_trgm
            ON personas USING GIN (nombres gin_trgm_ops)
        """))
        # Índice para búsqueda en apellido paterno
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_personas_apellido_paterno_trgm
            ON personas USING GIN (apellido_paterno gin_trgm_ops)
        """))
        # Índice para búsqueda en nombre de empresas
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_empresas_nombre_trgm
            ON empresas USING GIN (nombre gin_trgm_ops)
        """))
        conn.commit()
        print("  ✓ Índices GIN con pg_trgm creados")
    except Exception as e:
        conn.rollback()
        print(f"  ⚠ Advertencia al crear índices: {e}")
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("  RedCorruptela — Migraciones")
    print("=" * 60)
    print()

    step_create_tables()
    print()
    step_remove_duplicates()
    print()
    step_migrate_persona_trabajo()
    print()
    step_add_empresa_columns()
    print()
    step_create_indexes()
    print()
    print("✅ Migraciones completadas exitosamente")


if __name__ == "__main__":
    main()
