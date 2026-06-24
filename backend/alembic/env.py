"""
alembic/env.py — Entorno Alembic para migraciones de RedCorruptela.

Uso:
  cd backend
  alembic upgrade head    # Aplica todas las migraciones pendientes
  alembic revision --autogenerate -m "descripcion"  # Crea nueva migracion

Configuracion:
  - La URL de BD se toma de DATABASE_URL (variable de entorno)
  - Los modelos se importan desde models.py para autogenerate
"""

from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# Agregar backend/ al path para importar modelos
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base
from models import Persona, Relacion, Etiqueta, PersonaEtiqueta
from models import Empresa, PersonaEmpresa, EmpresaEtiqueta
from models import Usuario, Auditoria

# Alembic Config object
config = context.config

# Usar DATABASE_URL del entorno si existe (sobrescribe alembic.ini)
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Configurar logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata objetivo para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (direct DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
