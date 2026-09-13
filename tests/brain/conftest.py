"""Markers and isolation local to the brain acceptance suite."""
import sqlite3

import pytest


_LIVE_TESTS = {
    "test_yaishka_parity_04_live_vision_critique",
}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.name in _LIVE_TESTS:
            item.add_marker(pytest.mark.live)


@pytest.fixture(autouse=True)
def isolate_outreach_ledger():
    """A nudge emitted by one test must not rate-limit another test."""
    from src.brain.db import get_connection

    connection = get_connection()
    try:
        connection.execute("DELETE FROM outreach_log")
        connection.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()
    yield
