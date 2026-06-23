"""
models.py — Modelos SQLAlchemy para la base de datos de RedCorruptela.

Define tablas principales:
  - personas: datos biográficos de cada individuo (DNI único).
  - relaciones: vínculo dirigido entre dos personas.
  - etiquetas: categorías para marcar a personas o empresas.
  - persona_etiqueta: tabla pivote etiqueta-persona.
  - empresas: personas jurídicas (RUC único).
  - persona_empresa: vínculo persona ↔ empresa con cargo.
  - empresa_etiqueta: tabla pivote etiqueta-empresa.
  - usuarios: cuentas de acceso (admin/lector).
  - auditoria: registro de cambios.
"""

from sqlalchemy import (
    Column, Integer, String, Date, Boolean, ForeignKey,
    Text, DateTime, UniqueConstraint, JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Persona(Base):
    """
    Representa a una persona física identificada por su DNI.
    El campo 'activo' permite baja lógica (no se borra realmente).

    Índices recomendados (aplicar via scripts/migrate.py con pg_trgm):
      CREATE INDEX IF NOT EXISTS idx_personas_nombre_trgm
          ON personas USING GIN (nombres gin_trgm_ops);
      CREATE INDEX IF NOT EXISTS idx_personas_apellido_paterno_trgm
          ON personas USING GIN (apellido_paterno gin_trgm_ops);
    """
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    dni = Column(String(20), unique=True, nullable=False, index=True,
                 comment="Documento Nacional de Identidad, único y obligatorio")
    nombres = Column(String(200), nullable=False)
    apellido_paterno = Column(String(100), nullable=False)
    apellido_materno = Column(String(100), nullable=True)
    fecha_nacimiento = Column(Date, nullable=True)
    foto_url = Column(Text, nullable=True,
                      comment="URL de Cloudinary (se integrará después)")
    notas = Column(Text, nullable=True,
                   comment="Notas libres del periodista")
    activo = Column(Boolean, default=True,
                    comment="False = baja lógica")
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones donde esta persona es el origen (A → B)
    relaciones_origen = relationship(
        "Relacion",
        foreign_keys="Relacion.persona_origen_id",
        back_populates="origen",
        lazy="selectin",
    )
    # Relaciones donde esta persona es el destino (B ← A)
    relaciones_destino = relationship(
        "Relacion",
        foreign_keys="Relacion.persona_destino_id",
        back_populates="destino",
        lazy="selectin",
    )
    # Etiquetas asignadas
    etiquetas_asignadas = relationship(
        "PersonaEtiqueta",
        back_populates="persona",
        lazy="selectin",
    )
    # Empresas vinculadas (reemplaza a PersonaTrabajo)
    empresas = relationship(
        "PersonaEmpresa",
        back_populates="persona",
        lazy="selectin",
    )

    @property
    def nombre_completo(self):
        """Retorna el nombre completo formateado."""
        partes = [self.nombres, self.apellido_paterno]
        if self.apellido_materno:
            partes.append(self.apellido_materno)
        return " ".join(partes)

    def __repr__(self):
        return f"<Persona(dni='{self.dni}', nombre='{self.nombre_completo}')>"


class Relacion(Base):
    """
    Vínculo dirigido entre dos personas.

    Tipos de relación (almacenados):
      - 'padre': persona_origen es padre de persona_destino
      - 'madre': persona_origen es madre de persona_destino
      - 'conyuge': relación simétrica (matrimonio, unión civil, etc.)
      - 'hermano': persona_origen es hermano de persona_destino
      - 'hermana': persona_origen es hermana de persona_destino

    Nota: 'hijo' e 'hija' no se almacenan; se infieren invirtiendo 'padre'/'madre'.

    Certeza: confirmado | rumor | documento
    """
    __tablename__ = "relaciones"

    id = Column(Integer, primary_key=True, index=True)
    persona_origen_id = Column(
        Integer, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    persona_destino_id = Column(
        Integer, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    tipo_relacion = Column(
        String(20), nullable=False,
        comment="padre | madre | conyuge | hermano | hermana"
    )
    certeza = Column(
        String(20), default="confirmado",
        comment="confirmado | rumor | documento"
    )
    notas = Column(Text, nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    origen = relationship(
        "Persona",
        foreign_keys=[persona_origen_id],
        back_populates="relaciones_origen",
    )
    destino = relationship(
        "Persona",
        foreign_keys=[persona_destino_id],
        back_populates="relaciones_destino",
    )

    # Evita duplicados exactos: misma persona A, misma persona B, mismo tipo
    __table_args__ = (
        UniqueConstraint(
            "persona_origen_id", "persona_destino_id", "tipo_relacion",
            name="uq_relacion_origen_destino_tipo",
        ),
    )

    def __repr__(self):
        return (
            f"<Relacion({self.origen_id} --{self.tipo_relacion}--> "
            f"{self.destino_id})>"
        )


class Etiqueta(Base):
    """
    Categoría o marcador que se puede asignar a personas o empresas.
    Ejemplos: "contratado 2024", "proveedor municipalidad",
              "familiar de alcalde", "investigación abierta".
    """
    __tablename__ = "etiquetas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"<Etiqueta(nombre='{self.nombre}')>"


class PersonaEtiqueta(Base):
    """
    Tabla pivote: asigna una etiqueta a una persona en una fecha,
    con una observación opcional (ej. "contrato del 15/03/2024").
    """
    __tablename__ = "persona_etiqueta"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(
        Integer, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    etiqueta_id = Column(
        Integer, ForeignKey("etiquetas.id", ondelete="CASCADE"), nullable=False
    )
    observacion = Column(Text, nullable=True)
    fecha_asignacion = Column(DateTime(timezone=True), server_default=func.now())

    persona = relationship("Persona", back_populates="etiquetas_asignadas")
    etiqueta = relationship("Etiqueta", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("persona_id", "etiqueta_id", name="uq_persona_etiqueta"),
    )

    def __repr__(self):
        return f"<PersonaEtiqueta(persona={self.persona_id}, etiqueta={self.etiqueta_id})>"


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRESAS
# ═══════════════════════════════════════════════════════════════════════════════

class Empresa(Base):
    """
    Persona jurídica identificada por su RUC.

    Los campos de SUNAT se llenan automaticamente via SunatScraper.
    El representante legal se cruza automaticamente con la tabla personas.

    Índices recomendados (aplicar via scripts/migrate.py con pg_trgm):
      CREATE INDEX IF NOT EXISTS idx_empresas_nombre_trgm
          ON empresas USING GIN (nombre gin_trgm_ops);
      CREATE INDEX IF NOT EXISTS idx_empresas_rep_legal_dni
          ON empresas (representante_legal_dni);
    """
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    ruc = Column(String(11), unique=True, nullable=False, index=True,
                 comment="Registro Único del Contribuyente, 11 dígitos")
    nombre = Column(String(300), nullable=False,
                    comment="Razón social")

    # ── Datos SUNAT ────────────────────────────────────────────────────
    direccion = Column(Text, nullable=True)
    estado = Column(String(50), nullable=True, comment="ACTIVO, BAJA, etc.")
    condicion = Column(String(50), nullable=True, comment="HABIDO, NO HABIDO")
    tipo_contribuyente = Column(String(100), nullable=True)
    nombre_comercial = Column(String(300), nullable=True)
    fecha_inscripcion = Column(String(20), nullable=True)
    fecha_inicio_actividades = Column(String(20), nullable=True)
    sistema_contabilidad = Column(String(100), nullable=True)
    actividad_comercio_exterior = Column(String(100), nullable=True)
    actividad_economica = Column(String(300), nullable=True)
    comprobantes_autorizados = Column(String(300), nullable=True)
    sistema_emision = Column(String(100), nullable=True)
    afiliado_ple = Column(String(5), nullable=True, comment="SI/NO")

    # ── Representante Legal ────────────────────────────────────────────
    representante_legal_dni = Column(
        String(20), nullable=True, index=True,
        comment="DNI del representante legal (para cruce automatico)"
    )
    representante_legal_nombre = Column(
        String(300), nullable=True,
        comment="Nombre del representante legal"
    )

    # ── Metadatos ──────────────────────────────────────────────────────
    notas = Column(Text, nullable=True)
    activo = Column(Boolean, default=True, comment="False = baja lógica")
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True),
                            server_default=func.now(), onupdate=func.now())

    # Relaciones
    personas_relacionadas = relationship(
        "PersonaEmpresa",
        back_populates="empresa",
        lazy="selectin",
    )
    etiquetas_asignadas = relationship(
        "EmpresaEtiqueta",
        back_populates="empresa",
        lazy="selectin",
    )

    @property
    def tiene_representante_vinculado(self) -> bool:
        """Verifica si ya existe un vinculo como representante legal."""
        return any(
            pe.cargo == "representante legal"
            for pe in (self.personas_relacionadas or [])
        )

    def __repr__(self):
        return f"<Empresa(ruc='{self.ruc}', nombre='{self.nombre}')>"


class PersonaEmpresa(Base):
    """
    Vínculo entre una persona y una empresa con un cargo específico.
    Reemplaza a PersonaTrabajo (empresa_nombre texto -> entidad Empresa).

    Ejemplos de cargo:
      - 'trabajador' / 'empleado'
      - 'representante legal'
      - 'gerente general'
      - 'socio' / 'accionista'
    """
    __tablename__ = "persona_empresa"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(
        Integer, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    empresa_id = Column(
        Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    cargo = Column(String(200), nullable=True,
                   comment="Rol de la persona en la empresa: trabajador, representante legal, etc.")
    fecha_desde = Column(Date, nullable=True)
    fecha_hasta = Column(Date, nullable=True)
    observacion = Column(Text, nullable=True)

    persona = relationship("Persona", back_populates="empresas")
    empresa = relationship("Empresa", back_populates="personas_relacionadas")

    # Una persona puede tener varios cargos en la misma empresa
    __table_args__ = (
        UniqueConstraint(
            "persona_id", "empresa_id", "cargo",
            name="uq_persona_empresa_cargo",
        ),
    )

    def __repr__(self):
        return (
            f"<PersonaEmpresa(persona_id={self.persona_id}, "
            f"empresa_id={self.empresa_id}, cargo='{self.cargo}')>"
        )


class EmpresaEtiqueta(Base):
    """
    Tabla pivote: asigna una etiqueta a una empresa.
    """
    __tablename__ = "empresa_etiqueta"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(
        Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    etiqueta_id = Column(
        Integer, ForeignKey("etiquetas.id", ondelete="CASCADE"), nullable=False
    )
    observacion = Column(Text, nullable=True)
    fecha_asignacion = Column(DateTime(timezone=True), server_default=func.now())

    empresa = relationship("Empresa", back_populates="etiquetas_asignadas")
    etiqueta = relationship("Etiqueta", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("empresa_id", "etiqueta_id", name="uq_empresa_etiqueta"),
    )

    def __repr__(self):
        return f"<EmpresaEtiqueta(empresa={self.empresa_id}, etiqueta={self.etiqueta_id})>"


# ═══════════════════════════════════════════════════════════════════════════════
# (Eliminado) PersonaTrabajo — reemplazado por Empresa + PersonaEmpresa
# ═══════════════════════════════════════════════════════════════════════════════


class Usuario(Base):
    """Cuenta de acceso al sistema."""
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    rol = Column(String(20), nullable=False, default="lector", comment="admin | lector")
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Usuario(username='{self.username}', rol='{self.rol}')>"


class Auditoria(Base):
    """Registro de cambios en la base de datos."""
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    usuario_username = Column(String(80), nullable=True)
    accion = Column(String(20), nullable=False, comment="CREATE | UPDATE | DELETE")
    entidad = Column(String(50), nullable=False, comment="Persona | Relacion | Etiqueta | Empresa | PersonaEmpresa")
    entidad_id = Column(String(50), nullable=True, comment="DNI o ID de la entidad")
    detalle = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    usuario = relationship("Usuario")
