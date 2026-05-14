from datetime import datetime, timezone
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.cache import check_redis_connection
from app.schemas.common import HealthResponse
from app.core.logger import logger

router = APIRouter(prefix="/health", tags=["Health"])


def _check_db() -> str:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return "ok"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return f"error: {e}"


@router.get(
    "",
    response_model=HealthResponse,
    summary="System health check",
    description="Returns status of the application, database, and Redis.",
)
def health_check():
    db_status = _check_db()
    redis_status = "ok" if check_redis_connection() else "unavailable"

    overall = "healthy" if db_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        database=db_status,
        redis=redis_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
