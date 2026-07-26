from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol


class SupportsReplayGuard(Protocol):
    def seen(self, key: str) -> bool: ...


class SupportsRateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_reference(prefix: str = "GS") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}-{int(time.time())}"


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True, default=str)


def kobo_from_naira(amount_naira: float) -> int:
    return int(round(float(amount_naira) * 100))


def mask_email(email: str) -> str:
    value = email.strip()
    if "@" not in value:
        return "hidden"
    name, domain = value.split("@", 1)
    if len(name) <= 2:
        name = f"{name[:1]}***"
    else:
        name = f"{name[:2]}***"
    return f"{name}@{domain}"


def sanitize_for_logs(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    for key in ("authorization", "secret", "token", "signature", "access_code"):
        if key in redacted:
            redacted[key] = "***"
    return redacted


def verify_paystack_signature(raw_body: bytes, secret_key: str, signature_header: str) -> bool:
    if not secret_key or not signature_header:
        return False
    computed = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature_header.strip())


class ReplayGuard:
    """Simple replay-attack guard backed by in-memory cache."""

    def __init__(self, ttl_seconds: int = 900, max_items: int = 5000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: dict[str, float] = {}
        self._queue: deque[str] = deque()
        self._lock = Lock()

    def seen(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._evict(now)
            if key in self._items:
                return True
            self._items[key] = now + self.ttl_seconds
            self._queue.append(key)
            return False

    def _evict(self, now: float) -> None:
        while self._queue and len(self._items) > self.max_items:
            old = self._queue.popleft()
            self._items.pop(old, None)
        while self._queue:
            first = self._queue[0]
            expiry = self._items.get(first)
            if expiry is None:
                self._queue.popleft()
                continue
            if expiry > now:
                break
            self._queue.popleft()
            self._items.pop(first, None)


class RedisReplayGuard:
    """Distributed replay-attack guard using Redis SET NX EX semantics."""

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 900,
        prefix: str = "pay:webhook:replay",
        fallback_guard: SupportsReplayGuard | None = None,
        fail_closed: bool = True,
    ) -> None:
        import redis

        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self.fallback_guard = fallback_guard
        self.fail_closed = fail_closed
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def seen(self, key: str) -> bool:
        namespaced = f"{self.prefix}:{key}"
        try:
            created = self._redis.set(namespaced, "1", ex=self.ttl_seconds, nx=True)
            return created is None
        except Exception:
            if self.fallback_guard is not None:
                return self.fallback_guard.seen(key)
            # Fail-closed when no fallback is available.
            return self.fail_closed


class InMemoryRateLimiter:
    """Best-effort in-process limiter. Use Redis in multi-node production deployments."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._store: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._store[key]
            while bucket and (now - bucket[0]) > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


class RedisRateLimiter:
    """Distributed fixed-window rate limiter using Redis INCR + EXPIRE."""

    def __init__(
        self,
        redis_url: str,
        limit: int,
        window_seconds: int,
        prefix: str = "pay:rl",
        fallback_limiter: SupportsRateLimiter | None = None,
    ) -> None:
        import redis

        self.limit = limit
        self.window_seconds = window_seconds
        self.prefix = prefix
        self.fallback_limiter = fallback_limiter
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def allow(self, key: str) -> bool:
        namespaced = f"{self.prefix}:{key}"
        try:
            count = self._redis.incr(namespaced)
            if count == 1:
                self._redis.expire(namespaced, self.window_seconds)
            return int(count) <= self.limit
        except Exception:
            if self.fallback_limiter is not None:
                return self.fallback_limiter.allow(key)
            # Conservative default if no fallback is configured.
            return False
