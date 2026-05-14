"""
app/middleware/metrics_middleware.py  — Task 3: Prometheus Metrics Collection
=============================================================================
Collects HTTP request metrics for every request:
  - Request count (by method, endpoint, status code)
  - Request duration histogram (by method, endpoint)
  - Active request gauge (concurrent requests)

Also registers the /metrics endpoint using prometheus_client.
"""

import time
import re
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app, REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    ACTIVE_REQUESTS,
    ERRORS_TOTAL,
    AUTH_EVENTS,
)
from app.core.logger import logger


# ─── Path normalization ────────────────────────────────────────────────────────
# Replace path params like /books/42 → /books/{id} to avoid high cardinality

_PARAM_PATTERNS = [
    (re.compile(r"/\d+"), "/{id}"),
]


def _normalize_path(path: str) -> str:
    for pattern, replacement in _PARAM_PATTERNS:
        path = pattern.sub(replacement, path)
    return path


# ─── Metrics Middleware ───────────────────────────────────────────────────────

class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Collect Prometheus metrics for every HTTP request."""

    SKIP_PATHS = {"/metrics", "/health", "/docs", "/redoc", "/openapi.json", "/"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip internal/meta paths
        if path in self.SKIP_PATHS:
            return await call_next(request)

        method = request.method
        normalized_path = _normalize_path(path)

        ACTIVE_REQUESTS.inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            ACTIVE_REQUESTS.dec()
            ERRORS_TOTAL.labels(
                error_type=type(exc).__name__,
                endpoint=normalized_path,
            ).inc()
            raise

        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)

        # Record metrics
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=normalized_path,
            status_code=status_code,
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=method,
            endpoint=normalized_path,
        ).observe(duration)

        ACTIVE_REQUESTS.dec()

        # Track auth-specific events
        self._track_auth_events(path, method, response.status_code)

        return response

    def _track_auth_events(self, path: str, method: str, status_code: int) -> None:
        """Increment auth event counters based on endpoint and outcome."""
        if "/auth/login" in path:
            outcome = "success" if status_code == 200 else "failure"
            AUTH_EVENTS.labels(event_type="login", outcome=outcome).inc()
        elif "/auth/register" in path:
            outcome = "success" if status_code == 201 else "failure"
            AUTH_EVENTS.labels(event_type="register", outcome=outcome).inc()
        elif "/auth/refresh" in path:
            outcome = "success" if status_code == 200 else "failure"
            AUTH_EVENTS.labels(event_type="refresh", outcome=outcome).inc()


def setup_metrics(app: FastAPI) -> None:
    """
    Attach Prometheus metrics to the FastAPI app.
    Exposes the /metrics endpoint for Prometheus scraping.
    Also uses prometheus-fastapi-instrumentator for auto-instrumentation.
    """
    # Mount the /metrics ASGI app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    logger.info("Prometheus /metrics endpoint registered")
