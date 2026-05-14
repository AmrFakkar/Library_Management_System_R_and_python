"""Tests for book CRUD operations, filtering, and pagination."""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_token, auth_headers


class TestBookCRUD:
    def test_create_book_as_admin(self, client: TestClient, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={
            "title": "The Pragmatic Programmer",
            "author": "David Thomas",
            "isbn": "978-0135957059",
            "genre": "Technology",
            "total_copies": 2,
            "published_year": 2019,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "The Pragmatic Programmer"
        assert data["available_copies"] == 2
        assert data["is_available"] is True

    def test_create_book_as_member_forbidden(self, client: TestClient, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={
            "title": "Unauthorized Book",
            "author": "Someone",
        })
        assert resp.status_code == 403

    def test_create_book_duplicate_isbn(self, client: TestClient, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={
            "title": "Duplicate ISBN Book",
            "author": "Author",
            "isbn": "978-0132350884",  # same as sample_book
        })
        assert resp.status_code == 409

    def test_get_book_by_id(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_book.id

    def test_get_nonexistent_book(self, client: TestClient, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books/99999", headers=auth_headers(token))
        assert resp.status_code == 404

    def test_list_books(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    def test_update_book_as_admin(self, client: TestClient, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.put(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token), json={
            "title": "Clean Code — Updated Edition",
            "total_copies": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Clean Code — Updated Edition"
        assert data["total_copies"] == 5
        assert data["available_copies"] == 5  # was 3, added 2

    def test_delete_book_as_admin(self, client: TestClient, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.delete(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
        assert resp.status_code == 200
        # Verify it's gone
        resp2 = client.get(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
        assert resp2.status_code == 404

    def test_delete_book_as_member_forbidden(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.delete(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
        assert resp.status_code == 403


class TestBookFiltering:
    def test_filter_by_genre(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books?genre=Technology", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_filter_available_only(self, client: TestClient, member_user, sample_book, unavailable_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books?available_only=true", headers=auth_headers(token))
        assert resp.status_code == 200
        for book in resp.json()["items"]:
            assert book["is_available"] is True

    def test_search_by_title(self, client: TestClient, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books?search=Clean", headers=auth_headers(token))
        assert resp.status_code == 200
        assert any("Clean" in b["title"] for b in resp.json()["items"])

    def test_pagination(self, client: TestClient, admin_user, db):
        from app.models.book import Book
        # Create 15 books
        for i in range(15):
            db.add(Book(title=f"Book {i}", author="Author", total_copies=1, available_copies=1))
        db.commit()

        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/books?page=1&page_size=5", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["total"] == 15
        assert data["total_pages"] == 3
        assert data["has_next"] is True
        assert data["has_prev"] is False

    def test_pagination_page_2(self, client: TestClient, admin_user, db):
        from app.models.book import Book
        for i in range(15):
            db.add(Book(title=f"Paginated Book {i}", author="Author", total_copies=1, available_copies=1))
        db.commit()

        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/books?page=2&page_size=5", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_prev"] is True
        assert data["page"] == 2
