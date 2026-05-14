"""tests/test_users.py -- Task 4: User CRUD & Role Restriction Tests"""
import pytest
from tests.conftest import get_token, auth_headers


class TestUserList:
    def test_admin_can_list_users(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/users", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_member_cannot_list_users(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.get("/api/v1/users", headers=auth_headers(token)).status_code == 403

    def test_list_users_pagination(self, client, admin_user, db):
        from app.models.user import User, UserRole
        from app.core.security import hash_password
        for i in range(12):
            db.add(User(full_name=f"User {i}", email=f"u{i}@test.com",
                        hashed_password=hash_password("Pass1234"), role=UserRole.member))
        db.commit()
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/users?page=1&page_size=5", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["total_pages"] >= 3

    def test_filter_users_by_role(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/users?role=admin", headers=auth_headers(token))
        assert resp.status_code == 200
        for u in resp.json()["items"]:
            assert u["role"] == "admin"

    def test_filter_users_by_active(self, client, admin_user, inactive_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/users?is_active=false", headers=auth_headers(token))
        assert resp.status_code == 200
        for u in resp.json()["items"]:
            assert u["is_active"] is False

    def test_search_users_by_name(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get("/api/v1/users?search=Member", headers=auth_headers(token))
        assert resp.status_code == 200
        assert any("Member" in u["full_name"] for u in resp.json()["items"])


class TestUserProfile:
    def test_member_can_view_own_profile(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get(f"/api/v1/users/{member_user.id}", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == member_user.id

    def test_member_cannot_view_others_profile(self, client, member_user, admin_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.get(f"/api/v1/users/{admin_user.id}", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_admin_can_view_any_profile(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.get(f"/api/v1/users/{member_user.id}", headers=auth_headers(token))
        assert resp.status_code == 200

    def test_get_nonexistent_user_returns_404(self, client, admin_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        assert client.get("/api/v1/users/99999", headers=auth_headers(token)).status_code == 404


class TestUserUpdate:
    def test_member_can_update_own_name(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.put(f"/api/v1/users/{member_user.id}", headers=auth_headers(token),
                          json={"full_name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    def test_member_cannot_update_others(self, client, member_user, admin_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.put(f"/api/v1/users/{admin_user.id}", headers=auth_headers(token),
                          json={"full_name": "Hacked"})
        assert resp.status_code == 403

    def test_member_cannot_change_own_role(self, client, member_user):
        token = get_token(client, "member@library.com", "Member1234")
        resp = client.put(f"/api/v1/users/{member_user.id}", headers=auth_headers(token),
                          json={"role": "admin"})
        assert resp.status_code == 403

    def test_admin_can_change_user_role(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.put(f"/api/v1/users/{member_user.id}", headers=auth_headers(token),
                          json={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_update_duplicate_email_rejected(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.put(f"/api/v1/users/{member_user.id}", headers=auth_headers(token),
                          json={"email": "admin@library.com"})
        assert resp.status_code == 409


class TestUserDelete:
    def test_admin_can_delete_user(self, client, admin_user, member_user):
        token = get_token(client, "admin@library.com", "Admin1234")
        resp = client.delete(f"/api/v1/users/{member_user.id}", headers=auth_headers(token))
        assert resp.status_code == 200
        assert client.get(f"/api/v1/users/{member_user.id}", headers=auth_headers(token)).status_code == 404

    def test_member_cannot_delete_users(self, client, member_user, admin_user):
        token = get_token(client, "member@library.com", "Member1234")
        assert client.delete(f"/api/v1/users/{admin_user.id}", headers=auth_headers(token)).status_code == 403
