"""Outbound pacing for the Telegram Bot API: one limiter, one honest backoff.

Telegram allows about one message per second inside a single chat and roughly
thirty calls per second overall. Crossing that line returns HTTP 429 with a
`parameters.retry_after` field, and that number is the only correct pause
length -- guessing a delay is what turns one 429 into a stream of them.

The limiter is a process-wide singleton on purpose. A limiter per sender
multiplies the real send rate by the number of senders, which is the classic
way to keep hitting 429 while believing the limit is respected.

Nothing here touches the network. `RateLimiter` only decides how long to wait,
so the whole policy is testable offline with an injected clock.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

# Telegram's documented ceilings, kept deliberately conservative.
PER_CHAT_INTERVAL = 1.05  # seconds between two messages in the same chat
GLOBAL_INTERVAL = 1.0 / 25  # seconds between any two API calls (30/s is the wall)
MAX_RETRY_AFTER = 60.0  # a longer pause is reported as a failure instead of slept through
MAX_ATTEMPTS = 3
MAX_TRACKED_CHATS = 256


def parse_retry_after(payload: Any) -> Optional[float]:
    """Extracts `retry_after` from a Bot API error body, header or dict.

    Returns None when the payload carries no flood-control hint at all, which
    is the signal for the caller to stop retrying: a 400 for broken Markdown
    will never be fixed by waiting.
    """
    if payload is None:
        return None
    data: Any = payload
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except Exception:
            try:
                value = float(text)
            except ValueError:
                return None
            return value if value >= 0 else None
    if isinstance(data, bool):
        return None
    if isinstance(data, (int, float)):
        return float(data) if data >= 0 else None
    if not isinstance(data, dict):
        return None
    for source in (data.get("parameters"), data):
        if not isinstance(source, dict) or "retry_after" not in source:
            continue
        try:
            value = float(source["retry_after"])
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


class RateLimiter:
    """Reservation-based pacing: every call books the next free slot.

    Booking under the lock and sleeping outside it keeps the order of waiting
    senders stable and never holds the lock for the length of a pause.
    """

    def __init__(
        self,
        clock: Optional[Callable[[], float]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        per_chat_interval: float = PER_CHAT_INTERVAL,
        global_interval: float = GLOBAL_INTERVAL,
    ) -> None:
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._per_chat = float(per_chat_interval)
        self._global = float(global_interval)
        self._lock = threading.Lock()
        self._next_global = 0.0
        self._next_chat: dict[str, float] = {}

    @staticmethod
    def _key(chat_id: Any) -> Optional[str]:
        return None if chat_id is None else str(chat_id)

    def _trim(self, now: float) -> None:
        """Drops chats whose slot is long past so the map cannot grow forever."""
        if len(self._next_chat) <= MAX_TRACKED_CHATS:
            return
        stale = [key for key, moment in self._next_chat.items() if moment <= now]
        for key in stale:
            self._next_chat.pop(key, None)

    def acquire(self, chat_id: Any = None) -> float:
        """Waits for this chat's next free slot. Returns the seconds slept.

        Pass chat_id=None for calls that do not count against the per-chat
        budget (a typing action must not push the real answer a second later).
        """
        key = self._key(chat_id)
        with self._lock:
            now = self._clock()
            earliest = max(now, self._next_global)
            if key is not None:
                earliest = max(earliest, self._next_chat.get(key, 0.0))
            self._next_global = earliest + self._global
            if key is not None:
                self._next_chat[key] = earliest + self._per_chat
            self._trim(now)
            wait = earliest - now
        if wait > 0:
            self._sleep(wait)
        return max(0.0, wait)

    def penalize(self, chat_id: Any, retry_after: Any) -> float:
        """Blocks the chat and the whole bot for exactly retry_after seconds."""
        try:
            pause = max(0.0, float(retry_after or 0.0))
        except (TypeError, ValueError):
            return 0.0
        with self._lock:
            until = self._clock() + pause
            self._next_global = max(self._next_global, until)
            key = self._key(chat_id)
            if key is not None:
                self._next_chat[key] = max(self._next_chat.get(key, 0.0), until)
        return pause

    def run(
        self,
        chat_id: Any,
        attempt: Callable[[], tuple[bool, Optional[float]]],
        max_attempts: int = MAX_ATTEMPTS,
    ) -> bool:
        """Paces one API call and retries it only when Telegram asked to wait.

        `attempt` must return (delivered, retry_after). A None retry_after
        means the failure is not flood control, so the caller's own fallback
        (plain text instead of Markdown, for example) has to take over.
        """
        attempts = max(1, int(max_attempts))
        for number in range(1, attempts + 1):
            self.acquire(chat_id)
            delivered, retry_after = attempt()
            if delivered:
                return True
            if retry_after is None:
                return False
            self.penalize(chat_id, min(float(retry_after), MAX_RETRY_AFTER))
            if float(retry_after) > MAX_RETRY_AFTER or number >= attempts:
                return False
        return False


_SHARED: Optional[RateLimiter] = None
_SHARED_LOCK = threading.Lock()


def limiter() -> RateLimiter:
    """Returns the one limiter every Telegram sender in this process shares."""
    global _SHARED
    if _SHARED is None:
        with _SHARED_LOCK:
            if _SHARED is None:
                _SHARED = RateLimiter()
    return _SHARED
