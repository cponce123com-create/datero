"""
parentesco_service.py — Servicio de orquestación de inferencias.

Wrapper que llama a las funciones de parentesco.py y agrega
manejo de errores y lógica adicional si es necesaria.
"""

from typing import List
from sqlalchemy.orm import Session

from models import Persona
from parentesco import (
    inferir_todos_parentescos as _inferir_todos,
    inferir_parentesco_especifico as _inferir_especifico,
)


def inferir_todos_parentescos(db: Session, persona: Persona) -> List[dict]:
    """Ejecuta todas las inferencias y retorna resultados combinados."""
    try:
        return _inferir_todos(db, persona)
    except Exception as e:
        return []


def inferir_parentesco_especifico(
    db: Session, persona: Persona, tipo: str
) -> List[dict]:
    """Infiera un tipo específico de parentesco."""
    try:
        return _inferir_especifico(db, persona, tipo)
    except Exception as e:
        return []
