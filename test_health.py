"""tests/test_health.py -- Task 4: Health & System Endpoint Tests"""
from tests.conftest import get_token, auth_headers


class TestHealthEndpoint:
    def test_health_publicly_accessible(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_response_fields(self, client):
        data = client.get("/api/v1/health").json()
        for field in ["status", "app_name", "version", "database", "redis", "timestamp"]:
            assert field in data

    def test_health_status_is_healthy_or_degraded(self, client):
        status = client.get("/api/v1/health").json()["status"]
        assert status in ("healthy", "degraded")

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "docs" in resp.json()

    def test_swagger_docs_accessible(self, client):
        assert client.get("/docs").status_code == 200

    def test_openapi_json_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
        assert "components" in data


class TestDetailedHealthEndpoint:
    def test_detailed_health_returns_dependencies(self, client):
        resp = client.get("/api/v1/monitoring/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert "dependencies" in data
        assert "database" in data["dependencies"]

    def test_detailed_health_db_ok(self, client):
        deps = client.get("/api/v1/monitoring/health/detailed").json()["dependencies"]
        assert deps["database"]["status"] == "ok"
        assert "latency_ms" in deps["database"]
