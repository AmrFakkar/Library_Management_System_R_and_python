"""
app/schemas/user.py  — Task 2: Auth-related Pydantic Schemas
=============================================================
Extends Task 1 schemas with:
  - RefreshRequest       — for POST /auth/refresh
  - TokenResponse        — now includes refresh_token
  - PasswordChangeRequest— for PUT /auth/me/password
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.user import UserRole


# ─── Request Schemas ──────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, examples=["John Doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=8, max_length=128, examples=["StrongPass1"])
    role: UserRole = Field(default=UserRole.member)

    @field_validator("password")
    @classmethod
    def password_must_contain_digit(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., examples=["StrongPass1"])


class RefreshRequest(BaseModel):
    """Body for POST /auth/refresh."""
    refresh_token: str = Field(..., description="A valid refresh JWT token")


class PasswordChangeRequest(BaseModel):
    """Body for PUT /auth/me/password."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("New password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class UserAdminUpdate(UserUpdate):
    """Admins can additionally change the role."""
    role: Optional[UserRole] = None


# ─── Response Schemas ─────────────────────────────────────────────────────────

class UserPublicResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: UserRole

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """
    Returned on login and refresh.
    access_token  — short-lived (30 min), used in Authorization header
    refresh_token — long-lived (7 days), used only for /auth/refresh
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    user: UserPublicResponse


# ─── Filter Schemas ───────────────────────────────────────────────────────────

class UserFilter(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    search: Optional[str] = Field(None, description="Search by name or email")
