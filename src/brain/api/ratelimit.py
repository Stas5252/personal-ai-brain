"""In-process rate limiting for the single-owner Brain API.

This API serves one owner, so an in-memory token bucket is the right tool: no
Redis, no extra container, no shared state to get wrong. It exists to bound the
damage from a leaked API key, a runaway client retry loop, or an accidental
``while true`` in a script — all of which otherwise burn LLM quota silently.

Pure standard library on purpose, so it is unit testable without FastAPI.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """Token bucket keyed by caller identity.

    ``capacity`` requests may burst immediately; the bucket then refills at
    ``capacity / window_seconds`` tokens per second.
    """

    def __init__(self, capacity: int, window_seconds: float, max_keys: int = 4096) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.capacity = float(capacity)
        self.window_seconds = float(window_seconds)
        self.refill_per_second = self.capacity / self.window_seconds
        self._max_keys = int(max_keys)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _evict_if_needed(self) -> None:
        if len(self._buckets) <= self._max_keys:
            return
        # Drop the least recently seen half. Buckets are cheap to rebuild, and
        # an unbounded dict would be a memory-exhaustion vector by itself.
        ordered = sorted(self._buckets.items(), key=lambda kv: kv[1].updated_at)
        for key, _ in ordered[: len(ordered) // 2]:
            self._buckets.pop(key, None)

    def check(self, key: str) -> tuple[bool, int]:
        """Consume one token for ``key``.

        Returns ``(allowed, retry_after_seconds)``. ``retry_after_seconds`` is
        always at least 1 when the request is rejected, so it is safe to put
        straight into a ``Retry-After`` header.
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._evict_if_needed()
                self._buckets[key] = _Bucket(tokens=self.capacity - 1.0, updated_at=now)
                return True, 0

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
            bucket.updated_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0

            deficit = 1.0 - bucket.tokens
            return False, max(1, int(deficit / self.refill_per_second) + 1)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_key(authorization: str | None, api_key_header: str | None, client_host: str | None) -> str:
    """Identify a caller without ever storing the raw secret.

    Keying on a hash of the presented credential means one leaked key cannot
    exhaust another caller's budget, and the limiter never holds a token that
    would be useful to an attacker reading a memory dump.
    """
    secret = (authorization or api_key_header or "").strip()
    if secret:
        return "key:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:32]
    return "ip:" + (client_host or "unknown")
