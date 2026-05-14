# 🔗 How to Integrate All 4 Tasks Into One Project

Each task folder contains files that **replace or extend** files from Task 1.
Follow these steps to assemble the complete working project.

---

## Step 1 — Start with Task 1 (Core System)

Task 1 is the **base project**. Use it as-is. It already runs end-to-end.

```
task1_core/   ← This is your main project folder
```

---

## Step 2 — Apply Task 2 (JWT Auth + RBAC)

Copy these files into `task1_core/`, replacing existing ones:

| Source (task2_auth/)               | Destination (task1_core/)                    |
|-----------------------------------|----------------------------------------------|
| `app/core/security.py`            | `app/core/security.py`  ← replace            |
| `app/core/token_blacklist.py`     | `app/core/token_blacklist.py` ← new file     |
| `app/core/config.py`              | `app/core/config.py` ← replace (adds REFRESH_TOKEN_EXPIRE_DAYS) |
| `app/routes/auth.py`              | `app/routes/auth.py` ← replace              |
| `app/schemas/user.py`             | `app/schemas/user.py` ← replace (adds RefreshRequest, PasswordChangeRequest) |
| `app/middleware/auth_middleware.py` | `app/middleware/auth_middleware.py` ← new   |
| `app/main.py`                     | `app/main.py` ← replace (adds AuthEventLoggingMiddleware) |
| `tests/test_auth_full.py`         | `tests/test_auth_full.py` ← new test file   |

Also add to `.env`:
```
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## Step 3 — Apply Task 3 (Caching + Monitoring)

Copy these files into `task1_core/`, replacing existing ones:

| Source (task3_caching_monitoring/) | Destination (task1_core/)                   |
|-----------------------------------|----------------------------------------------|
| `app/core/cache.py`               | `app/core/cache.py` ← replace (adds make_list_key, cache_get_or_set, stats) |
| `app/core/logger.py`              | `app/core/logger.py` ← replace (adds error log file, context binding) |
| `app/core/metrics.py`             | `app/core/metrics.py` ← new file            |
| `app/routes/monitoring.py`        | `app/routes/monitoring.py` ← new file       |
| `app/middleware/metrics_middleware.py` | `app/middleware/metrics_middleware.py` ← new |
| `app/main.py`                     | `app/main.py` ← replace (adds Prometheus + monitoring router) |
| `monitoring/prometheus.yml`       | `monitoring/prometheus.yml` ← replace       |
| `monitoring/grafana/`             | `monitoring/grafana/` ← replace entire dir  |
| `tests/test_caching.py`           | `tests/test_caching.py` ← new test file     |

Also register the monitoring router in `app/routes/__init__.py`:
```python
from app.routes.monitoring import router as monitoring_router
```

Add to `requirements.txt`:
```
prometheus-client==0.20.0
prometheus-fastapi-instrumentator==6.1.0
```

---

## Step 4 — Apply Task 4 (Testing)

Copy these files into `task1_core/`, replacing existing test files:

| Source (task4_testing/)        | Destination (task1_core/)          |
|--------------------------------|------------------------------------|
| `tests/conftest.py`            | `tests/conftest.py` ← replace (richer fixtures) |
| `tests/test_auth.py`           | `tests/test_auth.py` ← replace     |
| `tests/test_books.py`          | `tests/test_books.py` ← replace    |
| `tests/test_borrows.py`        | `tests/test_borrows.py` ← replace  |
| `tests/test_users.py`          | `tests/test_users.py` ← new file   |
| `tests/test_edge_cases.py`     | `tests/test_edge_cases.py` ← new   |
| `tests/test_health.py`         | `tests/test_health.py` ← new file  |
| `pytest.ini`                   | `pytest.ini` ← replace             |
| `pyproject.toml`               | `pyproject.toml` ← new file        |

---

## Final Project Structure (after integration)

```
task1_core/               ← final integrated project
├── app/
│   ├── core/
│   │   ├── config.py     (T1+T2)
│   │   ├── database.py   (T1)
│   │   ├── security.py   (T2)
│   │   ├── token_blacklist.py (T2)
│   │   ├── cache.py      (T1+T3)
│   │   ├── logger.py     (T1+T3)
│   │   └── metrics.py    (T3)
│   ├── models/           (T1)
│   ├── schemas/
│   │   └── user.py       (T1+T2)
│   ├── services/         (T1)
│   ├── routes/
│   │   ├── auth.py       (T2)
│   │   ├── books.py      (T1)
│   │   ├── borrows.py    (T1)
│   │   ├── users.py      (T1)
│   │   ├── health.py     (T1)
│   │   └── monitoring.py (T3)
│   ├── middleware/
│   │   ├── logging_middleware.py (T1)
│   │   ├── error_handlers.py    (T1)
│   │   ├── auth_middleware.py   (T2)
│   │   └── metrics_middleware.py (T3)
│   └── main.py           (T1+T2+T3)
├── tests/
│   ├── conftest.py       (T4)
│   ├── test_auth.py      (T4)
│   ├── test_auth_full.py (T2)
│   ├── test_books.py     (T4)
│   ├── test_borrows.py   (T4)
│   ├── test_users.py     (T4)
│   ├── test_edge_cases.py (T4)
│   ├── test_health.py    (T4)
│   └── test_caching.py   (T3)
├── monitoring/           (T1+T3)
├── alembic/              (T1)
├── docker-compose.yml    (T1)
├── Dockerfile            (T1)
├── requirements.txt      (T1+T3)
├── seed.py               (T1)
└── pytest.ini / pyproject.toml (T4)
```

---

## Running the Final Integrated Project

```bash
# Docker (recommended)
docker-compose up --build
docker-compose exec api python seed.py

# Local
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # edit with your DB/Redis URLs
uvicorn app.main:app --reload

# Tests (no Docker needed)
pytest
pytest --cov=app --cov-report=term-missing
```

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/api/v1/health | Health check |
| http://localhost:8000/metrics | Prometheus metrics |
| http://localhost:8000/api/v1/monitoring/dashboard | Custom dashboard |
| http://localhost:9090 | Prometheus UI |
| http://localhost:3000 | Grafana (admin/admin) |
