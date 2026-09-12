"""SQLite persistence with production-safe connection invariants."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, Tuple

from src.brain.config import DB_PATH


def _busy_timeout_ms() -> int:
    try:
        value = int(os.environ.get("BRAIN_SQLITE_BUSY_TIMEOUT_MS", "15000"))
    except ValueError:
        value = 15000
    return min(max(value, 1000), 120000)


def get_connection() -> sqlite3.Connection:
    """Open a connection configured consistently in every process."""
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    timeout_ms = _busy_timeout_ms()
    connection = sqlite3.connect(path, timeout=timeout_ms / 1000.0)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={timeout_ms}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def _add_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: Iterable[Tuple[str, str]],
) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns:
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db() -> None:
    """Create and migrate the schema while holding a single writer lock."""
    connection = get_connection()
    try:
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).casefold() != "wal":
            raise RuntimeError(f"SQLite WAL mode is required, got {mode!r}")
        connection.execute("PRAGMA wal_autocheckpoint=1000")
        # API and worker can start together. Serialize schema discovery and
        # ALTER TABLE statements so both processes cannot race a migration.
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """CREATE TABLE IF NOT EXISTS user_profile (
            id TEXT PRIMARY KEY, data_json TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, content TEXT NOT NULL,
            importance REAL NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, source TEXT, project_id TEXT, client_id TEXT,
            expires_at TEXT, status TEXT NOT NULL, superseded_by TEXT, tags_json TEXT)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS knowledge_sources (
            source_id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT, date TEXT,
            type TEXT, category TEXT NOT NULL, subcategory TEXT, tags_json TEXT,
            project TEXT, client TEXT, language TEXT, source_path TEXT, timestamp TEXT,
            confidence REAL, visual_description TEXT, ocr_text TEXT,
            original_filename TEXT, mime_type TEXT, file_size INTEGER DEFAULT 0,
            sha256 TEXT, p_hash TEXT, storage_path TEXT, derived_dir TEXT,
            ingestion_status TEXT DEFAULT 'COMPLETED', processing_version TEXT DEFAULT 'v1.0',
            classification_method TEXT DEFAULT 'rules', seen_count INTEGER DEFAULT 1,
            checkpoint_stage TEXT, error_message TEXT, metadata_json TEXT DEFAULT '{}')"""
        )
        _add_columns(
            connection,
            "knowledge_sources",
            [
                ("original_filename", "TEXT"),
                ("mime_type", "TEXT"),
                ("file_size", "INTEGER DEFAULT 0"),
                ("sha256", "TEXT"),
                ("p_hash", "TEXT"),
                ("storage_path", "TEXT"),
                ("derived_dir", "TEXT"),
                ("ingestion_status", "TEXT DEFAULT 'COMPLETED'"),
                ("processing_version", "TEXT DEFAULT 'v1.0'"),
                ("classification_method", "TEXT DEFAULT 'rules'"),
                ("seen_count", "INTEGER DEFAULT 1"),
                ("checkpoint_stage", "TEXT"),
                ("error_message", "TEXT"),
                ("metadata_json", "TEXT DEFAULT '{}'"),
            ],
        )

        connection.execute(
            """CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, layer TEXT NOT NULL,
            content TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
            content_type TEXT DEFAULT 'text', page_number INTEGER, slide_number INTEGER,
            sheet_name TEXT, start_time REAL, end_time REAL, heading_path TEXT,
            language TEXT DEFAULT 'ru', token_count INTEGER DEFAULT 0,
            FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE)"""
        )
        _add_columns(
            connection,
            "knowledge_chunks",
            [
                ("content_type", "TEXT DEFAULT 'text'"),
                ("page_number", "INTEGER"),
                ("slide_number", "INTEGER"),
                ("sheet_name", "TEXT"),
                ("start_time", "REAL"),
                ("end_time", "REAL"),
                ("heading_path", "TEXT"),
                ("language", "TEXT DEFAULT 'ru'"),
                ("token_count", "INTEGER DEFAULT 0"),
            ],
        )

        connection.execute(
            """CREATE TABLE IF NOT EXISTS ingestion_jobs (
            job_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, status TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 10, stage TEXT NOT NULL DEFAULT 'DISCOVERED',
            attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
            next_retry_at TEXT, progress REAL NOT NULL DEFAULT 0.0, checkpoint_stage TEXT,
            error_message TEXT, worker_id TEXT, lease_until TEXT, heartbeat_at TEXT,
            lease_token INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE)"""
        )
        _add_columns(
            connection,
            "ingestion_jobs",
            [
                ("worker_id", "TEXT"),
                ("lease_until", "TEXT"),
                ("heartbeat_at", "TEXT"),
                ("lease_token", "INTEGER NOT NULL DEFAULT 0"),
            ],
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ij_lease "
            "ON ingestion_jobs(status, lease_until, priority DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ij_worker ON ingestion_jobs(worker_id)"
        )

        connection.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
            chunk_id UNINDEXED, source_id UNINDEXED, content, heading_path,
            sheet_name, layer UNINDEXED)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS style_exemplars (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
            exemplar_type TEXT NOT NULL, category TEXT NOT NULL, tags_json TEXT,
            notes TEXT, created_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, contact TEXT, status TEXT NOT NULL,
            source TEXT, budget TEXT, service TEXT, preferences TEXT, objections TEXT,
            history_json TEXT, projects_json TEXT, notes_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, status TEXT NOT NULL,
            start_date TEXT, deadline TEXT, client_id TEXT, files_json TEXT,
            conversations_json TEXT, tasks_json TEXT, decisions_json TEXT,
            outputs_json TEXT, memory_ids_json TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)"""
        )
        _add_columns(
            connection,
            "clients",
            [
                ("source_channel", "TEXT"),
                ("preferred_style", "TEXT"),
                ("objections_history_json", "TEXT DEFAULT '[]'"),
                ("last_contact_at", "TEXT"),
            ],
        )
        _add_columns(
            connection,
            "projects",
            [
                ("concept", "TEXT DEFAULT ''"),
                ("location", "TEXT"),
                ("shot_list_json", "TEXT DEFAULT '[]'"),
                ("moodboard_refs_json", "TEXT DEFAULT '[]'"),
                ("deliverables_json", "TEXT DEFAULT '[]'"),
            ],
        )

        connection.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY, title TEXT NOT NULL, type TEXT NOT NULL,
            status TEXT NOT NULL, priority TEXT NOT NULL, created_at TEXT NOT NULL,
            due_at TEXT, project_id TEXT, client_id TEXT, inputs_json TEXT NOT NULL DEFAULT '{}',
            outputs_json TEXT NOT NULL DEFAULT '{}', approval_state TEXT NOT NULL DEFAULT 'NONE')"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, due_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_client ON tasks(client_id)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS workflows (
            workflow_id TEXT PRIMARY KEY, name TEXT NOT NULL, workflow_type TEXT NOT NULL,
            status TEXT NOT NULL, current_step INTEGER NOT NULL DEFAULT 0,
            steps_json TEXT NOT NULL DEFAULT '[]', context_json TEXT NOT NULL DEFAULT '{}',
            results_json TEXT NOT NULL DEFAULT '{}', approval_state TEXT NOT NULL DEFAULT 'NONE',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_wf_status ON workflows(status, updated_at)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS request_traces (
            request_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, query TEXT NOT NULL,
            intent TEXT NOT NULL, data_json TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS onboarding_sessions (
            session_id TEXT PRIMARY KEY, step INTEGER NOT NULL, answers_json TEXT NOT NULL,
            completed INTEGER NOT NULL, created_at TEXT NOT NULL)"""
        )
        connection.commit()

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            summary = ", ".join(f"{row[0]}:{row[1]}" for row in violations[:10])
            raise RuntimeError(f"SQLite foreign-key violations detected: {summary}")
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


init_db()
