"""
alembic/versions/001_crear_tablas_iniciales.py

Migracion inicial: crea todas las tablas del sistema.

Generado manualmente para tener control total sobre
tipos de datos, indices y constraints.

Ejecutar:
  cd backend && alembic upgrade head
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_crear_tablas_iniciales"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extension pg_trgm para busqueda por similitud ────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── Tabla: personas ──────────────────────────────────────────────
    op.create_table(
        "personas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dni", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("nombres", sa.String(200), nullable=False),
        sa.Column("apellido_paterno", sa.String(100), nullable=False),
        sa.Column("apellido_materno", sa.String(100), nullable=True),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("foto_url", sa.Text(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), default=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    # Indices GIN para busqueda textual con pg_trgm
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_personas_nombre_trgm "
        "ON personas USING GIN (nombres gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_personas_apellido_paterno_trgm "
        "ON personas USING GIN (apellido_paterno gin_trgm_ops)"
    )

    # ── Tabla: relaciones ────────────────────────────────────────────
    op.create_table(
        "relaciones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("persona_origen_id", sa.Integer(),
                  sa.ForeignKey("personas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("persona_destino_id", sa.Integer(),
                  sa.ForeignKey("personas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("tipo_relacion", sa.String(20), nullable=False),
        sa.Column("certeza", sa.String(20), default="confirmado"),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("persona_origen_id", "persona_destino_id",
                            "tipo_relacion",
                            name="uq_relacion_origen_destino_tipo"),
    )
    # Indices compuestos para CTE de parentesco
    op.create_index("idx_relaciones_origen_destino", "relaciones",
                    ["persona_origen_id", "persona_destino_id"])
    op.create_index("idx_relaciones_destino_origen", "relaciones",
                    ["persona_destino_id", "persona_origen_id"])

    # ── Tabla: etiquetas ─────────────────────────────────────────────
    op.create_table(
        "etiquetas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(100), unique=True, nullable=False),
    )

    # ── Tabla: persona_etiqueta ──────────────────────────────────────
    op.create_table(
        "persona_etiqueta",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("persona_id", sa.Integer(),
                  sa.ForeignKey("personas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("etiqueta_id", sa.Integer(),
                  sa.ForeignKey("etiquetas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("fecha_asignacion", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("persona_id", "etiqueta_id",
                            name="uq_persona_etiqueta"),
    )

    # ── Tabla: empresas ──────────────────────────────────────────────
    op.create_table(
        "empresas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ruc", sa.String(11), unique=True, nullable=False,
                  index=True),
        sa.Column("nombre", sa.String(300), nullable=False),

        # Datos SUNAT
        sa.Column("direccion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(50), nullable=True),
        sa.Column("condicion", sa.String(50), nullable=True),
        sa.Column("tipo_contribuyente", sa.String(100), nullable=True),
        sa.Column("nombre_comercial", sa.String(300), nullable=True),
        sa.Column("fecha_inscripcion", sa.String(20), nullable=True),
        sa.Column("fecha_inicio_actividades", sa.String(20), nullable=True),
        sa.Column("sistema_contabilidad", sa.String(100), nullable=True),
        sa.Column("actividad_comercio_exterior", sa.String(100), nullable=True),
        sa.Column("actividad_economica", sa.String(300), nullable=True),
        sa.Column("comprobantes_autorizados", sa.String(300), nullable=True),
        sa.Column("sistema_emision", sa.String(100), nullable=True),
        sa.Column("afiliado_ple", sa.String(5), nullable=True),

        # Datos SUNAT extendidos
        sa.Column("sistema_emision_electronica", sa.Text(), nullable=True),
        sa.Column("emisor_electronico_desde", sa.String(20), nullable=True),
        sa.Column("comprobantes_electronicos", sa.Text(), nullable=True),
        sa.Column("padrones", sa.Text(), nullable=True),
        sa.Column("establecimientos", sa.Text(), nullable=True),

        # Representante legal
        sa.Column("representante_legal_dni", sa.String(20),
                  nullable=True, index=True),
        sa.Column("representante_legal_nombre", sa.String(300), nullable=True),

        # Metadatos
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), default=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    # Indice pg_trgm para busqueda de empresas por nombre
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_empresas_nombre_trgm "
        "ON empresas USING GIN (nombre gin_trgm_ops)"
    )

    # ── Tabla: persona_empresa ───────────────────────────────────────
    op.create_table(
        "persona_empresa",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("persona_id", sa.Integer(),
                  sa.ForeignKey("personas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("empresa_id", sa.Integer(),
                  sa.ForeignKey("empresas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("cargo", sa.String(200), nullable=True),
        sa.Column("fecha_desde", sa.Date(), nullable=True),
        sa.Column("fecha_hasta", sa.Date(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.UniqueConstraint("persona_id", "empresa_id", "cargo",
                            name="uq_persona_empresa_cargo"),
    )

    # ── Tabla: empresa_etiqueta ──────────────────────────────────────
    op.create_table(
        "empresa_etiqueta",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Integer(),
                  sa.ForeignKey("empresas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("etiqueta_id", sa.Integer(),
                  sa.ForeignKey("etiquetas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("fecha_asignacion", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("empresa_id", "etiqueta_id",
                            name="uq_empresa_etiqueta"),
    )

    # ── Tabla: usuarios ──────────────────────────────────────────────
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(80), unique=True,
                  nullable=False, index=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False, default="lector"),
        sa.Column("activo", sa.Boolean(), default=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── Tabla: auditoria ─────────────────────────────────────────────
    op.create_table(
        "auditoria",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("usuario_username", sa.String(80), nullable=True),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("entidad", sa.String(50), nullable=False),
        sa.Column("entidad_id", sa.String(50), nullable=True),
        sa.Column("detalle", postgresql.JSONB(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Elimina todas las tablas en orden inverso."""
    op.drop_table("auditoria")
    op.drop_table("usuario")
    op.drop_table("empresa_etiqueta")
    op.drop_table("persona_empresa")
    op.drop_table("empresas")
    op.drop_table("persona_etiqueta")
    op.drop_table("etiquetas")
    op.drop_table("relaciones")
    op.drop_table("personas")
