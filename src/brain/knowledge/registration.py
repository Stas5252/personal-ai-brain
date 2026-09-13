"""Atomic registration for the single production knowledge-ingestion path."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from src.brain.db import get_connection
from src.brain.knowledge.storage import StorageManager
from src.brain.models.knowledge import IngestionJob, IngestionStatus, KnowledgeLayer

_TERMINAL = ("COMPLETED", "FAILED", "SKIPPED", "DUPLICATE")
_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}


@dataclass(frozen=True)
class RegistrationResult:
    source_id: str
    job: IngestionJob
    duplicate: bool = False


def _source_type(extension: str) -> str:
    if extension in _VIDEO:
        return "video"
    if extension in _AUDIO:
        return "audio"
    if extension in _IMAGE:
        return "image"
    return "document"


def _row_to_job(row: Any) -> IngestionJob:
    return IngestionJob(
        job_id=row["job_id"], source_id=row["source_id"],
        status=IngestionStatus(row["status"]), priority=row["priority"],
        stage=row["stage"], attempts=row["attempts"], max_attempts=row["max_attempts"],
        progress=row["progress"], checkpoint_stage=row["checkpoint_stage"],
        error_message=row["error_message"], worker_id=row["worker_id"],
        lease_until=row["lease_until"], heartbeat_at=row["heartbeat_at"],
        lease_token=row["lease_token"], created_at=row["created_at"], updated_at=row["updated_at"],
    )


class IngestionRegistrar:
    """Persist a source and its queue job in one SQLite transaction."""

    def __init__(self, storage: Optional[StorageManager] = None):
        self.storage = storage or StorageManager()

    @staticmethod
    def _ensure_constraints(connection) -> None:
        connection.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_sources_sha256 ON knowledge_sources(sha256)")
        connection.execute(
            """UPDATE ingestion_jobs AS candidate
               SET status='SKIPPED', stage='SKIPPED',
                   error_message='Superseded by atomic registration migration'
               WHERE status NOT IN ('COMPLETED','FAILED','SKIPPED','DUPLICATE')
                 AND EXISTS (
                   SELECT 1 FROM ingestion_jobs AS keeper
                   WHERE keeper.source_id=candidate.source_id
                     AND keeper.status NOT IN ('COMPLETED','FAILED','SKIPPED','DUPLICATE')
                     AND (keeper.created_at < candidate.created_at OR
                          (keeper.created_at = candidate.created_at AND keeper.job_id < candidate.job_id))
                 )"""
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_jobs_active_source "
            "ON ingestion_jobs(source_id) "
            "WHERE status NOT IN ('COMPLETED','FAILED','SKIPPED','DUPLICATE')"
        )

    @staticmethod
    def _active_job(connection, source_id: str):
        return connection.execute(
            "SELECT * FROM ingestion_jobs WHERE source_id=? "
            "AND status NOT IN ('COMPLETED','FAILED','SKIPPED','DUPLICATE') "
            "ORDER BY created_at DESC LIMIT 1", (source_id,),
        ).fetchone()

    @staticmethod
    def _insert_job(connection, source_id: str, priority: int, max_attempts: int, now: str):
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        connection.execute(
            """INSERT INTO ingestion_jobs (
                job_id, source_id, status, priority, stage, attempts,
                max_attempts, next_retry_at, progress, checkpoint_stage,
                error_message, worker_id, lease_until, heartbeat_at,
                lease_token, created_at, updated_at
            ) VALUES (?, ?, 'DISCOVERED', ?, 'DISCOVERED', 0, ?, NULL, 0.0,
                      'DISCOVERED', NULL, NULL, NULL, NULL, 0, ?, ?)""",
            (job_id, source_id, priority, max_attempts, now, now),
        )
        return connection.execute("SELECT * FROM ingestion_jobs WHERE job_id=?", (job_id,)).fetchone()

    def register_file(
        self, file_path: Path, *, original_filename: Optional[str] = None,
        title: Optional[str] = None, layer: KnowledgeLayer = KnowledgeLayer.GLOBAL,
        author: str = "User", subcategory: Optional[str] = None,
        tags: Optional[Iterable[str]] = None, project: Optional[str] = None,
        client: Optional[str] = None, priority: int = 10, max_attempts: int = 3,
        force: bool = False, metadata: Optional[dict[str, Any]] = None,
    ) -> RegistrationResult:
        path = Path(file_path)
        validation = self.storage.validate_file(path, original_filename=original_filename)
        if not validation.is_valid:
            raise ValueError(validation.error_message or "File validation failed")
        stored = self.storage.store_original(path, validation.sha256, validation.safe_filename)
        now = datetime.now(timezone.utc).isoformat()
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tag_list = list(tags or ())
        meta = dict(metadata or {})
        meta.update({"author": author, "subcategory": subcategory, "tags": tag_list,
                     "project": project, "client": client, "layer": layer.value})
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_constraints(connection)
            existing = connection.execute(
                "SELECT * FROM knowledge_sources WHERE sha256=? ORDER BY timestamp DESC LIMIT 1",
                (validation.sha256,),
            ).fetchone()
            if existing is not None and not force:
                active = self._active_job(connection, existing["source_id"])
                if active is not None:
                    connection.execute("UPDATE knowledge_sources SET seen_count=seen_count+1 WHERE source_id=?", (existing["source_id"],))
                    connection.commit()
                    return RegistrationResult(existing["source_id"], _row_to_job(active), True)
                if existing["ingestion_status"] in ("COMPLETED", "DUPLICATE"):
                    duplicate = self._insert_job(connection, existing["source_id"], priority, max_attempts, now)
                    connection.execute(
                        "UPDATE ingestion_jobs SET status='DUPLICATE', stage='DUPLICATE', "
                        "checkpoint_stage='DUPLICATE', progress=1.0 WHERE job_id=?", (duplicate["job_id"],),
                    )
                    connection.execute("UPDATE knowledge_sources SET seen_count=seen_count+1 WHERE source_id=?", (existing["source_id"],))
                    duplicate = connection.execute("SELECT * FROM ingestion_jobs WHERE job_id=?", (duplicate["job_id"],)).fetchone()
                    connection.commit()
                    return RegistrationResult(existing["source_id"], _row_to_job(duplicate), True)

            source_id = existing["source_id"] if existing is not None else str(uuid.uuid4())
            derived = self.storage.get_derived_dir(source_id)
            source_title = title or Path(validation.safe_filename).stem.replace("_", " ").title()
            connection.execute(
                """INSERT INTO knowledge_sources (
                    source_id, title, author, date, type, category, subcategory,
                    tags_json, project, client, language, source_path, timestamp,
                    confidence, original_filename, mime_type, file_size, sha256,
                    p_hash, storage_path, derived_dir, ingestion_status,
                    processing_version, classification_method, seen_count,
                    checkpoint_stage, error_message, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ru', ?, ?, 1.0, ?, ?, ?, ?, ?, ?, ?,
                          'DISCOVERED', 'v1.0', 'rules', 1, 'DISCOVERED', NULL, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    title=excluded.title, author=excluded.author, category=excluded.category,
                    subcategory=excluded.subcategory, tags_json=excluded.tags_json,
                    project=excluded.project, client=excluded.client,
                    source_path=excluded.source_path, timestamp=excluded.timestamp,
                    original_filename=excluded.original_filename, mime_type=excluded.mime_type,
                    file_size=excluded.file_size, sha256=excluded.sha256,
                    p_hash=excluded.p_hash, storage_path=excluded.storage_path,
                    derived_dir=excluded.derived_dir, ingestion_status='DISCOVERED',
                    checkpoint_stage='DISCOVERED', error_message=NULL,
                    metadata_json=excluded.metadata_json""",
                (source_id, source_title, author, date, _source_type(validation.extension), layer.value,
                 subcategory, json.dumps(tag_list), project, client, str(stored), now,
                 validation.safe_filename, validation.mime_type, validation.file_size,
                 validation.sha256, validation.p_hash, str(stored), str(derived), json.dumps(meta)),
            )
            active = self._active_job(connection, source_id)
            job_row = active or self._insert_job(connection, source_id, priority, max_attempts, now)
            connection.commit()
            return RegistrationResult(source_id, _row_to_job(job_row), False)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def register_text(self, content: str, *, title: str = "User Text Source", **kwargs) -> RegistrationResult:
        if not str(content or "").strip():
            raise ValueError("Text content is empty")
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            return self.register_file(temp_path, original_filename=f"{title}.md", title=title, **kwargs)
        finally:
            temp_path.unlink(missing_ok=True)

    def enqueue_existing(self, source_id: str, *, priority: int = 12, max_attempts: int = 3) -> RegistrationResult:
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_constraints(connection)
            if connection.execute("SELECT 1 FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone() is None:
                raise ValueError(f"Knowledge source {source_id!r} not found")
            active = self._active_job(connection, source_id)
            duplicate = active is not None
            row = active or self._insert_job(connection, source_id, priority, max_attempts, datetime.now(timezone.utc).isoformat())
            if not duplicate:
                connection.execute(
                    "UPDATE knowledge_sources SET ingestion_status='DISCOVERED', "
                    "checkpoint_stage='DISCOVERED', error_message=NULL WHERE source_id=?", (source_id,),
                )
            connection.commit()
            return RegistrationResult(source_id, _row_to_job(row), duplicate)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def job_status(job_id: str) -> Optional[dict[str, Any]]:
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM ingestion_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {
        "job_id": row["job_id"], "source_id": row["source_id"],
        "status": row["status"], "stage": row["stage"], "progress": row["progress"],
        "attempts": row["attempts"], "max_attempts": row["max_attempts"],
        "error": row["error_message"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], "terminal": row["status"] in _TERMINAL,
    }
