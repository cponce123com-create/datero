"""
utils/validators.py — Validación de relaciones familiares.

Funciones:
  - validar_edad(origen, destino, tipo): verifica coherencia etaria
  - corregir_genero(tipo, genero_origen, genero_destino): corrige tipo según género
  - validar_relacion(principal, familiar, tipo): ejecuta todas las validaciones
"""

from datetime import datetime, date
from typing import Optional, Tuple

from models import Persona


def _calcular_edad(fecha_nac: Optional[date]) -> Optional[int]:
    """Calcula edad en años a partir de fecha de nacimiento."""
    if not fecha_nac:
        return None
    today = date.today()
    return today.year - fecha_nac.year - (
        (today.month, today.day) < (fecha_nac.month, fecha_nac.day)
    )


# Edad mínima para ser padre/madre (biológicamente plausible)
_EDAD_MINIMA_PADRE = 12


def validar_edad(origen: Persona, destino: Persona, tipo: str) -> Tuple[bool, str]:
    """
    Verifica coherencia de edad según el tipo de relación.

    Retorna (valido: bool, mensaje: str).

    Reglas:
      - PADRE/MADRE: el origen debe ser >= 12 años mayor que el destino
      - HIJO/HIJA: el destino debe ser >= 12 años mayor que el origen
      - HERMANO: sin restricción de edad
      - CONYUGE: sin restricción (diferencia razonable)
      - Otros: sin restricción
    """
    edad_origen = _calcular_edad(origen.fecha_nacimiento)
    edad_destino = _calcular_edad(destino.fecha_nacimiento)

    # Si falta fecha, no podemos validar
    if edad_origen is None or edad_destino is None:
        return True, "Fechas insuficientes, se asume valido"

    if tipo in ("padre", "madre"):
        diff = edad_origen - edad_destino
        if diff < _EDAD_MINIMA_PADRE:
            return False, (
                f"Edad incompatible: {origen.nombre_completo} ({edad_origen}) "
                f"es {diff} años mayor que {destino.nombre_completo} ({edad_destino}). "
                f"Mínimo requerido: {_EDAD_MINIMA_PADRE}"
            )
        if diff > 60:
            return True, (
                f"Diferencia grande ({diff} años) pero posible. "
                f"Marcar para revision"
            )
        return True, ""

    if tipo in ("hijo", "hija"):
        diff = edad_destino - edad_origen
        if diff < _EDAD_MINIMA_PADRE:
            return False, (
                f"Edad incompatible: {destino.nombre_completo} ({edad_destino}) "
                f"es {diff} años mayor que {origen.nombre_completo} ({edad_origen}). "
                f"Mínimo requerido: {_EDAD_MINIMA_PADRE}"
            )
        return True, ""

    return True, ""


def corregir_genero(
    tipo: str,
    genero_origen: Optional[str],
    genero_destino: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Corrige el tipo de relación según los géneros conocidos.

    Retorna (tipo_corregido: str | None, observacion: str | None).
    Si retorna None, la relacion se rechaza por incompatibilidad total.
    """
    obs = None

    # Si no hay género, no podemos corregir
    if not genero_origen and not genero_destino:
        return tipo, None

    t = tipo.lower()

    # Correcciones por género del origen (quien es padre/madre)
    if t in ("padre",) and genero_origen == "FEMENINO":
        obs = f"Corregido: '{tipo}' -> 'MADRE' (origen es femenino)"
        return "madre", obs
    if t in ("madre",) and genero_origen == "MASCULINO":
        obs = f"Corregido: '{tipo}' -> 'PADRE' (origen es masculino)"
        return "padre", obs

    # Correcciones por género del destino (quien es hijo/hija)
    if t in ("hijo",) and genero_destino == "FEMENINO":
        obs = f"Corregido: '{tipo}' -> 'HIJA' (destino es femenino)"
        return "hija", obs
    if t in ("hija",) and genero_destino == "MASCULINO":
        obs = f"Corregido: '{tipo}' -> 'HIJO' (destino es masculino)"
        return "hijo", obs

    return tipo, obs


def validar_relacion(
    principal: Persona,
    familiar: Persona,
    tipo: str,
) -> Tuple[bool, str, Optional[str]]:
    """
    Ejecuta todas las validaciones sobre una relación.
    Retorna (valida: bool, tipo_final: str, observacion: str | None).
    """
    # 1. Auto-relación
    if principal.id == familiar.id:
        return False, tipo, "Auto-relacion rechazada"

    # 2. Corrección de género
    tipo_final, obs_genero = corregir_genero(tipo, principal.genero, familiar.genero)
    if tipo_final is None:
        return False, tipo, f"Genero incompatible: {principal.genero} vs {familiar.genero}"

    # 3. Validación de edad
    valido, msg_edad = validar_edad(principal, familiar, tipo_final)
    if not valido:
        return False, tipo_final, msg_edad

    # Combinar observaciones
    obs = obs_genero or ""
    if msg_edad and "grande" in msg_edad.lower():
        obs = (obs + "; " if obs else "") + msg_edad

    return True, tipo_final, obs or None
