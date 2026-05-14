"""
app/core/security.py  — Task 2: JWT Authentication + Role-Based Authorization
==============================================================================
Provides:
  - Password hashing / verification (bcrypt)
  - Access token generation (short-lived, 30 min)
  - Refresh token generation (long-lived, 7 days)
  - Token decoding & validation
  - Token blacklist check (Redis)
  - FastAPI dependency guards:
      get_current_user       → any authenticated user
      require_admin          → admin role only
      require_member         → member role only
      require_member_or_admin→ either role
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger

# ─── Password hashing ────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Bearer scheme ────────────────────────────────────────────────────────────
security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plaintext password against stored bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# ─── Token Generation ─────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """
    Create a short-lived JWT access token (default 30 min).
    Payload includes: sub (user_id), role, type=access, iat, exp.
    """
    payload = data.copy()
    now = datetime.now(timezone.utc)
    payload.update({
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    })
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logger.debug(f"Access token created for user: {data.get('sub')}")
    return token


def create_refresh_token(data: dict) -> str:
    """
    Create a long-lived JWT refresh token (default 7 days).
    Payload includes: sub (user_id), type=refresh, iat, exp.
    Refresh tokens carry minimal claims — no role (role may change).
    """
    payload = {"sub": data["sub"], "type": "refresh"}
    now = datetime.now(timezone.utc)
    payload.update({
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    })
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logger.debug(f"Refresh token created for user: {data.get('sub')}")
    return token


# ─── Token Decoding ───────────────────────────────────────────────────────────

def _decode_token(token: str, expected_type: str) -> dict:
    """
    Decode and validate a JWT token.
    Raises HTTP 401 on any failure (expired, invalid, wrong type).
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as e:
        logger.warning(f"Token decode failed [{expected_type}]: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected '{expected_type}'.",
        )

    return payload


def decode_access_token(token: str) -> dict:
    return _decode_token(token, "access")


def decode_refresh_token(token: str) -> dict:
    return _decode_token(token, "refresh")


# ─── Token Blacklist check ────────────────────────────────────────────────────

def _is_blacklisted(token: str) -> bool:
    """Check if the token has been blacklisted (logged out)."""
    from app.core.token_blacklist import is_token_blacklisted
    return is_token_blacklisted(token)


# ─── FastAPI Auth Dependencies ────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """
    Dependency: decode Bearer token, check blacklist, load user from DB.
    Raises 401 for invalid/expired/blacklisted tokens.
    Raises 401 if user is not found or inactive.
    """
    from app.models.user import User

    token = credentials.credentials

    # 1. Check blacklist first (fast Redis lookup)
    if _is_blacklisted(token):
        logger.warning("Blacklisted token used")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
        )

    # 2. Decode & validate
    payload = decode_access_token(token)
    user_id: Optional[str] = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject (sub)",
        )

    # 3. Load user from DB
    user = db.query(User).filter(
        User.id == int(user_id),
        User.is_active == True,
    ).first()

    if not user:
        logger.warning(f"Valid token but user {user_id} not found or inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or has been deactivated",
        )

    logger.debug(f"Authenticated: user_id={user.id} role={user.role}")
    return user


def get_current_active_user(current_user=Depends(get_current_user)):
    """Dependency: get current user and assert they are active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is inactive",
        )
    return current_user


# ─── Role Guards ──────────────────────────────────────────────────────────────

def require_admin(current_user=Depends(get_current_user)):
    """
    Dependency: restrict endpoint to Admin role only.
    Returns the user object on success.
    Raises HTTP 403 if the user is not an admin.
    """
    if current_user.role != "admin":
        logger.warning(
            f"Forbidden: user {current_user.id} (role={current_user.role}) "
            f"attempted admin-only action"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires Admin privileges",
        )
    return current_user


def require_member(current_user=Depends(get_current_user)):
    """
    Dependency: restrict endpoint to Member role only.
    Admins are blocked — use require_member_or_admin if you want both.
    """
    if current_user.role != "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is restricted to Member accounts",
        )
    return current_user


def require_member_or_admin(current_user=Depends(get_current_user)):
    """Dependency: allow both Admin and Member roles."""
    if current_user.role not in ("admin", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges",
        )
    return current_user


def require_self_or_admin(user_id: int, current_user=Depends(get_current_user)):
    """
    Dependency factory: allow the user themselves OR an admin.
    Usage: Depends(lambda cu=Depends(get_current_user): require_self_or_admin(user_id, cu))
    """
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only perform this action on your own account",
        )
    return current_user
