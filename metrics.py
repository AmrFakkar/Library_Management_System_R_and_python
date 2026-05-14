"""
app/core/metrics.py  — Task 3: Prometheus Metrics
==================================================
Defines custom Prometheus metrics for the Library Management System.
These are collected by the metrics middleware and exposed at /metrics.

Metrics exposed:
  library_http_requests_total          Counter   — requests by method/path/status
  library_http_request_duration_seconds Histogram — response time by method/path
  library_active_requests              Gauge     — currently in-flight requests
  library_db_query_duration_seconds    Histogram — DB query latency
  library_cache_hits_total             Counter   — Redis cache hits
  library_cache_misses_total           Counter   — Redis cache misses
  library_books_borrowed_total         Counter   — total borrow operations
  library_books_returned_total         Counter   — total return operations
  library_auth_events_total            Counter   — auth events by type/status
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# ─── HTTP Metrics ──────────────────────────────────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "library_http_requests_total",
    "Total HTTP requests processed",
    labelnames=["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "library_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ACTIVE_REQUESTS = Gauge(
    "library_active_requests",
    "Number of HTTP requests currently being processed",
)

# ─── Database Metrics ─────────────────────────────────────────────────────────

DB_QUERY_DURATION = Histogram(
    "library_db_query_duration_seconds",
    "Database query duration in seconds",
    labelnames=["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

# ─── Cache Metrics ────────────────────────────────────────────────────────────

CACHE_HITS = Counter(
    "library_cache_hits_total",
    "Total Redis cache hits",
    labelnames=["entity"],
)

CACHE_MISSES = Counter(
    "library_cache_misses_total",
    "Total Redis cache misses",
    labelnames=["entity"],
)

# ─── Business Metrics ─────────────────────────────────────────────────────────

BOOKS_BORROWED = Counter(
    "library_books_borrowed_total",
    "Total number of books borrowed",
)

BOOKS_RETURNED = Counter(
    "library_books_returned_total",
    "Total number of books returned",
)

AUTH_EVENTS = Counter(
    "library_auth_events_total",
    "Authentication events by type and outcome",
    labelnames=["event_type", "outcome"],  # event_type: login/register/refresh, outcome: success/failure
)

ERRORS_TOTAL = Counter(
    "library_errors_total",
    "Total application errors by type",
    labelnames=["error_type", "endpoint"],
)
