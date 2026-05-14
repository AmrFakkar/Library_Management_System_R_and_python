"""
app/main.py  -- Task 3 Integration Patch
=========================================
Shows how to add Task 3 components (Prometheus metrics, monitoring routes)
into the main FastAPI app from Task 1.

Changes to make in app/main.py:
  1. Import PrometheusMetricsMiddleware and setup_metrics
  2. Import monitoring_router
  3. Add middleware
  4. Register /metrics endpoint
  5. Include monitoring_router
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.logger import logger
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.auth_middleware import AuthEventLoggingMiddleware        # Task 2
from app.middleware.metrics_middleware import PrometheusMetricsMiddleware, setup_metrics  # Task 3
from app.middleware.error_handlers import register_exception_handlers
from app.routes import (
    auth_router,
    users_router,
    books_router,
    borrows_router,
    health_router,
)
from app.routes.monitoring import router as monitoring_router                # Task 3


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    logger.info("Application ready")
    yield
    logger.info(f"{settings.APP_NAME} shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Library Management System API",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware (order matters: outermost runs first) ──────────────────────
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RequestLoggingMiddleware)           # Task 1
    app.add_middleware(AuthEventLoggingMiddleware)         # Task 2
    app.add_middleware(PrometheusMetricsMiddleware)        # Task 3 ← NEW

    # ── Exception handlers ────────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Prometheus /metrics endpoint ──────────────────────────────────────────
    setup_metrics(app)                                    # Task 3 ← NEW

    # ── Routes ───────────────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(users_router, prefix=API_PREFIX)
    app.include_router(books_router, prefix=API_PREFIX)
    app.include_router(borrows_router, prefix=API_PREFIX)
    app.include_router(monitoring_router, prefix=API_PREFIX)  # Task 3 ← NEW

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "name": settings.APP_NAME,
            "docs": "/docs",
            "health": "/api/v1/health",
            "metrics": "/metrics",
            "dashboard": "/api/v1/monitoring/dashboard",
        }

    return app


app = create_app()
