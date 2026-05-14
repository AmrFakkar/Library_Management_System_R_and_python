from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status

from app.models.book import Book
from app.schemas.book import BookCreate, BookUpdate, BookFilter
from app.schemas.common import PaginationParams
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.core.logger import logger

CACHE_PREFIX = "books"


class BookService:
    """Business logic for book management."""

    @staticmethod
    def create(db: Session, data: BookCreate) -> Book:
        # Check ISBN uniqueness if provided
        if data.isbn:
            existing = db.query(Book).filter(Book.isbn == data.isbn).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A book with ISBN '{data.isbn}' already exists",
                )

        book = Book(
            title=data.title,
            author=data.author,
            isbn=data.isbn,
            genre=data.genre,
            description=data.description,
            total_copies=data.total_copies,
            available_copies=data.total_copies,
            published_year=data.published_year,
        )
        db.add(book)
        db.commit()
        db.refresh(book)
        logger.info(f"Book created: '{book.title}' by {book.author} (id={book.id})")
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        return book

    @staticmethod
    def get_by_id(db: Session, book_id: int) -> Book:
        cache_key = f"{CACHE_PREFIX}:{book_id}"
        cached = cache_get(cache_key)
        if cached:
            # Return cached dict for route-level serialization
            # We still need the ORM object for mutations, so only use cache in GET routes
            pass

        book = db.query(Book).filter(Book.id == book_id, Book.is_active == True).first()
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Book {book_id} not found",
            )
        return book

    @staticmethod
    def get_by_id_cached(db: Session, book_id: int):
        """Get book with cache-aside pattern for GET endpoints."""
        cache_key = f"{CACHE_PREFIX}:{book_id}"
        cached = cache_get(cache_key)
        if cached:
            return cached  # Return raw dict (serializable)

        book = db.query(Book).filter(Book.id == book_id, Book.is_active == True).first()
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Book {book_id} not found",
            )

        from app.schemas.book import BookResponse
        data = BookResponse.model_validate(book).model_dump(mode="json")
        cache_set(cache_key, data)
        return data

    @staticmethod
    def list_books(
        db: Session,
        pagination: PaginationParams,
        filters: BookFilter,
    ) -> Tuple[List[Book], int]:
        # Build cache key from all params
        cache_key = (
            f"{CACHE_PREFIX}:list:"
            f"p{pagination.page}:ps{pagination.page_size}:"
            f"a{filters.author}:g{filters.genre}:"
            f"av{filters.available_only}:s{filters.search}:"
            f"y{filters.published_year}"
        )
        cached = cache_get(cache_key)
        if cached:
            return cached["items"], cached["total"]

        query = db.query(Book).filter(Book.is_active == True)

        if filters.author:
            query = query.filter(Book.author.ilike(f"%{filters.author}%"))
        if filters.genre:
            query = query.filter(Book.genre.ilike(f"%{filters.genre}%"))
        if filters.available_only:
            query = query.filter(Book.available_copies > 0)
        if filters.search:
            term = f"%{filters.search}%"
            query = query.filter(
                or_(Book.title.ilike(term), Book.author.ilike(term))
            )
        if filters.published_year:
            query = query.filter(Book.published_year == filters.published_year)

        total = query.count()
        books = query.order_by(Book.title).offset(pagination.offset).limit(pagination.limit).all()

        from app.schemas.book import BookResponse
        serialized = [BookResponse.model_validate(b).model_dump(mode="json") for b in books]
        cache_set(cache_key, {"items": serialized, "total": total})

        logger.debug(f"Listed books: page={pagination.page}, total={total}")
        return books, total

    @staticmethod
    def update(db: Session, book_id: int, data: BookUpdate) -> Book:
        book = BookService.get_by_id(db, book_id)
        update_data = data.model_dump(exclude_unset=True)

        # Handle total_copies change → adjust available_copies proportionally
        if "total_copies" in update_data:
            diff = update_data["total_copies"] - book.total_copies
            new_available = book.available_copies + diff
            if new_available < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot reduce total copies to {update_data['total_copies']}; "
                        f"{book.total_copies - book.available_copies} copies are currently borrowed."
                    ),
                )
            update_data["available_copies"] = new_available

        # ISBN uniqueness check
        if "isbn" in update_data and update_data["isbn"]:
            existing = db.query(Book).filter(
                Book.isbn == update_data["isbn"], Book.id != book_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another book with this ISBN already exists",
                )

        for key, value in update_data.items():
            setattr(book, key, value)

        db.commit()
        db.refresh(book)
        cache_delete(f"{CACHE_PREFIX}:{book_id}")
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        logger.info(f"Book {book_id} updated")
        return book

    @staticmethod
    def delete(db: Session, book_id: int) -> None:
        book = BookService.get_by_id(db, book_id)

        # Check for active borrows
        from app.models.borrow_record import BorrowRecord, BorrowStatus
        active_borrows = db.query(BorrowRecord).filter(
            BorrowRecord.book_id == book_id,
            BorrowRecord.status == BorrowStatus.active,
        ).count()

        if active_borrows > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete book: {active_borrows} active borrow(s) exist. Return all copies first.",
            )

        # Soft delete
        book.is_active = False
        db.commit()
        cache_delete(f"{CACHE_PREFIX}:{book_id}")
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        logger.info(f"Book {book_id} soft-deleted")
