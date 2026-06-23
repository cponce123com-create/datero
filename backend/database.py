"""
database.py — Conexión a PostgreSQL usando SQLAlchemy 2.0 + psycopg2 (síncrono).

La URL de conexión se toma de la variable de entorno DATABASE_URL.
Neon (el servicio de PostgreSQL serverless) requiere SSL, por lo que
SQLAlchemy se configura con connect_args={"sslmode": "require"}.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/redcorruptela"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"} if "neon" in DATABASE_URL or "ssl" in DATABASE_URL else {},
    pool_size=3,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=30,
    pool_use_lifo=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crea tablas y ejecuta migraciones."""
    Base.metadata.create_all(bind=engine)

    # UniqueConstraint para persona_etiqueta
    try:
        conn = engine.connect()
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
        conn.close()
    except Exception:
        pass

    # ── Migración: PersonaTrabajo -> Empresa + PersonaEmpresa ──
    try:
        conn = engine.connect()

        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'persona_trabajo'
            )
        """))
        tabla_existe = result.scalar()

        if tabla_existe:
            result = conn.execute(text("SELECT COUNT(*) FROM persona_trabajo"))
            count = result.scalar()

            if count and count > 0:
                print(f"[Migracion] {count} registros en persona_trabajo -> empresas + persona_empresa")

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

            try:
                conn.execute(text("DROP TABLE IF EXISTS persona_trabajo"))
                conn.commit()
            except Exception as e:
                conn.rollback()

        conn.close()
    except Exception as e:
        print(f"[Migracion] Error: {e}")
        try:
            conn.close()
        except Exception:
            pass
