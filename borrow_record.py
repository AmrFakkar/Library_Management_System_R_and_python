from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.models.borrow_record import BorrowStatus
from app.schemas.book import BookSummary
from app.schemas.user import UserPublicResponse


class BorrowRequest(BaseModel):
    book_id: int = Field(..., description="ID of the book to borrow")
    notes: Optional[str] = Field(None, max_length=500)


class ReturnRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=500)


class BorrowRecordResponse(BaseModel):
    id: int
    user_id: int
    book_id: int
    status: BorrowStatus
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    # Nested objects
    book: Optional[BookSummary] = None
    user: Optional[UserPublicResponse] = None

    model_config = {"from_attributes": True}


class BorrowRecordSummary(BaseModel):
    """Lightweight borrow info."""
    id: int
    user_id: int
    book_id: int
    status: BorrowStatus
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BorrowFilter(BaseModel):
    """Query filters for borrow records."""
    user_id: Optional[int] = None
    book_id: Optional[int] = None
    status: Optional[BorrowStatus] = None
