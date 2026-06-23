"""
auth.py — Autenticación HTTP Basic para proteger la API.

Los usuarios se definen en la variable de entorno AUTH_USERS con el formato:
    usuario1:contraseña1,usuario2:contraseña2

Si la variable no está definida, se usa un usuario por defecto:
    admin:redcorruptela2024

El frontend envía el header Authorization: Basic <base64> en cada petición.
"""

import os
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def _cargar_usuarios() -> dict[str, str]:
    """
    Carga los usuarios desde la variable de entorno AUTH_USERS.
    Formato: "usuario1:clave1,usuario2:clave2"
    """
    raw = os.getenv("AUTH_USERS", "admin:redcorruptela2024")
    usuarios = {}
    for par in raw.split(","):
        par = par.strip()
        if ":" in par:
            usuario, clave = par.split(":", 1)
            usuarios[usuario.strip()] = clave.strip()
    return usuarios


# Diccionario de usuarios cargado al iniciar el módulo
USUARIOS = _cargar_usuarios()


def autenticar(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Dependencia de FastAPI que verifica las credenciales Basic Auth.
    Se inyecta en los endpoints que requieren protección.

    Uso:
        @app.get("/protegido")
        def ruta_protegida(user=Depends(autenticar)):
            ...
    """
    clave_correcta = USUARIOS.get(credentials.username)
    if clave_correcta is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Comparación segura contra timing attacks
    if not secrets.compare_digest(credentials.password, clave_correcta):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña incorrecta",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username
