"""
models.py — Modelos SQLAlchemy para la base de datos de RedCorruptela.

Define cuatro tablas principales:
  - personas: datos biográficos de cada individuo (DNI único).
  - relaciones: vínculo dirigido entre dos personas (padre, madre, cónyuge, etc.).
  - etiquetas: categorías para marcar a personas (ej. "contratado en municipalidad").
  - persona_etiqueta: tabla pivote que asigna etiquetas a personas con observaciones.
"""

from sqlalchemy import (
    Column, Integer, String, Date, Boolean, ForeignKey,
    Text, DateTime, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Persona(Base):
    """
    Representa a una persona física identificada por su DNI.
    El campo 'activo' permite baja lógica (no se borra realmente).
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
    Categoría o marcador que se puede asignar a personas.
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

    def __repr__(self):
        return f"<PersonaEtiqueta(persona={self.persona_id}, etiqueta={self.etiqueta_id})>"
