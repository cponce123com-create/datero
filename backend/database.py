"""
database.py — Conexión a PostgreSQL usando SQLAlchemy 2.0 + psycopg2 (síncrono).

La URL de conexión se toma de la variable de entorno DATABASE_URL.
Neon (el servicio de PostgreSQL serverless) requiere SSL, por lo que
SQLAlchemy se configura con connect_args={"sslmode": "require"}.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# La URL de conexión debe tener el formato:
# postgresql://usuario:contraseña@host:5432/nombre_db?sslmode=require
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/redcorruptela"
)

# Configuramos el engine con soporte SSL (obligatorio para Neon)
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"} if "neon" in DATABASE_URL or "ssl" in DATABASE_URL else {},
    pool_size=3,
    max_overflow=5,
    pool_pre_ping=True,       # Verifica que la conexión esté viva antes de usarla
    pool_recycle=30,           # Recicla conexiones cada 30 segundos
    pool_use_lifo=True,        # Reusa la última conexión (reduce conexiones muertas)
)

# Fábrica de sesiones: cada petición obtiene su propia sesión de BD
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para los modelos ORM
Base = declarative_base()


def get_db():
    """
    Dependencia de FastAPI que proporciona una sesión de base de datos
    por petición y la cierra automáticamente al terminar.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Crea todas las tablas definidas en los modelos si no existen.
    Se llama al iniciar la aplicación.
    """
    Base.metadata.create_all(bind=engine)

    # Migración: agregar UniqueConstraint en persona_etiqueta si no existe
    try:
        from sqlalchemy import text
        conn = engine.connect()
        # Eliminar duplicados existentes (conservar el primero)
        conn.execute(text("""
            DELETE FROM persona_etiqueta pe1 USING persona_etiqueta pe2
            WHERE pe1.id < pe2.id
              AND pe1.persona_id = pe2.persona_id
              AND pe1.etiqueta_id = pe2.etiqueta_id
        """))
        # Agregar constraint si no existe
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
        pass  # La tabla puede no existir aún en el primer deploy
