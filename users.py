from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.user import UserRole
from app.schemas.user import (
    UserResponse, UserUpdate, UserAdminUpdate, UserFilter,
)
from app.schemas.common import PaginatedResponse, PaginationParams, get_pagination_params, MessageResponse
from app.services.user_service import UserService
from app.core.logger import logger

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=PaginatedResponse[UserResponse],
    summary="List all users (Admin only)",
    dependencies=[Depends(require_admin)],
)
def list_users(
    pagination: PaginationParams = Depends(get_pagination_params),
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    db: Session = Depends(get_db),
):
    filters = UserFilter(role=role, is_active=is_active, search=search)
    users, total = UserService.list_users(db, pagination, filters)
    return PaginatedResponse.create(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Members can only view their own profile
    if current_user.role != "admin" and current_user.id != user_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile",
        )
    return UserService.get_by_id(db, user_id)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user profile",
)
def update_user(
    user_id: int,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Members can only edit their own profile and cannot change role
    if current_user.role != "admin":
        if current_user.id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile",
            )
        if data.role is not None:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user roles",
            )

    return UserService.update(db, user_id, data, current_user.role)


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Delete user (Admin only)",
    dependencies=[Depends(require_admin)],
)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    UserService.delete(db, user_id)
    return {"message": f"User {user_id} deleted successfully"}
