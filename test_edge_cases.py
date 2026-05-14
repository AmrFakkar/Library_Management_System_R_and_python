"""tests/test_edge_cases.py -- Task 4: Edge Cases, Validation & Error Handling"""
import pytest
from tests.conftest import get_token, auth_headers


class TestValidationErrors:
    def test_invalid_json_body(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers={**auth_headers(token), "Content-Type": "application/json"},
                           content=b"not-json{{{")
        assert resp.status_code == 422

    def test_book_total_copies_must_be_positive(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={"title": "Bad", "author": "Auth", "total_copies": 0})
        assert resp.status_code == 422

    def test_book_title_required(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={"author": "Auth"})
        assert resp.status_code == 422

    def test_book_author_required(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={"title": "Title"})
        assert resp.status_code == 422

    def test_pagination_page_must_be_positive(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books?page=0", headers=auth_headers(token))
        assert resp.status_code == 422

    def test_pagination_page_size_max_100(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books?page_size=101", headers=auth_headers(token))
        assert resp.status_code == 422

    def test_invalid_isbn_format(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={
            "title": "Bad ISBN", "author": "Auth", "isbn": "123"
        })
        assert resp.status_code == 422

    def test_published_year_out_of_range(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={
            "title": "Old", "author": "Auth", "published_year": 500
        })
        assert resp.status_code == 422


class TestNotFoundErrors:
    def test_borrow_nonexistent_book(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": 99999}).status_code == 404

    def test_return_nonexistent_record(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.post("/api/v1/borrows/99999/return", headers=auth_headers(token), json={}).status_code == 404

    def test_get_nonexistent_book(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.get("/api/v1/books/99999", headers=auth_headers(token)).status_code == 404

    def test_get_nonexistent_borrow(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.get("/api/v1/borrows/99999", headers=auth_headers(token)).status_code == 404


class TestConflictErrors:
    def test_register_duplicate_email(self, client, member_user):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Dup", "email": "member@library.com", "password": "Pass1234"
        })
        assert resp.status_code == 409

    def test_create_book_duplicate_isbn(self, client, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.post("/api/v1/books", headers=auth_headers(token), json={
            "title": "Another", "author": "Auth", "isbn": "978-0132350884"
        })
        assert resp.status_code == 409

    def test_borrow_unavailable_book(self, client, member_user, unavailable_book):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": unavailable_book.id}).status_code == 409

    def test_return_already_returned(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        bid = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id}).json()["id"]
        client.post(f"/api/v1/borrows/{bid}/return", headers=auth_headers(token), json={})
        assert client.post(f"/api/v1/borrows/{bid}/return", headers=auth_headers(token), json={}).status_code == 409

    def test_delete_book_with_active_borrow(self, client, admin_user, member_user, sample_book):
        member_token = get_token(client, "member@library.com", "Member1234")
        client.post("/api/v1/borrows", headers=auth_headers(member_token), json={"book_id": sample_book.id})
        admin_token = get_token(client, "admin@library.com", "Admin1234")
        assert client.delete(f"/api/v1/books/{sample_book.id}", headers=auth_headers(admin_token)).status_code == 409


class TestAuthErrors:
    def test_unauthenticated_request_rejected(self, client):
        assert client.get("/api/v1/books").status_code == 403

    def test_invalid_bearer_token_rejected(self, client):
        assert client.get("/api/v1/books", headers={"Authorization": "Bearer garbage"}).status_code == 401

    def test_missing_bearer_scheme(self, client):
        assert client.get("/api/v1/books", headers={"Authorization": "notbearer token"}).status_code == 403

    def test_wrong_login_password(self, client, member_user):
        assert client.post("/api/v1/auth/login", json={"email": "member@library.com", "password": "Wrong123"}).status_code == 401

    def test_login_nonexistent_user(self, client):
        assert client.post("/api/v1/auth/login", json={"email": "ghost@test.com", "password": "Pass1234"}).status_code == 401


class TestResponseFormat:
    def test_paginated_response_has_required_fields(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        data = client.get("/api/v1/books", headers=auth_headers(token)).json()
        for field in ["items", "total", "page", "page_size", "total_pages", "has_next", "has_prev"]:
            assert field in data, f"Missing field: {field}"

    def test_error_response_has_detail(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/books/99999", headers=auth_headers(token))
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_book_response_has_is_available(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        data = client.get(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token)).json()
        assert "is_available" in data
        assert data["is_available"] is True

    def test_borrow_response_includes_nested_book(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        data = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id}).json()
        assert "book" in data
        assert data["book"]["id"] == sample_book.id

    def test_token_response_has_required_fields(self, client, member_user):
        resp = client.post("/api/v1/auth/login", json={"email": "member@library.com", "password": "Member1234"})
        data = resp.json()
        for field in ["access_token", "token_type", "expires_in", "user"]:
            assert field in data


class TestCopiesAdjustment:
    def test_reduce_total_copies_blocked_if_all_borrowed(self, client, admin_user, member_user, sample_book, db):
        """Cannot reduce total_copies below the number currently borrowed."""
        # sample_book has 3 total, 3 available. Borrow all 3.
        from app.core.security import hash_password
        from app.models.user import User, UserRole
        tokens = []
        for i in range(3):
            u = User(full_name=f"U{i}", email=f"u{i}@borrow.com",
                     hashed_password=hash_password("Pass1234"), role=UserRole.member)
            db.add(u); db.commit(); db.refresh(u)
            t = get_token(client, f"u{i}@borrow.com", "Pass1234")
            r = client.post("/api/v1/borrows", headers=auth_headers(t), json={"book_id": sample_book.id})
            assert r.status_code == 201

        admin_token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.put(f"/api/v1/books/{sample_book.id}", headers=auth_headers(admin_token),
                          json={"total_copies": 2})
        assert resp.status_code == 400

    def test_increase_total_copies_increases_available(self, client, admin_user, sample_book, db):
        admin_token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.put(f"/api/v1/books/{sample_book.id}", headers=auth_headers(admin_token),
                          json={"total_copies": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_copies"] == 5
        assert data["available_copies"] == 5
