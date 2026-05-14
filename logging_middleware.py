import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every incoming request and outgoing response with:
    - HTTP method, path, status code
    - Response time in milliseconds
    - Unique request ID for tracing
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        # Attach request ID to request state for downstream use
        request.state.request_id = request_id

        logger.info(
            f"[{request_id}] → {request.method} {request.url.path}"
            + (f"?{request.url.query}" if request.url.query else "")
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[{request_id}] ✗ {request.method} {request.url.path} "
                f"UNHANDLED ERROR in {elapsed_ms:.1f}ms — {exc}"
            )
            raise

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code
        level = "info" if status_code < 400 else ("warning" if status_code < 500 else "error")

        getattr(logger, level)(
            f"[{request_id}] ← {request.method} {request.url.path} "
            f"HTTP {status_code} ({elapsed_ms:.1f}ms)"
        )

        # Attach request ID to response headers for client-side tracing
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        return response
