"""
app/core/logger.py  — Task 3: Structured Logging
================================================
Implements:
  - Console output: colorized, human-readable (development)
  - File output:    JSON-structured (production, ELK-compatible)
  - Log rotation:   10 MB per file, 30-day retention, gzip compression
  - Async-safe:     enqueue=True for thread/async safety
  - Log levels:     DEBUG, INFO, WARNING, ERROR, CRITICAL used appropriately

Log Format (JSON file):
  {
    "text": "...",
    "record": {
      "time": "2024-01-01T12:00:00.000Z",
      "level": {"name": "INFO"},
      "name": "app.routes.books",
      "function": "list_books",
      "line": 42,
      "message": "Listed books: page=1 total=50",
      "extra": {}
    }
  }

Usage throughout the app:
  from app.core.logger import logger
  logger.info("User logged in: {email}", email=user.email)
  logger.warning("Cache miss for key: {key}", key=cache_key)
  logger.error("DB error: {error}", error=str(e))
  logger.exception("Unhandled error")   # Includes full traceback
"""

import sys
import os
from loguru import logger
from app.core.config import settings

# ─── Setup ────────────────────────────────────────────────────────────────────

# Remove the default loguru handler
logger.remove()

# Ensure log directory exists
os.makedirs(os.path.dirname(settings.LOG_FILE) if "/" in settings.LOG_FILE else "logs", exist_ok=True)


# ─── Console Handler ──────────────────────────────────────────────────────────
# Human-readable, colorized output for development
logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL,
    colorize=True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <9}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>\n"
        "  <level>{message}</level>"
    ),
    backtrace=False,
    diagnose=False,
)


# ─── File Handler (JSON — ELK/Kibana compatible) ──────────────────────────────
logger.add(
    settings.LOG_FILE,
    level=settings.LOG_LEVEL,
    rotation="10 MB",        # New file every 10 MB
    retention="30 days",     # Keep logs for 30 days
    compression="zip",       # Compress rotated logs
    serialize=True,          # JSON format (ELK-compatible)
    enqueue=True,            # Thread/async safe (non-blocking)
    backtrace=True,          # Include stack trace on errors
    diagnose=True,           # Include variable values in tracebacks
)


# ─── Error-Only File Handler ──────────────────────────────────────────────────
# Separate file for ERROR and CRITICAL — easier alerting
error_log = settings.LOG_FILE.replace(".log", ".errors.log")
logger.add(
    error_log,
    level="ERROR",
    rotation="5 MB",
    retention="90 days",
    compression="zip",
    serialize=True,
    enqueue=True,
    backtrace=True,
    diagnose=True,
)


# ─── Context binding helpers ──────────────────────────────────────────────────

def get_request_logger(request_id: str, user_id: int = None, endpoint: str = None):
    """
    Return a logger bound with request-level context.
    Use in route handlers for correlated log entries.

    Example:
        log = get_request_logger(request_id, user_id=current_user.id)
        log.info("Book borrowed successfully")
        # → {"message": "Book borrowed", "request_id": "abc123", "user_id": 42}
    """
    return logger.bind(
        request_id=request_id,
        user_id=user_id,
        endpoint=endpoint,
    )


__all__ = ["logger", "get_request_logger"]
