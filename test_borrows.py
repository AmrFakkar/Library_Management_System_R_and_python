"""Tests for borrowing, returning, history, and all business rule enforcement."""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_token, auth_headers
from app.models.borrow_record import BorrowRecord, BorrowStatus
from app.models.book import Book
from app.core.security import hash_password
from app.models.user import User, UserRole


class TestBorrowBook:
    def test_borrow_available_book(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={
            "book_id": sample_book.id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["book_id"] == sample_book.id
        assert data["user_id"] == member_user.id
        assert data["status"] == "active"
        assert data["due_date"] is not None

    def test_borrow_unavailable_book(self, client: TestClient, member_user, unavailable_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={
            "book_id": unavailable_book.id,
        })
        assert resp.status_code == 409
        assert "unavailable" in resp.json()["detail"].lower()

    def test_borrow_nonexistent_book(self, client: TestClient, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={
            "book_id": 99999,
        })
        assert resp.status_code == 404

    def test_borrow_decrements_available_copies(self, client: TestClient, member_user, sample_book, db):
        token = get_token(client, "member@library.com", "Member1234")
        initial_copies = sample_book.available_copies
        client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        db.refresh(sample_book)
        assert sample_book.available_copies == initial_copies - 1

    def test_prevent_duplicate_active_borrow(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        # First borrow
        r1 = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        assert r1.status_code == 201
        # Second borrow of same book
        r2 = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        assert r2.status_code == 409

    def test_borrow_limit_enforcement(self, client: TestClient, member_user, db):
        """Cannot borrow more than MAX_BORROWED_BOOKS (5 by default)."""
        from app.core.config import settings
        token = get_token(client, "member@library.com", "Member1234")

        # Create enough books
        for i in range(settings.MAX_BORROWED_BOOKS + 1):
            book = Book(title=f"Limit Book {i}", author="Author", total_copies=2, available_copies=2)
            db.add(book)
        db.commit()
        db.expire_all()

        books = db.query(Book).filter(Book.title.like("Limit Book%")).all()

        # Borrow up to the limit
        for i in range(settings.MAX_BORROWED_BOOKS):
            r = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": books[i].id})
            assert r.status_code == 201, f"Borrow {i+1} failed: {r.text}"

        # One more should fail
        r = client.post(
            "/api/v1/borrows",
            headers=auth_headers(token),
            json={"book_id": books[settings.MAX_BORROWED_BOOKS].id},
        )
        assert r.status_code == 409
        assert "limit" in r.json()["detail"].lower()


class TestReturnBook:
    def test_return_borrowed_book(self, client: TestClient, member_user, sample_book, db):
        token = get_token(client, "member@library.com", "Member1234")
        # Borrow first
        borrow_resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        record_id = borrow_resp.json()["id"]

        # Return
        resp = client.post(f"/api/v1/borrows/{record_id}/return", headers=auth_headers(token), json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "returned"
        assert data["returned_at"] is not None

    def test_return_restores_available_copies(self, client: TestClient, member_user, sample_book, db):
        token = get_token(client, "member@library.com", "Member1234")
        initial = sample_book.available_copies

        borrow_resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        record_id = borrow_resp.json()["id"]
        client.post(f"/api/v1/borrows/{record_id}/return", headers=auth_headers(token), json={})

        db.refresh(sample_book)
        assert sample_book.available_copies == initial

    def test_cannot_return_already_returned(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        borrow_resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        record_id = borrow_resp.json()["id"]
        client.post(f"/api/v1/borrows/{record_id}/return", headers=auth_headers(token), json={})
        # Return again
        resp = client.post(f"/api/v1/borrows/{record_id}/return", headers=auth_headers(token), json={})
        assert resp.status_code == 409

    def test_member_cannot_return_others_book(self, client: TestClient, member_user, admin_user, sample_book, db):
        # Admin borrows
        admin_token = get_token(client, "admin@library.com", "Admin1234")
        borrow_resp = client.post("/api/v1/borrows", headers=auth_headers(admin_token), json={"book_id": sample_book.id})
        record_id = borrow_resp.json()["id"]

        # Member tries to return admin's book
        member_token = get_token(client, "member@library.com", "Member1234")
        resp = client.post(f"/api/v1/borrows/{record_id}/return", headers=auth_headers(member_token), json={})
        assert resp.status_code == 403

    def test_admin_can_return_any_book(self, client: TestClient, member_user, admin_user, sample_book):
        # Member borrows
        member_token = get_token(client, "member@library.com", "Member1234")
        borrow_resp = client.post("/api/v1/borrows", headers=auth_headers(member_token), json={"book_id": sample_book.id})
        record_id = borrow_resp.json()["id"]

        # Admin returns
        admin_token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post(f"/api/v1/borrows/{record_id}/return", headers=auth_headers(admin_token), json={})
        assert resp.status_code == 200


class TestBorrowHistory:
    def test_member_sees_own_history(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        resp = client.get("/api/v1/borrows", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for record in data["items"]:
            assert record["user_id"] == member_user.id

    def test_admin_sees_all_records(self, client: TestClient, admin_user, member_user, sample_book):
        # Member borrows
        member_token = get_token(client, "member@library.com", "Member1234")
        client.post("/api/v1/borrows", headers=auth_headers(member_token), json={"book_id": sample_book.id})

        # Admin lists all
        admin_token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/borrows", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_filter_by_status(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
        resp = client.get("/api/v1/borrows?status=active", headers=auth_headers(token))
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "active"

    def test_user_history_endpoint(self, client: TestClient, member_user, admin_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})

        admin_token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get(f"/api/v1/borrows/users/{member_user.id}/history", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_mark_overdue_admin_only(self, client: TestClient, admin_user, member_user):
        admin_token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/borrows/admin/mark-overdue", headers=auth_headers(admin_token))
        assert resp.status_code == 200

        member_token = get_token(client, "member@library.com", "Member1234")
        resp2 = client.post("/api/v1/borrows/admin/mark-overdue", headers=auth_headers(member_token))
        assert resp2.status_code == 403
