"""
database.py — Conexión a PostgreSQL usando SQLAlchemy 2.0 + psycopg2 (síncrono).

La URL de conexión se toma de la variable de entorno DATABASE_URL.
Neon (PostgreSQL serverless) requiere SSL, por lo que
SQLAlchemy se configura con connect_args={"sslmode": "require"}.

Las migraciones se ejecutan via scripts/migrate.py, NO en producción.
"""

import os
from sqlalchemy import create_engine
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
    pool_recycle=300,
    pool_use_lifo=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
