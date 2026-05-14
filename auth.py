"""
app/routes/auth.py  — Task 2: Authentication Endpoints
=======================================================
Endpoints:
  POST /auth/register          Register new user
  POST /auth/login             Login → access + refresh tokens
  POST /auth/refresh           Exchange refresh token for new access token
  POST /auth/logout            Blacklist access token
  POST /auth/logout-all        Revoke all tokens for the current user
  GET  /auth/me                Get current user profile
  PUT  /auth/me/password       Change password (invalidates all tokens)
  POST /auth/admin/impersonate/{user_id}  Admin: issue token for any user
"""

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    require_admin,
)
from app.core.token_blacklist import (
    blacklist_token,
    blacklist_all_user_tokens,
    is_token_blacklisted,
)
from app.core.config import settings
from app.core.logger import logger
from app.models.user import User, UserRole
from app.schemas.user import (
    UserCreate,
    UserResponse,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    PasswordChangeRequest,
)
from app.schemas.common import MessageResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/auth", tags=["Authentication"])
security_scheme = HTTPBearer()


# ─── Register ─────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user. Default role is 'member'.
    Admins can set role='admin' during registration.
    Password must be at least 8 characters and contain a digit.
    """
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        logger.warning(f"Registration failed — email already exists: {data.email}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{data.email}' already exists",
        )

    user = User(
        full_name=data.full_name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"New user registered: {user.email} (id={user.id}, role={user.role})")
    return user


# ─── Login ────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive access + refresh tokens",
)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with email and password.
    Returns:
    - access_token  (short-lived, 30 min by default)
    - refresh_token (long-lived, 7 days by default)
    """
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning(f"Failed login attempt for email: {data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        logger.warning(f"Login attempt on inactive account: {data.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact an admin.",
        )

    token_data = {"sub": str(user.id), "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info(f"User logged in: {user.email} (id={user.id}, role={user.role})")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user,
    }


# ─── Refresh Token ────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Get a new access token using a refresh token",
)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token.
    The refresh token itself is NOT rotated (stateless approach).
    To rotate refresh tokens, blacklist the old one and issue a new one.
    """
    payload = decode_refresh_token(data.refresh_token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    # Check if refresh token is blacklisted
    if is_token_blacklisted(data.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_data = {"sub": str(user.id), "role": user.role}
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    # Blacklist old refresh token (token rotation)
    blacklist_token(data.refresh_token)

    logger.info(f"Token refreshed for user: {user.email}")

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user,
    }


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout — invalidate current access token",
)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    current_user=Depends(get_current_user),
):
    """
    Blacklist the current access token in Redis.
    The token remains syntactically valid but will be rejected
    by all protected endpoints until it naturally expires.
    """
    token = credentials.credentials
    blacklist_token(token)
    logger.info(f"User logged out: {current_user.email} (id={current_user.id})")
    return {"message": "Successfully logged out. Your token has been invalidated."}


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Logout from all devices — revoke all active tokens",
)
def logout_all(current_user=Depends(get_current_user)):
    """
    Revoke ALL tokens for the current user by setting a global
    revocation timestamp in Redis. Any token issued before this
    moment will be rejected. Useful for security incidents or
    password changes.
    """
    blacklist_all_user_tokens(current_user.id)
    logger.info(f"All tokens revoked for user: {current_user.email} (id={current_user.id})")
    return {"message": "All sessions have been terminated. Please log in again on all devices."}


# ─── Current User ─────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user's profile",
)
def get_me(current_user=Depends(get_current_user)):
    return current_user


# ─── Password Change ──────────────────────────────────────────────────────────

@router.put(
    "/me/password",
    response_model=MessageResponse,
    summary="Change current user's password",
)
def change_password(
    data: PasswordChangeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change the authenticated user's password.
    - Verifies the current password before allowing the change.
    - Revokes all existing tokens (forces re-login on all devices).
    """
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    current_user.hashed_password = hash_password(data.new_password)
    db.commit()

    # Invalidate all existing tokens
    blacklist_all_user_tokens(current_user.id)
    blacklist_token(credentials.credentials)  # Current token too

    logger.info(f"Password changed for user: {current_user.email} (id={current_user.id})")
    return {"message": "Password changed successfully. Please log in again on all devices."}


# ─── Admin: Impersonate ───────────────────────────────────────────────────────

@router.post(
    "/admin/impersonate/{user_id}",
    response_model=TokenResponse,
    summary="[Admin] Issue a token for any user (for support/debugging)",
    dependencies=[Depends(require_admin)],
)
def impersonate_user(user_id: int, db: Session = Depends(get_db)):
    """
    Admin-only: Generate an access token for any user.
    Useful for debugging or customer support.
    All impersonation actions are logged.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    token_data = {"sub": str(user.id), "role": user.role, "impersonated": True}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.warning(f"Admin impersonation: token issued for user {user.email} (id={user.id})")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user,
    }
