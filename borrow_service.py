from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from fastapi import HTTPException, status

from app.models.borrow_record import BorrowRecord, BorrowStatus
from app.models.book import Book
from app.models.user import User
from app.schemas.borrow_record import BorrowRequest, ReturnRequest, BorrowFilter
from app.schemas.common import PaginationParams
from app.core.config import settings
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.core.logger import logger

CACHE_PREFIX = "borrows"


class BorrowService:
    """Business logic for borrowing and returning books."""

    @staticmethod
    def borrow_book(db: Session, user: User, data: BorrowRequest) -> BorrowRecord:
        """
        Borrow a book for a user, enforcing:
        - Book availability
        - Per-user borrow limit
        - No duplicate active borrows of the same book
        """
        # 1. Load book
        book = db.query(Book).filter(Book.id == data.book_id, Book.is_active == True).first()
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Book {data.book_id} not found",
            )

        # 2. Check availability
        if book.available_copies <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Book '{book.title}' is currently unavailable (all copies are borrowed)",
            )

        # 3. Check user borrow limit
        active_count = db.query(BorrowRecord).filter(
            BorrowRecord.user_id == user.id,
            BorrowRecord.status == BorrowStatus.active,
        ).count()

        if active_count >= settings.MAX_BORROWED_BOOKS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Borrow limit reached. You have {active_count} active borrows; "
                    f"maximum is {settings.MAX_BORROWED_BOOKS}."
                ),
            )

        # 4. Prevent duplicate active borrow of the same book
        duplicate = db.query(BorrowRecord).filter(
            BorrowRecord.user_id == user.id,
            BorrowRecord.book_id == data.book_id,
            BorrowRecord.status == BorrowStatus.active,
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already have an active borrow for '{book.title}'",
            )

        # 5. Create borrow record
        now = datetime.now(timezone.utc)
        due_date = now + timedelta(days=settings.MAX_BORROW_DAYS)

        record = BorrowRecord(
            user_id=user.id,
            book_id=data.book_id,
            status=BorrowStatus.active,
            borrowed_at=now,
            due_date=due_date,
            notes=data.notes,
        )
        db.add(record)

        # 6. Decrement available copies
        book.available_copies -= 1

        db.commit()
        db.refresh(record)

        # Eager-load relationships for response
        record = (
            db.query(BorrowRecord)
            .options(joinedload(BorrowRecord.book), joinedload(BorrowRecord.user))
            .filter(BorrowRecord.id == record.id)
            .first()
        )

        # Invalidate caches
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        cache_delete(f"books:{data.book_id}")
        cache_delete_pattern(f"books:list:*")

        logger.info(
            f"Book borrowed: user={user.id} book={data.book_id} "
            f"record={record.id} due={due_date.date()}"
        )
        return record

    @staticmethod
    def return_book(db: Session, user: User, record_id: int, data: ReturnRequest) -> BorrowRecord:
        """Return a borrowed book."""
        record = (
            db.query(BorrowRecord)
            .options(joinedload(BorrowRecord.book), joinedload(BorrowRecord.user))
            .filter(BorrowRecord.id == record_id)
            .first()
        )

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Borrow record {record_id} not found",
            )

        # Members can only return their own books
        if user.role == "member" and record.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only return your own borrowed books",
            )

        if record.status == BorrowStatus.returned:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This book has already been returned",
            )

        # Mark as returned
        now = datetime.now(timezone.utc)
        record.status = BorrowStatus.returned
        record.returned_at = now
        if data.notes:
            record.notes = data.notes

        # Restore available copies
        book = db.query(Book).filter(Book.id == record.book_id).first()
        if book:
            book.available_copies = min(book.available_copies + 1, book.total_copies)

        db.commit()
        db.refresh(record)

        # Invalidate caches
        cache_delete(f"{CACHE_PREFIX}:{record_id}")
        cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
        cache_delete(f"books:{record.book_id}")
        cache_delete_pattern(f"books:list:*")

        logger.info(
            f"Book returned: user={user.id} book={record.book_id} "
            f"record={record_id} on={now.date()}"
        )
        return record

    @staticmethod
    def get_by_id(db: Session, record_id: int) -> BorrowRecord:
        record = (
            db.query(BorrowRecord)
            .options(joinedload(BorrowRecord.book), joinedload(BorrowRecord.user))
            .filter(BorrowRecord.id == record_id)
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Borrow record {record_id} not found",
            )
        return record

    @staticmethod
    def list_records(
        db: Session,
        pagination: PaginationParams,
        filters: BorrowFilter,
        current_user: Optional[User] = None,
    ) -> Tuple[List[BorrowRecord], int]:
        """
        List borrow records.
        - Admins can filter by any user.
        - Members only see their own records.
        """
        query = db.query(BorrowRecord).options(
            joinedload(BorrowRecord.book),
            joinedload(BorrowRecord.user),
        )

        # Scope to current user if member
        if current_user and current_user.role == "member":
            query = query.filter(BorrowRecord.user_id == current_user.id)
        elif filters.user_id:
            query = query.filter(BorrowRecord.user_id == filters.user_id)

        if filters.book_id:
            query = query.filter(BorrowRecord.book_id == filters.book_id)
        if filters.status:
            query = query.filter(BorrowRecord.status == filters.status)

        total = query.count()
        records = (
            query
            .order_by(BorrowRecord.borrowed_at.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
            .all()
        )

        logger.debug(f"Listed borrow records: page={pagination.page}, total={total}")
        return records, total

    @staticmethod
    def mark_overdue(db: Session) -> int:
        """
        Background task: mark all active records past due_date as overdue.
        Returns count of updated records.
        """
        now = datetime.now(timezone.utc)
        updated = (
            db.query(BorrowRecord)
            .filter(
                BorrowRecord.status == BorrowStatus.active,
                BorrowRecord.due_date < now,
            )
            .update({"status": BorrowStatus.overdue}, synchronize_session=False)
        )
        if updated:
            db.commit()
            cache_delete_pattern(f"{CACHE_PREFIX}:list:*")
            logger.info(f"Marked {updated} borrow record(s) as overdue")
        return updated

    @staticmethod
    def get_user_history(
        db: Session,
        user_id: int,
        pagination: PaginationParams,
    ) -> Tuple[List[BorrowRecord], int]:
        """Get full borrowing history for a specific user."""
        query = (
            db.query(BorrowRecord)
            .options(joinedload(BorrowRecord.book))
            .filter(BorrowRecord.user_id == user_id)
            .order_by(BorrowRecord.borrowed_at.desc())
        )
        total = query.count()
        records = query.offset(pagination.offset).limit(pagination.limit).all()
        return records, total
