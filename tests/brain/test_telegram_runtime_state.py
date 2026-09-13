"""Integration tests for the durable Telegram outbox using real SQLite."""
import json
import sqlite3

import pytest

from src.brain.channels.runtime_state import RuntimeState


def update(number):
    return {"update_id": number, "message": {"text": "hello", "chat": {"id": 42, "type": "private"}, "from": {"id": 42}}}


def plan(*texts):
    return {"version": 1, "chat_id": "42", "parts": [{"kind": "text", "text": text, "parse_mode": None, "reply_markup": None} for text in texts]}


def inbox_row(state, ident):
    with state.connect() as db:
        return db.execute("SELECT status,attempts,retry_at,last_error FROM telegram_inbox WHERE id=?", (ident,)).fetchone()


def test_existing_runtime_database_is_migrated_without_data_loss(tmp_path):
    path = tmp_path / "runtime.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE transport_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE telegram_inbox (
            id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0
        );
        INSERT INTO telegram_inbox(id,payload) VALUES (7,'{"update_id":7}');
    """)
    connection.commit()
    connection.close()
    state = RuntimeState(path)
    assert state.next_update()[0] == 7
    with state.connect() as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(telegram_inbox)")}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "last_error" in columns
    assert "telegram_outbox" in tables
    assert "telegram_delivery_receipts" in tables


def test_delivery_plan_is_immutable_for_an_update(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(update(1))
    state.stage_delivery(1, plan("original answer"))
    state.stage_delivery(1, plan("original answer"))
    with pytest.raises(RuntimeError, match="immutable"):
        state.stage_delivery(1, plan("replacement answer"))
    assert state.get_delivery(1)["parts"][0]["text"] == "original answer"


def test_confirmed_part_checkpoint_is_idempotent_and_cannot_skip(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(update(3))
    state.stage_delivery(3, plan("part-0", "part-1", "part-2"))
    with pytest.raises(RuntimeError, match="Cannot skip"):
        state.confirm_delivery_part(3, 1, 101)
    state.confirm_delivery_part(3, 0, 100)
    state.confirm_delivery_part(3, 0, 100)
    assert state.get_delivery(3)["next_part"] == 1
    assert state.next_delivery_part(3)["text"] == "part-1"


def test_delivery_failure_preserves_plan_and_checkpoint(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(update(4))
    original = plan("part-0", "part-1")
    state.stage_delivery(4, original)
    state.confirm_delivery_part(4, 0, 100)
    assert state.fail_delivery(4, "network timeout", retry_delay=0) == "retry_wait"
    delivery = state.get_delivery(4)
    assert delivery["next_part"] == 1
    assert delivery["parts"] == original["parts"]
    assert inbox_row(state, 4)[1] == 1


def test_retry_budget_and_redrive_keep_the_same_plan(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(update(5))
    state.stage_delivery(5, plan("important"))
    assert state.fail_delivery(5, "first", retry_delay=0) == "retry_wait"
    assert state.fail_delivery(5, "second", retry_delay=0) == "retry_wait"
    assert state.fail_delivery(5, "third", retry_delay=0) == "failed"
    state.redrive_delivery(5)
    assert inbox_row(state, 5)[:2] == ("ready", 0)
    assert state.next_delivery_part(5)["text"] == "important"


def test_future_retry_does_not_block_a_later_update(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(update(10))
    state.stage_delivery(10, plan("blocked"))
    state.fail_delivery(10, "wait", retry_delay=60)
    state.enqueue(update(11))
    assert state.next_update()[0] == 11


def test_all_parts_must_be_confirmed_before_done(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(update(12))
    state.stage_delivery(12, plan("a", "b"))
    state.confirm_delivery_part(12, 0, 100)
    with pytest.raises(RuntimeError, match="pending"):
        state.complete_delivery(12)
    state.confirm_delivery_part(12, 1, 101)
    state.complete_delivery(12)
    assert inbox_row(state, 12)[0] == "done"
    with state.connect() as db:
        stored = db.execute("SELECT response_json FROM telegram_outbox WHERE update_id=12").fetchone()[0]
    assert json.loads(stored)["parts"] == plan("a", "b")["parts"]
