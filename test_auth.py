"""Tests for authentication: registration, login, token validation, protected routes."""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_token, auth_headers


class TestRegistration:
    def test_register_member_success(self, client: TestClient):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "password": "Password1",
            "role": "member",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "jane@example.com"
        assert data["role"] == "member"
        assert "hashed_password" not in data

    def test_register_admin_success(self, client: TestClient):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Admin Doe",
            "email": "admin2@example.com",
            "password": "AdminPass1",
            "role": "admin",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "admin"

    def test_register_duplicate_email(self, client: TestClient, member_user):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Dup User",
            "email": "member@library.com",
            "password": "Password1",
        })
        assert resp.status_code == 409

    def test_register_weak_password(self, client: TestClient):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Weak Pass",
            "email": "weak@example.com",
            "password": "nodigits",
        })
        assert resp.status_code == 422

    def test_register_invalid_email(self, client: TestClient):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Bad Email",
            "email": "not-an-email",
            "password": "Password1",
        })
        assert resp.status_code == 422

    def test_register_missing_fields(self, client: TestClient):
        resp = client.post("/api/v1/auth/register", json={"email": "x@x.com"})
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client: TestClient, member_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": "member@library.com",
            "password": "Member1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "member@library.com"

    def test_login_wrong_password(self, client: TestClient, member_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": "member@library.com",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient):
        resp = client.post("/api/v1/auth/login", json={
            "email": "ghost@example.com",
            "password": "SomePass1",
        })
        assert resp.status_code == 401

    def test_login_missing_fields(self, client: TestClient):
        resp = client.post("/api/v1/auth/login", json={"email": "a@a.com"})
        assert resp.status_code == 422


class TestProtectedRoutes:
    def test_get_me_authenticated(self, client: TestClient, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == "member@library.com"

    def test_get_me_unauthenticated(self, client: TestClient):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 403  # Missing Bearer scheme

    def test_get_me_invalid_token(self, client: TestClient):
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_admin_endpoint_blocked_for_member(self, client: TestClient, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get("/api/v1/users", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_admin_endpoint_accessible_for_admin(self, client: TestClient, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/users", headers=auth_headers(token))
        assert resp.status_code == 200
