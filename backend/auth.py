"""
auth.py — Autenticación JWT + compatibilidad con Basic Auth + roles + rate limiting.

Flujo:
1. POST /api/auth/login con {username, password} → devuelve JWT token.
2. Los endpoints protegen con dependencia get_current_user (Bearer JWT).
3. Por compatibilidad, también se acepta Authorization Basic mientras se migra.
4. Dependencia requiere_rol("admin") para endpoints de escritura.
5. Rate limiting con slowapi en login.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario

# ─── Configuración JWT ─────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", "redcorruptela_super_secret_key_change_in_prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

# ─── Password hashing ──────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Security schemes ──────────────────────────────────────────────────────
security_basic = HTTPBasic(auto_error=False)
security_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Genera hash bcrypt de una contraseña."""
    return pwd_context.hash(password)


def verificar_password(plain: str, hashed: str) -> bool:
    """Verifica contraseña contra su hash bcrypt."""
    return pwd_context.verify(plain, hashed)


def crear_token(username: str, usuario_id: int, rol: str) -> str:
    """Crea un JWT token para el usuario."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "id": usuario_id,
        "rol": rol,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> dict:
    """Decodifica un JWT token y retorna el payload."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def seed_usuario_admin(db: Session):
    """
    Crea o migra el usuario admin desde AUTH_USERS en la base de datos.
    Se llama al iniciar la aplicación.
    """
    raw = os.getenv("AUTH_USERS", "admin:redcorruptela2024")
    for par in raw.split(","):
        par = par.strip()
        if ":" not in par:
            continue
        username, password = par.split(":", 1)
        username = username.strip()
        password = password.strip()

        existente = db.query(Usuario).filter(Usuario.username == username).first()
        if existente:
            # Actualizar hash por si cambió la clave
            existente.password_hash = hash_password(password)
            existente.rol = "admin"
        else:
            u = Usuario(
                username=username,
                password_hash=hash_password(password),
                rol="admin",
                activo=True,
            )
            db.add(u)
    db.commit()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    basic: Optional[HTTPBasicCredentials] = Depends(security_basic),
    bearer: Optional[str] = Depends(security_bearer),
) -> Usuario:
    """
    Obtiene el usuario autenticado desde:
    1. JWT Bearer token (nuevo)
    2. HTTP Basic Auth (compatibilidad)

    Retorna el objeto Usuario o lanza 401.
    """
    usuario = None

    # Intentar JWT primero
    if bearer:
        try:
            payload = decodificar_token(bearer.credentials)
            username = payload.get("sub")
            usuario = db.query(Usuario).filter(
                Usuario.username == username, Usuario.activo == True
            ).first()
        except Exception:
            pass

    # Fallback a Basic Auth (compatibilidad)
    if not usuario and basic:
        u = db.query(Usuario).filter(
            Usuario.username == basic.username, Usuario.activo == True
        ).first()
        if u and verificar_password(basic.password, u.password_hash):
            usuario = u

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return usuario


def requiere_rol(*roles: str):
    """
    Dependencia que verifica que el usuario tenga uno de los roles especificados.

    Uso:
        @app.delete("/api/personas/{dni}")
        def eliminar(user: Usuario = Depends(requiere_rol("admin"))):
            ...
    """
    def _verificar(user: Usuario = Depends(get_current_user)):
        if user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol: {' o '.join(roles)}",
            )
        return user
    return _verificar
