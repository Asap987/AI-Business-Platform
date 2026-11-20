"""Password hashing, session tokens and a small in-process rate limiter."""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Verified against when an email is unknown, so login time does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Only this digest is stored, so a leaked database cannot be used to log in."""
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter:
    """
    Sliding-window limiter, per process. Behind several workers or a proxy each
    worker counts separately, so treat it as a brake, not a guarantee; a shared
    store (Redis) is needed for strict limits.
    """

    def __init__(self, max_events: int, window_seconds: int) -> None:
        self._max, self._window = max_events, window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        """Record an attempt; False means the limit is exceeded."""
        now = time.monotonic()
        q = self._events[key]
        while q and now - q[0] > self._window:
            q.popleft()
        if len(q) >= self._max:
            return False
        q.append(now)
        return True
