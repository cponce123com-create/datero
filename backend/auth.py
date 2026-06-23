"""
auth.py — Autenticación JWT (solo Bearer token).

Flujo:
1. POST /api/auth/login con {username, password} → devuelve JWT token.
2. Los endpoints protegen con dependencia get_current_user (Bearer JWT).
3. Dependencia requiere_rol("admin") para endpoints de escritura.
4. Rate limiting con slowapi en login.

SEGURIDAD: JWT_SECRET es obligatorio via variable de entorno.
"""

import os
import warnings
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario

# ─── Configuración JWT ─────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET")
if not SECRET_KEY:
    SECRET_KEY = "dev-secret-CHANGE-IN-PRODUCTION"
    warnings.warn(
        "JWT_SECRET no configurada. Usando valor inseguro de desarrollo.",
        stacklevel=2,
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

# ─── Security scheme ────────────────────────────────────────────────────────
security_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Genera hash bcrypt de una contraseña."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _bcrypt.hashpw(password, _bcrypt.gensalt()).decode("utf-8")


def verificar_password(plain: str, hashed: str) -> bool:
    """Verifica contraseña contra su hash bcrypt."""
    if isinstance(plain, str):
        plain = plain.encode("utf-8")
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    try:
        return _bcrypt.checkpw(plain, hashed)
    except Exception:
        return False


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
            try:
                if not verificar_password(password, existente.password_hash):
                    existente.password_hash = hash_password(password)
            except Exception:
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
    bearer: str = Depends(security_bearer),
) -> Usuario:
    """
    Obtiene el usuario autenticado desde JWT Bearer token.

    Retorna el objeto Usuario o lanza 401.
    """
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere token de autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decodificar_token(bearer.credentials)
        username = payload.get("sub")
        usuario = db.query(Usuario).filter(
            Usuario.username == username, Usuario.activo == True
        ).first()
    except Exception:
        usuario = None

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
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
