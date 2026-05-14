from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserAdminUpdate, UserFilter
from app.schemas.common import PaginationParams
from app.core.security import hash_password, verify_password, create_access_token
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.core.logger import logger
from app.core.config import settings


CACHE_PREFIX = "users"


class UserService:
    """Business logic for user management."""

    # ─── Auth ─────────────────────────────────────────────────────────────────

    @staticmethod
    def register(db: Session, data: UserCreate) -> User:
        """Register a new user."""
        if db.query(User).filter(User.email == data.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{data.email}' is already registered",
            )
        user = User(
            full_name=data.full_name,
            email=data.email,
            hashed_password=hash_password(data.password),
            role=data.role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"New user registered: {user.email} (role={user.role})")
        cache_delete_pattern(f"{CACHE_PREFIX}:*")
        return user

    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> dict:
        """Authenticate a user and return a JWT token payload."""
        user = db.query(User).filter(User.email == email, User.is_active == True).first()
        if not user or not verify_password(password, user.hashed_password):
            logger.warning(f"Failed login attempt for email: {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        token = create_access_token({"sub": str(user.id), "role": user.role})
        logger.info(f"User logged in: {email}")
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user,
        }

    # ─── CRUD ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> User:
        cache_key = f"{CACHE_PREFIX}:{user_id}"
        cached = cache_get(cache_key)
        if cached:
            # Re-fetch from DB using cached ID to get a proper ORM object
            # (We store serialized data in cache, but return ORM objects from service)
            pass  # Cache used in route layer for response serialization

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
        return user

    @staticmethod
    def list_users(
        db: Session,
        pagination: PaginationParams,
        filters: UserFilter,
    ) -> Tuple[List[User], int]:
        query = db.query(User)

        # Apply filters
        if filters.role:
            query = query.filter(User.role == filters.role)
        if filters.is_active is not None:
            query = query.filter(User.is_active == filters.is_active)
        if filters.search:
            term = f"%{filters.search}%"
            query = query.filter(
                or_(User.full_name.ilike(term), User.email.ilike(term))
            )

        total = query.count()
        users = query.offset(pagination.offset).limit(pagination.limit).all()
        logger.debug(f"Listed users: page={pagination.page}, total={total}")
        return users, total

    @staticmethod
    def update(db: Session, user_id: int, data: UserUpdate, requester_role: str) -> User:
        user = UserService.get_by_id(db, user_id)

        update_data = data.model_dump(exclude_unset=True)

        # Check for email conflict
        if "email" in update_data:
            existing = db.query(User).filter(
                User.email == update_data["email"], User.id != user_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use",
                )

        # Role changes only allowed for admins (handled via AdminUpdate schema)
        for key, value in update_data.items():
            setattr(user, key, value)

        db.commit()
        db.refresh(user)
        cache_delete(f"{CACHE_PREFIX}:{user_id}")
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        logger.info(f"User {user_id} updated")
        return user

    @staticmethod
    def delete(db: Session, user_id: int) -> None:
        user = UserService.get_by_id(db, user_id)
        db.delete(user)
        db.commit()
        cache_delete(f"{CACHE_PREFIX}:{user_id}")
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        logger.info(f"User {user_id} deleted")
