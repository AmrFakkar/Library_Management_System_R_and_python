"""
app/core/cache.py  — Task 3: Redis Caching (Cache-Aside Pattern)
================================================================
Implements:
  - Cache-aside (lazy loading): check cache → miss → DB → store → return
  - Cache invalidation: delete specific keys or wildcard patterns
  - TTL-based expiry (configurable per entity)
  - Graceful degradation: if Redis is down, requests fall through to DB
  - Cache statistics: hit/miss counters (stored in Redis itself)

Cache Key Conventions:
  books:<id>                    Single book
  books:list:<fingerprint>      Paginated book list (hashed params)
  users:<id>                    Single user
  users:list:<fingerprint>      Paginated user list
  borrows:list:<fingerprint>    Paginated borrow list
  blacklist:<token>             JWT blacklist entry
  revoked_user:<user_id>        User-level token revocation timestamp
  cache:stats:hits              Global cache hit counter
  cache:stats:misses            Global cache miss counter
"""

import json
import hashlib
from typing import Any, Optional
import redis as redis_lib
from app.core.config import settings
from app.core.logger import logger

# ─── Singleton Redis Client ────────────────────────────────────────────────────

_redis_client: Optional[redis_lib.Redis] = None


def get_redis() -> Optional[redis_lib.Redis]:
    """
    Return a Redis client singleton.
    Returns None if Redis is unavailable — enabling graceful degradation.
    """
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis_lib.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
            )
            _redis_client.ping()
            logger.info(f"Redis connected: {settings.REDIS_URL}")
        except Exception as e:
            logger.warning(f"Redis unavailable — caching disabled: {e}")
            _redis_client = None
    return _redis_client


def check_redis_connection() -> bool:
    client = get_redis()
    if not client:
        return False
    try:
        client.ping()
        return True
    except Exception:
        return False


# ─── Key Helpers ──────────────────────────────────────────────────────────────

def make_list_key(prefix: str, **params) -> str:
    """
    Build a deterministic cache key for a paginated/filtered list.
    Hashes all params to keep key length manageable.
    """
    param_str = json.dumps(params, sort_keys=True, default=str)
    fingerprint = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"{prefix}:list:{fingerprint}"


# ─── Core Cache Operations ────────────────────────────────────────────────────

def cache_get(key: str) -> Optional[Any]:
    """
    Cache-aside READ: retrieve a value from Redis.
    Returns deserialized Python object, or None on miss/error.
    Increments hit/miss counters.
    """
    client = get_redis()
    if not client:
        return None

    try:
        raw = client.get(key)
        if raw is not None:
            logger.debug(f"Cache HIT  → {key}")
            _increment_stat(client, "hits")
            return json.loads(raw)
        else:
            logger.debug(f"Cache MISS → {key}")
            _increment_stat(client, "misses")
            return None
    except Exception as e:
        logger.warning(f"cache_get error [{key}]: {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = settings.CACHE_TTL) -> bool:
    """
    Cache-aside WRITE: store a serialized value in Redis with TTL.
    Returns True on success, False on error/unavailability.
    """
    client = get_redis()
    if not client:
        return False

    try:
        serialized = json.dumps(value, default=str)
        client.setex(key, ttl, serialized)
        logger.debug(f"Cache SET  → {key} (ttl={ttl}s, size={len(serialized)}B)")
        return True
    except Exception as e:
        logger.warning(f"cache_set error [{key}]: {e}")
        return False


def cache_delete(key: str) -> bool:
    """Delete a specific cache key (used on update/delete)."""
    client = get_redis()
    if not client:
        return False
    try:
        deleted = client.delete(key)
        if deleted:
            logger.debug(f"Cache DEL  → {key}")
        return True
    except Exception as e:
        logger.warning(f"cache_delete error [{key}]: {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a glob pattern (e.g. 'books:list:*').
    Uses SCAN to avoid blocking Redis on large keysets.
    Returns count of deleted keys.
    """
    client = get_redis()
    if not client:
        return 0
    try:
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=pattern, count=100)
            if keys:
                client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        if deleted:
            logger.debug(f"Cache DEL pattern '{pattern}' → {deleted} keys removed")
        return deleted
    except Exception as e:
        logger.warning(f"cache_delete_pattern error [{pattern}]: {e}")
        return 0


def cache_get_or_set(key: str, fetch_fn, ttl: int = settings.CACHE_TTL) -> Any:
    """
    Full cache-aside helper:
      1. Try cache
      2. On miss: call fetch_fn() to get data from DB
      3. Store result in cache
      4. Return data

    fetch_fn should return a JSON-serializable value.
    """
    cached = cache_get(key)
    if cached is not None:
        return cached

    data = fetch_fn()
    if data is not None:
        cache_set(key, data, ttl)
    return data


# ─── Cache Statistics ─────────────────────────────────────────────────────────

def _increment_stat(client: redis_lib.Redis, stat: str) -> None:
    try:
        client.incr(f"cache:stats:{stat}")
    except Exception:
        pass


def get_cache_stats() -> dict:
    """Return cache hit/miss statistics from Redis."""
    client = get_redis()
    if not client:
        return {"available": False, "hits": 0, "misses": 0, "hit_rate": 0.0}

    try:
        hits = int(client.get("cache:stats:hits") or 0)
        misses = int(client.get("cache:stats:misses") or 0)
        total = hits + misses
        hit_rate = round(hits / total * 100, 2) if total > 0 else 0.0

        # Get memory usage
        info = client.info("memory")
        used_memory = info.get("used_memory_human", "N/A")

        # Count keys by type
        book_keys = len(client.keys("books:*"))
        user_keys = len(client.keys("users:*"))
        blacklist_keys = len(client.keys("blacklist:*"))

        return {
            "available": True,
            "hits": hits,
            "misses": misses,
            "total_requests": total,
            "hit_rate_percent": hit_rate,
            "memory_used": used_memory,
            "key_counts": {
                "books": book_keys,
                "users": user_keys,
                "blacklist": blacklist_keys,
            },
        }
    except Exception as e:
        logger.warning(f"get_cache_stats error: {e}")
        return {"available": False, "error": str(e)}


def flush_cache(pattern: str = "*") -> int:
    """Flush all cache keys (or by pattern). Admin use only."""
    if pattern == "*":
        client = get_redis()
        if not client:
            return 0
        try:
            client.flushdb()
            logger.warning("Cache FLUSH — entire Redis DB cleared")
            return -1  # Indicates full flush
        except Exception as e:
            logger.error(f"Cache flush failed: {e}")
            return 0
    else:
        return cache_delete_pattern(pattern)
