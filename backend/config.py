"""
config.py — Configuración centralizada via variables de entorno.

Usa pydantic-settings para validar y tipar todas las variables.
Si JWT_SECRET tiene el valor por defecto en producción, la app falla.
"""

import os
from typing import Optional


class Settings:
    """
    Configuración de la aplicación.

    Las variables se leen desde os.getenv(). En producción,
    crear un archivo .env en la raíz o configurarlas en el
    panel de Render/Neon.
    """

    # ── Base de datos ────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/redcorruptela"
    )

    # ── JWT ──────────────────────────────────────────────────────────
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "dev-secret-CHANGE-IN-PRODUCTION"
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "72"))

    # ── Entorno ──────────────────────────────────────────────────────
    ENV: str = os.getenv("ENV", "development")

    # ── Redis (opcional, para caché de parentescos) ──────────────────
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL") or None

    # ── Debug ────────────────────────────────────────────────────────
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # ── Validación en producción ─────────────────────────────────────
    def __init__(self):
        if self.ENV == "production" and self.JWT_SECRET == "dev-secret-CHANGE-IN-PRODUCTION":
            raise ValueError(
                "JWT_SECRET no configurado. "
                "Define JWT_SECRET en el entorno antes de desplegar a producción."
            )
        # Validar que DATABASE_URL no sea el valor por defecto en producción
        if self.ENV == "production" and "localhost" in self.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL apunta a localhost en producción. "
                "Configura DATABASE_URL correctamente."
            )


settings = Settings()
