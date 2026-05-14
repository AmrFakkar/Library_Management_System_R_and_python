"""
tests/conftest.py -- Task 4: Shared Fixtures
All tests use an isolated in-memory SQLite database.
No external services (PostgreSQL, Redis) required.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.book import Book
from app.models.borrow_record import BorrowRecord, BorrowStatus
from datetime import datetime, timezone, timedelta

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_user(db):
    u = User(full_name="Admin User", email="admin@library.com",
             hashed_password=hash_password("Admin1234"), role=UserRole.admin, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def member_user(db):
    u = User(full_name="Member User", email="member@library.com",
             hashed_password=hash_password("Member1234"), role=UserRole.member, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def member_user_2(db):
    u = User(full_name="Second Member", email="member2@library.com",
             hashed_password=hash_password("Member1234"), role=UserRole.member, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def inactive_user(db):
    u = User(full_name="Inactive User", email="inactive@library.com",
             hashed_password=hash_password("Member1234"), role=UserRole.member, is_active=False)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def sample_book(db):
    b = Book(title="Clean Code", author="Robert C. Martin", isbn="978-0132350884",
             genre="Technology", total_copies=3, available_copies=3, published_year=2008)
    db.add(b); db.commit(); db.refresh(b)
    return b


@pytest.fixture
def sample_book_2(db):
    b = Book(title="The Pragmatic Programmer", author="David Thomas", isbn="978-0135957059",
             genre="Technology", total_copies=2, available_copies=2, published_year=2019)
    db.add(b); db.commit(); db.refresh(b)
    return b


@pytest.fixture
def unavailable_book(db):
    b = Book(title="Fully Borrowed", author="Author", total_copies=1, available_copies=0)
    db.add(b); db.commit(); db.refresh(b)
    return b


@pytest.fixture
def fiction_book(db):
    b = Book(title="Dune", author="Frank Herbert", isbn="978-0441013593",
             genre="Science Fiction", total_copies=2, available_copies=2, published_year=1965)
    db.add(b); db.commit(); db.refresh(b)
    return b


@pytest.fixture
def overdue_borrow(db, member_user, sample_book):
    """A borrow record that is already overdue."""
    past_due = datetime.now(timezone.utc) - timedelta(days=5)
    record = BorrowRecord(
        user_id=member_user.id, book_id=sample_book.id,
        status=BorrowStatus.overdue,
        borrowed_at=datetime.now(timezone.utc) - timedelta(days=20),
        due_date=past_due,
    )
    sample_book.available_copies -= 1
    db.add(record); db.commit(); db.refresh(record)
    return record


def get_token(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
