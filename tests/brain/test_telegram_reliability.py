"""Offline tests for outbound pacing, 429 handling and the background worker.

No network and no sleeping: the limiter takes an injected clock, so a 30
second retry_after is verified in microseconds. The worker tests use real
threads but every wait is bounded.
"""
import threading

from src.brain.channels.task_queue import SerialWorker
from src.brain.channels.telegram_ratelimit import (
    GLOBAL_INTERVAL,
    MAX_RETRY_AFTER,
    PER_CHAT_INTERVAL,
    RateLimiter,
    limiter,
    parse_retry_after,
)


class FakeClock:
    """Deterministic clock: sleeping moves time forward instead of waiting."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def build(clock: FakeClock) -> RateLimiter:
    return RateLimiter(clock=clock.time, sleeper=clock.sleep)


# -- pacing -----------------------------------------------------------------


def test_first_send_is_not_delayed():
    clock = FakeClock()
    assert build(clock).acquire("chat-1") == 0.0
    assert clock.slept == []


def test_second_message_to_same_chat_waits_a_second():
    clock = FakeClock()
    limit = build(clock)
    limit.acquire("chat-1")
    waited = limit.acquire("chat-1")
    assert abs(waited - PER_CHAT_INTERVAL) < 1e-9
    assert clock.slept == [waited]


def test_other_chats_only_pay_the_global_interval():
    clock = FakeClock()
    limit = build(clock)
    limit.acquire("chat-1")
    waited = limit.acquire("chat-2")
    assert abs(waited - GLOBAL_INTERVAL) < 1e-9


def test_typing_pings_do_not_consume_the_chat_budget():
    """chat_id=None keeps a status ping from delaying the real answer."""
    clock = FakeClock()
    limit = build(clock)
    limit.acquire(None)
    waited = limit.acquire("chat-1")
    assert waited < PER_CHAT_INTERVAL


def test_penalize_blocks_the_chat_for_exactly_retry_after():
    clock = FakeClock()
    limit = build(clock)
    assert limit.penalize("chat-1", 7) == 7.0
    waited = limit.acquire("chat-1")
    assert abs(waited - 7.0) < 1e-9


def test_penalize_also_holds_back_every_other_chat():
    clock = FakeClock()
    limit = build(clock)
    limit.penalize("chat-1", 5)
    assert abs(limit.acquire("chat-2") - 5.0) < 1e-9


def test_penalize_survives_garbage():
    clock = FakeClock()
    limit = build(clock)
    assert limit.penalize("chat-1", None) == 0.0
    assert limit.penalize("chat-1", "soon") == 0.0


def test_limiter_is_shared_process_wide():
    """A limiter per sender would multiply the real send rate."""
    assert limiter() is limiter()


def test_concurrent_senders_are_serialized():
    clock = FakeClock()
    limit = build(clock)
    seen: list[float] = []
    lock = threading.Lock()

    def send() -> None:
        waited = limit.acquire("chat-1")
        with lock:
            seen.append(waited)

    threads = [threading.Thread(target=send) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(seen) == 3
    assert sum(1 for value in seen if value >= PER_CHAT_INTERVAL) >= 2


# -- retry_after parsing ----------------------------------------------------


def test_parse_retry_after_reads_the_bot_api_shape():
    body = b'{"ok":false,"error_code":429,"parameters":{"retry_after":9}}'
    assert parse_retry_after(body) == 9.0


def test_parse_retry_after_reads_a_plain_header():
    assert parse_retry_after("12") == 12.0


def test_parse_retry_after_ignores_unrelated_failures():
    body = b'{"ok":false,"error_code":400,"description":"can\'t parse entities"}'
    assert parse_retry_after(body) is None
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after(True) is None


# -- retry policy -----------------------------------------------------------


def test_run_waits_out_a_429_and_then_succeeds():
    clock = FakeClock()
    limit = build(clock)
    calls: list[int] = []

    def attempt():
        calls.append(1)
        return (True, None) if len(calls) > 1 else (False, 3.0)

    assert limit.run("chat-1", attempt) is True
    assert len(calls) == 2
    assert 3.0 in clock.slept


def test_run_does_not_retry_a_failure_that_is_not_flood_control():
    clock = FakeClock()
    limit = build(clock)
    calls: list[int] = []

    def attempt():
        calls.append(1)
        return False, None

    assert limit.run("chat-1", attempt) is False
    assert len(calls) == 1


def test_run_gives_up_after_the_attempt_budget():
    clock = FakeClock()
    limit = build(clock)
    calls: list[int] = []

    def attempt():
        calls.append(1)
        return False, 1.0

    assert limit.run("chat-1", attempt, max_attempts=3) is False
    assert len(calls) == 3


def test_run_reports_an_absurd_retry_after_instead_of_sleeping_through_it():
    clock = FakeClock()
    limit = build(clock)
    calls: list[int] = []

    def attempt():
        calls.append(1)
        return False, MAX_RETRY_AFTER + 120

    assert limit.run("chat-1", attempt) is False
    assert len(calls) == 1
    assert max(clock.slept or [0.0]) <= MAX_RETRY_AFTER


# -- background worker ------------------------------------------------------


def test_worker_keeps_the_order_of_messages():
    worker = SerialWorker(name="test-order")
    done: list[int] = []
    for number in range(5):
        worker.submit(done.append, number)
    assert worker.join(timeout=5) is True
    assert done == [0, 1, 2, 3, 4]
    worker.stop()


def test_worker_survives_a_failing_job():
    worker = SerialWorker(name="test-crash")
    done: list[str] = []

    def boom():
        raise RuntimeError("generation failed")

    worker.submit(boom)
    worker.submit(done.append, "after")
    assert worker.join(timeout=5) is True
    assert done == ["after"]
    worker.stop()


def test_worker_reports_pending_work():
    worker = SerialWorker(name="test-pending")
    gate = threading.Event()
    worker.submit(gate.wait, 5)
    worker.submit(lambda: None)
    assert worker.busy() is True
    gate.set()
    assert worker.join(timeout=5) is True
    assert worker.pending() == 0
    worker.stop()
