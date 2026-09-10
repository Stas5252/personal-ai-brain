"""Offline tests for the outreach limits: no network, no shared database.

Every decide() case pins its own "now", so these tests cannot start failing
next month; the ledger cases use timestamps relative to the real clock,
because history() filters by the real clock.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.brain.engines.outreach_policy import (
    ALLOW,
    BLOCK_QUIET,
    BLOCK_SAME_TYPE,
    BLOCK_TOO_SOON,
    BLOCK_WAITING,
    BLOCK_WINDOW,
    OutreachLedger,
    decide,
    normalize_history,
    parse_moment,
    within_quiet_hours,
)

NOW = datetime(2026, 9, 10, 13, 0, tzinfo=timezone.utc)


def touch(hours_ago, nudge_type="POST_SHOOT_FOLLOWUP", answered=True):
    return {
        "nudge_type": nudge_type,
        "sent_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "answered": answered,
    }


@pytest.fixture()
def ledger(tmp_path):
    path = tmp_path / "outreach.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    return OutreachLedger(connect=connect)


def test_quiet_window_wraps_over_midnight():
    assert within_quiet_hours(23) is True
    assert within_quiet_hours(2) is True
    assert within_quiet_hours(10) is False
    assert within_quiet_hours(21) is False


def test_quiet_window_without_wrap():
    assert within_quiet_hours(8, start=7, end=9) is True
    assert within_quiet_hours(9, start=7, end=9) is False


def test_first_touch_in_the_daytime_is_allowed():
    assert decide("POST_SHOOT_FOLLOWUP", [], now=NOW) == (True, ALLOW)


def test_night_is_silent():
    allowed, reason = decide("POST_SHOOT_FOLLOWUP", [], now=NOW, quiet_hour=23)
    assert (allowed, reason) == (False, BLOCK_QUIET)


def test_unanswered_touch_stops_the_next_one():
    history = [touch(100, answered=False)]
    allowed, reason = decide("CONTENT_IDLE_REMINDER", history, now=NOW)
    assert (allowed, reason) == (False, BLOCK_WAITING)


def test_unanswered_touch_stops_blocking_after_the_hold():
    history = [touch(24 * 10, nudge_type="OLD_TYPE", answered=False)]
    assert decide("CONTENT_IDLE_REMINDER", history, now=NOW) == (True, ALLOW)


def test_four_touches_in_two_weeks_is_the_ceiling():
    history = [
        touch(100, nudge_type="A"),
        touch(200, nudge_type="B"),
        touch(300, nudge_type="C"),
        touch(330, nudge_type="D"),
    ]
    allowed, reason = decide("E", history, now=NOW)
    assert (allowed, reason) == (False, BLOCK_WINDOW)


def test_second_touch_too_soon_is_blocked():
    history = [touch(10, nudge_type="A")]
    allowed, reason = decide("B", history, now=NOW)
    assert (allowed, reason) == (False, BLOCK_TOO_SOON)


def test_same_reminder_is_not_repeated_inside_two_weeks():
    history = [touch(100, nudge_type="CONTENT_IDLE_REMINDER")]
    allowed, reason = decide("CONTENT_IDLE_REMINDER", history, now=NOW)
    assert (allowed, reason) == (False, BLOCK_SAME_TYPE)


def test_another_reason_is_allowed_after_the_interval():
    history = [touch(100, nudge_type="CONTENT_IDLE_REMINDER")]
    assert decide("CLIENT_GHOSTING_CARE", history, now=NOW) == (True, ALLOW)


def test_history_older_than_the_window_is_ignored():
    history = [touch(24 * 40, nudge_type="CONTENT_IDLE_REMINDER", answered=False)]
    assert decide("CONTENT_IDLE_REMINDER", history, now=NOW) == (True, ALLOW)


def test_zulu_timestamp_is_understood():
    history = [{"nudge_type": "A", "sent_at": "2026-09-10T03:00:00Z", "answered": True}]
    allowed, reason = decide("B", history, now=NOW)
    assert (allowed, reason) == (False, BLOCK_TOO_SOON)


def test_naive_timestamp_is_treated_as_utc():
    history = [{"nudge_type": "A", "sent_at": "2026-09-10T03:00:00", "answered": True}]
    allowed, reason = decide("B", history, now=NOW)
    assert (allowed, reason) == (False, BLOCK_TOO_SOON)


def test_broken_rows_are_ignored_instead_of_crashing():
    history = [None, {}, {"sent_at": "не дата"}, {"sent_at": 5}]
    assert decide("A", history, now=NOW) == (True, ALLOW)


def test_normalize_history_sorts_newest_first():
    rows = normalize_history([touch(300, nudge_type="old"), touch(10, nudge_type="new")])
    assert [row["nudge_type"] for row in rows] == ["new", "old"]


def test_parse_moment_edge_cases():
    assert parse_moment("") is None
    assert parse_moment("вчера") is None
    assert parse_moment(NOW) == NOW
    naive = datetime(2026, 9, 10, 13, 0)
    assert parse_moment(naive).tzinfo is not None


def test_ledger_records_and_reads_back(ledger):
    assert ledger.record("POST_SHOOT_FOLLOWUP", "Собрать пост по вчерашней съёмке?") is True
    rows = ledger.history()
    assert len(rows) == 1
    assert rows[0]["nudge_type"] == "POST_SHOOT_FOLLOWUP"
    assert rows[0]["answered"] is False


def test_ledger_blocks_until_she_answers(ledger):
    real_now = datetime.now(timezone.utc)
    ledger.record("A", "первое касание", now=real_now - timedelta(hours=100))
    later = real_now + timedelta(hours=1)
    allowed, reason = decide("B", ledger.history(), now=later, quiet_hour=13)
    assert (allowed, reason) == (False, BLOCK_WAITING)
    assert ledger.mark_answered() == 1
    assert decide("B", ledger.history(), now=later, quiet_hour=13) == (True, ALLOW)


def test_ledger_summary_counts_what_was_sent(ledger):
    real_now = datetime.now(timezone.utc)
    ledger.record("A", "раз", now=real_now - timedelta(hours=200))
    ledger.mark_answered()
    ledger.record("B", "два", now=real_now - timedelta(hours=100))
    summary = ledger.summary()
    assert summary["sent"] == 2
    assert summary["unanswered"] == 1
    assert summary["last_type"] == "B"


def test_ledger_survives_a_dead_database():
    def broken():
        raise RuntimeError("no database")

    dead = OutreachLedger(connect=broken)
    assert dead.history() == []
    assert dead.record("A", "x") is False
    assert dead.mark_answered() == 0
    assert dead.summary()["sent"] == 0
