"""Every process must open SQLite with the same safety settings."""
from src.brain.db import get_connection


def test_sqlite_connections_enable_wal_foreign_keys_and_busy_timeout():
    connection = get_connection()
    journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    connection.close()
    assert str(journal).casefold() == "wal"
    assert foreign_keys == 1
    assert busy_timeout >= 1000
