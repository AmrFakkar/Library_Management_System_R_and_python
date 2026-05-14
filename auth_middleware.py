"""
app/middleware/auth_middleware.py  — Task 2: Auth Event Logging
===============================================================
Intercepts requests to auth-related endpoints and logs:
  - Login attempts (success / failure)
  - Token validation events
  - Logout events
  - Registration events
  - Suspicious patterns (repeated failures from same IP)

This is a passive logging middleware — it does NOT block requests.
Security enforcement is done in the route/dependency layer.
"""

import time
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import logger


# Simple in-memory tracker for failed login attempts per IP
# In production: replace with Redis for distributed rate-limiting
_failed_attempts: dict[str, list[float]] = defaultdict(list)
FAIL_WINDOW_SECONDS = 300   # 5 minutes
FAIL_THRESHOLD = 10          # Warn after 10 failures in the window


class AuthEventLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs authentication-related events with structured context.
    Tracks failed login attempts per IP and emits warnings on spikes.
    """

    # Auth endpoint paths to watch
    AUTH_PATHS = {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/me/password",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # Only instrument auth paths
        if path not in self.AUTH_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        request_id = getattr(request.state, "request_id", "?")
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        status_code = response.status_code

        # ── Structured auth event log ─────────────────────────────────────
        event = {
            "request_id": request_id,
            "event_type": self._classify(path, method),
            "endpoint": path,
            "method": method,
            "status_code": status_code,
            "client_ip": client_ip,
            "elapsed_ms": round(elapsed_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if status_code == 200 or status_code == 201:
            logger.info(f"AUTH_SUCCESS | {event}")
        elif status_code in (401, 403):
            logger.warning(f"AUTH_FAILURE | {event}")
            self._track_failure(client_ip, path)
        elif status_code >= 500:
            logger.error(f"AUTH_ERROR | {event}")
        else:
            logger.debug(f"AUTH_EVENT | {event}")

        return response

    def _classify(self, path: str, method: str) -> str:
        if "login" in path:
            return "LOGIN_ATTEMPT"
        if "register" in path:
            return "REGISTRATION"
        if "refresh" in path:
            return "TOKEN_REFRESH"
        if "logout-all" in path:
            return "LOGOUT_ALL"
        if "logout" in path:
            return "LOGOUT"
        if "password" in path:
            return "PASSWORD_CHANGE"
        return "AUTH_EVENT"

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, respecting X-Forwarded-For header."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _track_failure(self, ip: str, path: str) -> None:
        """Track failed auth attempts per IP, warn on threshold breach."""
        if "login" not in path and "refresh" not in path:
            return  # Only track login and refresh failures

        now = time.time()
        window_start = now - FAIL_WINDOW_SECONDS

        # Prune old entries
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > window_start]
        _failed_attempts[ip].append(now)

        count = len(_failed_attempts[ip])
        if count >= FAIL_THRESHOLD:
            logger.warning(
                f"BRUTE_FORCE_ALERT | IP={ip} has {count} failed auth attempts "
                f"in the last {FAIL_WINDOW_SECONDS}s — consider rate limiting"
            )
