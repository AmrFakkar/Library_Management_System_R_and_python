"""
app/core/token_blacklist.py  — Task 2: JWT Token Blacklisting
=============================================================
When a user logs out, their access token is added to a Redis blacklist
with a TTL equal to the token's remaining lifetime. This prevents reuse
of valid-but-revoked tokens without requiring a stateful session store.

Pattern: Redis SET with expiry
  Key:   blacklist:<token>
  Value: "1"
  TTL:   remaining seconds until token natural expiry
"""

from datetime import datetime, timezone
from typing import Optional
from jose import jwt, JWTError

from app.core.config import settings
from app.core.logger import logger


def _get_token_remaining_ttl(token: str) -> int:
    """
    Decode the token (without verifying expiry) and compute
    how many seconds remain until it naturally expires.
    Returns 0 if already expired or undecodable.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},   # We only want the exp claim
        )
        exp = payload.get("exp")
        if exp is None:
            return 0
        remaining = int(exp) - int(datetime.now(timezone.utc).timestamp())
        return max(remaining, 0)
    except JWTError:
        return 0


def blacklist_token(token: str) -> bool:
    """
    Add a token to the blacklist.
    The entry automatically expires when the token would have expired.
    Returns True if successful, False if Redis is unavailable.
    """
    from app.core.cache import get_redis
    client = get_redis()
    if not client:
        logger.warning("Redis unavailable — token blacklist not enforced on logout")
        return False

    ttl = _get_token_remaining_ttl(token)
    if ttl <= 0:
        logger.debug("Token already expired — skipping blacklist")
        return True  # No need to store an already-expired token

    key = f"blacklist:{token}"
    try:
        client.setex(key, ttl, "1")
        logger.info(f"Token blacklisted (TTL={ttl}s)")
        return True
    except Exception as e:
        logger.error(f"Failed to blacklist token: {e}")
        return False


def is_token_blacklisted(token: str) -> bool:
    """
    Check if a token is in the blacklist.
    Returns False (not blacklisted) if Redis is unavailable — fail open
    to avoid locking out users due to Redis downtime.
    """
    from app.core.cache import get_redis
    client = get_redis()
    if not client:
        return False

    try:
        return client.exists(f"blacklist:{token}") == 1
    except Exception as e:
        logger.warning(f"Blacklist check failed: {e}")
        return False


def blacklist_all_user_tokens(user_id: int) -> int:
    """
    Blacklist ALL active tokens for a user by storing a user-level
    revocation timestamp. Any token issued before this timestamp is rejected.
    Used for: password change, account suspension, forced logout all devices.

    Returns the number of seconds the revocation marker is stored.
    """
    from app.core.cache import get_redis
    client = get_redis()
    if not client:
        logger.warning("Redis unavailable — cannot revoke all user tokens")
        return 0

    # Store revocation timestamp for this user
    # Access tokens live for ACCESS_TOKEN_EXPIRE_MINUTES, so we keep
    # the marker for that long to cover any in-flight tokens.
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    key = f"revoked_user:{user_id}"
    timestamp = int(datetime.now(timezone.utc).timestamp())

    try:
        client.setex(key, ttl, str(timestamp))
        logger.info(f"All tokens revoked for user {user_id} (marker TTL={ttl}s)")
        return ttl
    except Exception as e:
        logger.error(f"Failed to set user revocation marker: {e}")
        return 0


def is_user_globally_revoked(user_id: int, token_iat: Optional[int]) -> bool:
    """
    Check if a user's tokens were globally revoked after the token was issued.
    token_iat: the 'iat' (issued-at) claim from the decoded token.
    """
    from app.core.cache import get_redis
    client = get_redis()
    if not client or token_iat is None:
        return False

    try:
        revoked_at = client.get(f"revoked_user:{user_id}")
        if revoked_at and int(revoked_at) > token_iat:
            return True
        return False
    except Exception as e:
        logger.warning(f"User revocation check failed: {e}")
        return False
