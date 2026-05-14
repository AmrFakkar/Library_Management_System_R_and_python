"""
tests/test_caching.py  -- Task 3: Redis Cache Behaviour Tests
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from tests.conftest import get_token, auth_headers


class TestCacheAsidePattern:
    def test_first_request_is_cache_miss(self, client, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        with patch("app.core.cache.cache_get", return_value=None) as mock_get, \
             patch("app.core.cache.cache_set") as mock_set:
            resp = client.get(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
            assert resp.status_code == 200
            mock_get.assert_called_once()
            mock_set.assert_called_once()

    def test_second_request_is_cache_hit(self, client, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        from app.schemas.book import BookResponse
        cached_data = BookResponse.model_validate(sample_book).model_dump(mode="json")
        with patch("app.core.cache.cache_get", return_value=cached_data) as mock_get:
            resp = client.get(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
            assert resp.status_code == 200
            mock_get.assert_called_once()

    def test_cache_invalidated_on_book_update(self, client, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        with patch("app.core.cache.cache_delete") as mock_del, \
             patch("app.core.cache.cache_delete_pattern") as mock_pat:
            resp = client.put(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token), json={"title": "Updated"})
            assert resp.status_code == 200
            mock_del.assert_any_call(f"books:{sample_book.id}")
            mock_pat.assert_any_call("books:list:*")

    def test_cache_invalidated_on_book_delete(self, client, admin_user, sample_book):
        token = get_token(client, "admin@library.com", "Admin1234")
        with patch("app.core.cache.cache_delete") as mock_del, \
             patch("app.core.cache.cache_delete_pattern"):
            resp = client.delete(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
            assert resp.status_code == 200
            mock_del.assert_any_call(f"books:{sample_book.id}")

    def test_cache_invalidated_on_book_create(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        with patch("app.core.cache.cache_delete_pattern") as mock_pat:
            resp = client.post("/api/v1/books", headers=auth_headers(token), json={"title": "New", "author": "Auth", "total_copies": 1})
            assert resp.status_code == 201
            mock_pat.assert_any_call("books:list:*")

    def test_cache_invalidated_on_borrow(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        with patch("app.core.cache.cache_delete") as mock_del, \
             patch("app.core.cache.cache_delete_pattern") as mock_pat:
            resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
            assert resp.status_code == 201
            mock_del.assert_any_call(f"books:{sample_book.id}")
            mock_pat.assert_any_call("books:list:*")

    def test_cache_invalidated_on_return(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        borrow_id = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id}).json()["id"]
        with patch("app.core.cache.cache_delete") as mock_del, \
             patch("app.core.cache.cache_delete_pattern"):
            resp = client.post(f"/api/v1/borrows/{borrow_id}/return", headers=auth_headers(token), json={})
            assert resp.status_code == 200
            mock_del.assert_any_call(f"books:{sample_book.id}")


class TestCacheGracefulDegradation:
    def test_books_list_works_without_redis(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        with patch("app.core.cache.get_redis", return_value=None):
            resp = client.get("/api/v1/books", headers=auth_headers(token))
            assert resp.status_code == 200

    def test_book_get_works_without_redis(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        with patch("app.core.cache.get_redis", return_value=None):
            resp = client.get(f"/api/v1/books/{sample_book.id}", headers=auth_headers(token))
            assert resp.status_code == 200

    def test_borrow_works_without_redis(self, client, member_user, sample_book):
        token = get_token(client, "member@library.com", "Member1234")
        with patch("app.core.cache.get_redis", return_value=None):
            resp = client.post("/api/v1/borrows", headers=auth_headers(token), json={"book_id": sample_book.id})
            assert resp.status_code == 201


class TestMonitoringEndpoints:
    def test_stats_requires_admin(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.get("/api/v1/monitoring/stats", headers=auth_headers(token)).status_code == 403

    def test_stats_accessible_by_admin(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/monitoring/stats", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "library" in data and "cache" in data and "infrastructure" in data

    def test_stats_library_fields_correct(self, client, admin_user, sample_book, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        lib = client.get("/api/v1/monitoring/stats", headers=auth_headers(token)).json()["library"]
        assert lib["total_books"] >= 1
        assert lib["total_users"] >= 1

    def test_detailed_health_public(self, client):
        resp = client.get("/api/v1/monitoring/health/detailed")
        assert resp.status_code == 200
        assert "status" in resp.json()
        assert "database" in resp.json()["dependencies"]

    def test_dashboard_returns_html(self, client):
        resp = client.get("/api/v1/monitoring/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Library" in resp.text

    def test_cache_flush_requires_admin(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.post("/api/v1/monitoring/cache/flush", headers=auth_headers(token)).status_code == 403

    def test_logs_requires_admin(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.get("/api/v1/monitoring/logs/recent", headers=auth_headers(token)).status_code == 403


class TestCacheKeyHelpers:
    def test_make_list_key_deterministic(self):
        from app.core.cache import make_list_key
        assert make_list_key("books", page=1, page_size=10) == make_list_key("books", page=1, page_size=10)

    def test_make_list_key_varies_with_params(self):
        from app.core.cache import make_list_key
        assert make_list_key("books", page=1) != make_list_key("books", page=2)

    def test_make_list_key_has_correct_prefix(self):
        from app.core.cache import make_list_key
        assert make_list_key("books", page=1).startswith("books:list:")
