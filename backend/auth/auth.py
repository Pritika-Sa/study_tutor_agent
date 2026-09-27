"""
Password hashing and JWT authentication.

This module is the single place where authentication logic lives -- API
routes call these functions rather than re-implementing hashing or token
handling, so there is exactly one code path for each concern.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database.database import get_db
from database.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl points Swagger's "Authorize" button at the login endpoint; it does
# not change how tokens are validated.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt. Never store the plain value."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plain-text password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: int) -> str:
    """
    Issue a JWT for the given user.

    Payload intentionally contains only `sub` (user id) and `exp`
    (expiration) -- no password or other sensitive data ever goes into the
    token.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode_user_id(token: str) -> int:
    """Decode and validate a JWT, returning the user id encoded in `sub`."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise _CREDENTIALS_ERROR

    raw_user_id: Optional[str] = payload.get("sub")
    if raw_user_id is None:
        raise _CREDENTIALS_ERROR

    try:
        return int(raw_user_id)
    except ValueError:
        raise _CREDENTIALS_ERROR


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Reusable protected-route dependency.

    Reads the Bearer token, validates signature + expiration, resolves the
    user from SQLite, and raises HTTP 401 for anything invalid.
    """
    user_id = _decode_user_id(token)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _CREDENTIALS_ERROR

    return user
