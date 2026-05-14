from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.schemas.book import BookCreate, BookUpdate, BookResponse, BookFilter
from app.schemas.common import PaginatedResponse, PaginationParams, get_pagination_params, MessageResponse
from app.services.book_service import BookService
from app.core.logger import logger

router = APIRouter(prefix="/books", tags=["Books"])


@router.get(
    "",
    response_model=PaginatedResponse[BookResponse],
    summary="List all books",
    description="Returns paginated books. Supports filtering by author, genre, availability, and keyword search.",
)
def list_books(
    pagination: PaginationParams = Depends(get_pagination_params),
    author: Optional[str] = Query(None, description="Filter by author name"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    available_only: bool = Query(False, description="Show only available books"),
    search: Optional[str] = Query(None, description="Search by title or author"),
    published_year: Optional[int] = Query(None, description="Filter by publication year"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    filters = BookFilter(
        author=author,
        genre=genre,
        available_only=available_only,
        search=search,
        published_year=published_year,
    )
    books, total = BookService.list_books(db, pagination, filters)
    return PaginatedResponse.create(
        items=[BookResponse.model_validate(b) for b in books],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{book_id}",
    response_model=BookResponse,
    summary="Get book by ID",
)
def get_book(
    book_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    # Uses cache-aside pattern
    result = BookService.get_by_id_cached(db, book_id)
    if isinstance(result, dict):
        return result  # From cache — FastAPI auto-validates via response_model
    return result


@router.post(
    "",
    response_model=BookResponse,
    status_code=201,
    summary="Add a new book (Admin only)",
    dependencies=[Depends(require_admin)],
)
def create_book(
    data: BookCreate,
    db: Session = Depends(get_db),
):
    return BookService.create(db, data)


@router.put(
    "/{book_id}",
    response_model=BookResponse,
    summary="Update a book (Admin only)",
    dependencies=[Depends(require_admin)],
)
def update_book(
    book_id: int,
    data: BookUpdate,
    db: Session = Depends(get_db),
):
    return BookService.update(db, book_id, data)


@router.delete(
    "/{book_id}",
    response_model=MessageResponse,
    summary="Delete a book (Admin only)",
    dependencies=[Depends(require_admin)],
)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    BookService.delete(db, book_id)
    return {"message": f"Book {book_id} deleted successfully"}
