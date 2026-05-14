from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class BookCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, examples=["Clean Code"])
    author: str = Field(..., min_length=1, max_length=255, examples=["Robert C. Martin"])
    isbn: Optional[str] = Field(None, max_length=20, examples=["978-0132350884"])
    genre: Optional[str] = Field(None, max_length=100, examples=["Technology"])
    description: Optional[str] = Field(None, max_length=5000)
    total_copies: int = Field(default=1, ge=1, le=1000)
    published_year: Optional[int] = Field(None, ge=1000, le=2100)

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = v.replace("-", "").replace(" ", "")
        if len(cleaned) not in (10, 13):
            raise ValueError("ISBN must be 10 or 13 digits")
        return v


class BookUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    author: Optional[str] = Field(None, min_length=1, max_length=255)
    isbn: Optional[str] = Field(None, max_length=20)
    genre: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=5000)
    total_copies: Optional[int] = Field(None, ge=1, le=1000)
    published_year: Optional[int] = Field(None, ge=1000, le=2100)
    is_active: Optional[bool] = None


class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    isbn: Optional[str]
    genre: Optional[str]
    description: Optional[str]
    total_copies: int
    available_copies: int
    published_year: Optional[int]
    is_available: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BookSummary(BaseModel):
    """Lightweight book info for embedding in other responses."""
    id: int
    title: str
    author: str
    isbn: Optional[str]
    genre: Optional[str]
    is_available: bool

    model_config = {"from_attributes": True}


class BookFilter(BaseModel):
    """Query filters for listing books."""
    author: Optional[str] = None
    genre: Optional[str] = None
    available_only: bool = False
    search: Optional[str] = Field(None, description="Search by title or author")
    published_year: Optional[int] = None
