from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from jose import JWTError

from app.core.logger import logger


def _error_response(status_code: int, error: str, detail, request_id: str = None) -> JSONResponse:
    content = {"error": error, "detail": detail}
    if request_id:
        content["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    # ── 422 Validation errors (Pydantic) ──────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", None)
        errors = []
        for err in exc.errors():
            errors.append({
                "field": " → ".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            })
        logger.warning(
            f"[{request_id}] Validation error on {request.method} {request.url.path}: {errors}"
        )
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error="Validation Error",
            detail=errors,
            request_id=request_id,
        )

    # ── 409 Database integrity violations ─────────────────────────────────────
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        request_id = getattr(request.state, "request_id", None)
        logger.error(f"[{request_id}] DB IntegrityError: {exc.orig}")
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            error="Database Conflict",
            detail="A record with the provided data already exists or violates a constraint.",
            request_id=request_id,
        )

    # ── 503 Database connectivity issues ──────────────────────────────────────
    @app.exception_handler(OperationalError)
    async def db_operational_error_handler(request: Request, exc: OperationalError):
        request_id = getattr(request.state, "request_id", None)
        logger.critical(f"[{request_id}] DB OperationalError: {exc}")
        return _error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="Database Unavailable",
            detail="The database is temporarily unavailable. Please try again later.",
            request_id=request_id,
        )

    # ── 401 JWT errors ────────────────────────────────────────────────────────
    @app.exception_handler(JWTError)
    async def jwt_error_handler(request: Request, exc: JWTError):
        request_id = getattr(request.state, "request_id", None)
        logger.warning(f"[{request_id}] JWT error: {exc}")
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="Authentication Error",
            detail="Invalid or expired token",
            request_id=request_id,
        )

    # ── 500 Catch-all unhandled exceptions ────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            f"[{request_id}] Unhandled exception on "
            f"{request.method} {request.url.path}: {exc}"
        )
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="Internal Server Error",
            detail="An unexpected error occurred. Please contact support.",
            request_id=request_id,
        )
