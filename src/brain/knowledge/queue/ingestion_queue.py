"""Persistent SQLite ingestion queue with atomic, fenced worker leases."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.brain.db import get_connection
from src.brain.models.knowledge import IngestionJob, IngestionStatus

_TERMINAL_STATUSES = ("COMPLETED", "FAILED", "SKIPPED", "DUPLICATE")


class IngestionQueue:
    """Coordinate singleton mutations across one or more worker processes.

    A claim increments both ``attempts`` and ``lease_token`` in the same
    ``BEGIN IMMEDIATE`` transaction that selects the job. Every worker-side
    mutation must present the current owner and token, which fences a stale
    process after its lease is reclaimed.
    """

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _validate_owner(worker_id: str, lease_token: int) -> None:
        if not str(worker_id or "").strip():
            raise ValueError("worker_id is required for a leased job mutation")
        if not isinstance(lease_token, int) or lease_token <= 0:
            raise ValueError("a positive lease_token is required for a leased job mutation")

    def clear(self) -> None:
        """Clear queue rows. Intended for isolated tests and maintenance only."""
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM ingestion_jobs")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue_job(
        self,
        source_id: str,
        priority: int = 10,
        max_attempts: int = 3,
    ) -> IngestionJob:
        if not str(source_id or "").strip():
            raise ValueError("source_id is required")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                "SELECT 1 FROM knowledge_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
            if source is None:
                raise ValueError(
                    f"Knowledge source {source_id!r} must be registered before enqueue"
                )
            connection.execute(
                """
                INSERT INTO ingestion_jobs (
                    job_id, source_id, status, priority, stage, attempts,
                    max_attempts, next_retry_at, progress, checkpoint_stage,
                    error_message, worker_id, lease_until, heartbeat_at,
                    lease_token, created_at, updated_at
                ) VALUES (?, ?, 'DISCOVERED', ?, 'DISCOVERED', 0, ?, ?, 0.0,
                          NULL, NULL, NULL, NULL, NULL, 0, ?, ?)
                """,
                (job_id, source_id, priority, max_attempts, now_str, now_str, now_str),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return IngestionJob(
            job_id=job_id,
            source_id=source_id,
            priority=priority,
            max_attempts=max_attempts,
            created_at=now_str,
            updated_at=now_str,
        )

    def claim_job(
        self,
        worker_id: str = "default_worker",
        lease_seconds: int = 60,
    ) -> Optional[IngestionJob]:
        """Atomically claim the highest-priority ready job.

        ``BEGIN IMMEDIATE`` serializes the candidate selection and ownership
        update across processes. Expired jobs are reclaimed in that same
        transaction before a new candidate is selected.
        """
        if not str(worker_id or "").strip():
            raise ValueError("worker_id is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = self._now()
        now_str = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            # A claim also repairs expired leases so recovery does not depend on
            # a separate maintenance loop.
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'FAILED', stage = 'FAILED',
                    error_message = 'Worker lease expired and max attempts reached',
                    worker_id = NULL, lease_until = NULL, heartbeat_at = NULL,
                    updated_at = ?
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                  AND lease_until IS NOT NULL AND lease_until <= ?
                  AND attempts >= max_attempts
                """,
                (now_str, now_str),
            )
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'RETRY_PENDING', stage = 'RETRY_PENDING',
                    next_retry_at = ?,
                    error_message = 'Worker lease expired; reclaimed for retry',
                    worker_id = NULL, lease_until = NULL, heartbeat_at = NULL,
                    updated_at = ?
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                  AND lease_until IS NOT NULL AND lease_until <= ?
                  AND attempts < max_attempts
                """,
                (now_str, now_str, now_str),
            )
            candidate = connection.execute(
                """
                SELECT job_id
                FROM ingestion_jobs
                WHERE status IN ('DISCOVERED', 'RETRY_PENDING')
                  AND worker_id IS NULL
                  AND attempts < max_attempts
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (now_str,),
            ).fetchone()
            if candidate is None:
                connection.commit()
                return None
            result = connection.execute(
                """
                UPDATE ingestion_jobs
                SET worker_id = ?, lease_until = ?, heartbeat_at = ?,
                    lease_token = lease_token + 1,
                    status = 'VALIDATING', stage = 'VALIDATING',
                    attempts = attempts + 1, error_message = NULL,
                    updated_at = ?
                WHERE job_id = ?
                  AND status IN ('DISCOVERED', 'RETRY_PENDING')
                  AND worker_id IS NULL
                  AND attempts < max_attempts
                """,
                (worker_id, lease_until, now_str, now_str, candidate["job_id"]),
            )
            if result.rowcount != 1:
                connection.rollback()
                return None
            row = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE job_id = ?",
                (candidate["job_id"],),
            ).fetchone()
            connection.commit()
            return self._row_to_job(row) if row else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def owns_lease(self, job_id: str, worker_id: str, lease_token: int) -> bool:
        self._validate_owner(worker_id, lease_token)
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            row = connection.execute(
                """
                SELECT 1 FROM ingestion_jobs
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                """,
                (job_id, worker_id, lease_token, now_str),
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int = 60,
        lease_token: Optional[int] = None,
    ) -> bool:
        """Extend a live lease only for its current fenced owner."""
        self._validate_owner(worker_id, lease_token or 0)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = self._now()
        now_str = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        connection = get_connection()
        try:
            result = connection.execute(
                """
                UPDATE ingestion_jobs
                SET lease_until = ?, heartbeat_at = ?, updated_at = ?
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                """,
                (
                    lease_until,
                    now_str,
                    now_str,
                    job_id,
                    worker_id,
                    lease_token,
                    now_str,
                ),
            )
            connection.commit()
            return result.rowcount == 1
        finally:
            connection.close()

    def update_progress(
        self,
        job_id: str,
        stage: str,
        progress: float,
        checkpoint_stage: Optional[str] = None,
        *,
        worker_id: str,
        lease_token: int,
    ) -> bool:
        self._validate_owner(worker_id, lease_token)
        if not 0.0 <= float(progress) <= 1.0:
            raise ValueError("progress must be between 0 and 1")
        normalized_stage = str(stage or "").strip().upper()
        if normalized_stage not in IngestionStatus._value2member_map_:
            raise ValueError(f"unknown ingestion stage: {stage!r}")
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            result = connection.execute(
                """
                UPDATE ingestion_jobs
                SET stage = ?, status = ?, progress = ?,
                    checkpoint_stage = COALESCE(?, checkpoint_stage), updated_at = ?
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                """,
                (
                    normalized_stage,
                    normalized_stage,
                    float(progress),
                    checkpoint_stage,
                    now_str,
                    job_id,
                    worker_id,
                    lease_token,
                    now_str,
                ),
            )
            connection.commit()
            return result.rowcount == 1
        finally:
            connection.close()

    def complete_job(self, job_id: str, worker_id: str, lease_token: int) -> bool:
        self._validate_owner(worker_id, lease_token)
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            result = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'COMPLETED', stage = 'COMPLETED', progress = 1.0,
                    worker_id = NULL, lease_until = NULL, heartbeat_at = NULL,
                    next_retry_at = NULL, updated_at = ?
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                """,
                (now_str, job_id, worker_id, lease_token, now_str),
            )
            connection.commit()
            return result.rowcount == 1
        finally:
            connection.close()

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        worker_id: str,
        lease_token: int,
    ) -> bool:
        """Fail the current attempt without incrementing attempts a second time."""
        self._validate_owner(worker_id, lease_token)
        now = self._now()
        now_str = now.isoformat()
        safe_error = str(error_message or "Unknown ingestion error")[:2000]
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT attempts, max_attempts FROM ingestion_jobs
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                """,
                (job_id, worker_id, lease_token, now_str),
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            if row["attempts"] < row["max_attempts"]:
                delay = min(300, 5 * (2 ** max(0, row["attempts"] - 1)))
                next_retry = (now + timedelta(seconds=delay)).isoformat()
                status = "RETRY_PENDING"
            else:
                next_retry = None
                status = "FAILED"
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, stage = ?, error_message = ?, next_retry_at = ?,
                    worker_id = NULL, lease_until = NULL, heartbeat_at = NULL,
                    updated_at = ?
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                """,
                (
                    status,
                    status,
                    safe_error,
                    next_retry,
                    now_str,
                    job_id,
                    worker_id,
                    lease_token,
                ),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release_job(self, job_id: str, worker_id: str, lease_token: int) -> bool:
        """Make a gracefully released job immediately claimable again."""
        self._validate_owner(worker_id, lease_token)
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            result = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'RETRY_PENDING', stage = 'RETRY_PENDING',
                    next_retry_at = ?, worker_id = NULL, lease_until = NULL,
                    heartbeat_at = NULL,
                    error_message = 'Worker released job before completion',
                    updated_at = ?
                WHERE job_id = ? AND worker_id = ? AND lease_token = ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                """,
                (now_str, now_str, job_id, worker_id, lease_token),
            )
            connection.commit()
            return result.rowcount == 1
        finally:
            connection.close()

    def reclaim_stale_jobs(self, stale_threshold_seconds: int = 0) -> int:
        """Reclaim leases expired before the optional grace threshold."""
        grace = max(0, int(stale_threshold_seconds))
        cutoff = (self._now() - timedelta(seconds=grace)).isoformat()
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            failed = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'FAILED', stage = 'FAILED',
                    error_message = 'Worker lease expired and max attempts reached',
                    worker_id = NULL, lease_until = NULL, heartbeat_at = NULL,
                    updated_at = ?
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                  AND lease_until IS NOT NULL AND lease_until <= ?
                  AND attempts >= max_attempts
                """,
                (now_str, cutoff),
            ).rowcount
            retried = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'RETRY_PENDING', stage = 'RETRY_PENDING',
                    next_retry_at = ?,
                    error_message = 'Worker lease expired; reclaimed for retry',
                    worker_id = NULL, lease_until = NULL, heartbeat_at = NULL,
                    updated_at = ?
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
                  AND lease_until IS NOT NULL AND lease_until <= ?
                  AND attempts < max_attempts
                """,
                (now_str, now_str, cutoff),
            ).rowcount
            connection.commit()
            return failed + retried
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_next_job(
        self,
        worker_id: str = "default_worker",
        lease_seconds: int = 60,
    ) -> Optional[IngestionJob]:
        return self.claim_job(worker_id=worker_id, lease_seconds=lease_seconds)

    def cancel_job(self, job_id: str) -> bool:
        now_str = self._now().isoformat()
        connection = get_connection()
        try:
            result = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'SKIPPED', stage = 'SKIPPED', worker_id = NULL,
                    lease_until = NULL, heartbeat_at = NULL, updated_at = ?
                WHERE job_id = ? AND status NOT IN ('COMPLETED', 'FAILED', 'DUPLICATE')
                """,
                (now_str, job_id),
            )
            connection.commit()
            return result.rowcount == 1
        finally:
            connection.close()

    def get_job(self, job_id: str) -> Optional[IngestionJob]:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return self._row_to_job(row) if row else None
        finally:
            connection.close()

    def get_stats(self) -> Dict[str, Any]:
        connection = get_connection()
        try:
            counts = {
                row["status"]: row["cnt"]
                for row in connection.execute(
                    "SELECT status, count(*) AS cnt FROM ingestion_jobs GROUP BY status"
                ).fetchall()
            }
            total_sources = connection.execute(
                "SELECT count(*) FROM knowledge_sources"
            ).fetchone()[0]
            total_chunks = connection.execute(
                "SELECT count(*) FROM knowledge_chunks"
            ).fetchone()[0]
            duplicates = connection.execute(
                "SELECT count(*) FROM knowledge_sources WHERE seen_count > 1"
            ).fetchone()[0]
        finally:
            connection.close()
        processing = sum(
            counts.get(status.value, 0)
            for status in (
                IngestionStatus.VALIDATING,
                IngestionStatus.EXTRACTING,
                IngestionStatus.NORMALIZING,
                IngestionStatus.CLASSIFYING,
                IngestionStatus.CHUNKING,
                IngestionStatus.EMBEDDING,
                IngestionStatus.INDEXING,
                IngestionStatus.VERIFYING,
            )
        )
        return {
            "total_sources": total_sources,
            "total_chunks": total_chunks,
            "duplicates_encountered": duplicates,
            "jobs_discovered": counts.get(IngestionStatus.DISCOVERED.value, 0),
            "jobs_processing": processing,
            "jobs_completed": counts.get(IngestionStatus.COMPLETED.value, 0),
            "jobs_failed": counts.get(IngestionStatus.FAILED.value, 0),
            "jobs_retry_pending": counts.get(IngestionStatus.RETRY_PENDING.value, 0),
        }

    @staticmethod
    def _row_to_job(row: Any) -> IngestionJob:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        raw_status = row["status"]
        status = (
            IngestionStatus(raw_status)
            if raw_status in IngestionStatus._value2member_map_
            else IngestionStatus.FAILED
        )
        return IngestionJob(
            job_id=row["job_id"],
            source_id=row["source_id"],
            status=status,
            priority=row["priority"],
            stage=row["stage"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            progress=row["progress"],
            checkpoint_stage=row["checkpoint_stage"],
            error_message=row["error_message"],
            worker_id=row["worker_id"] if "worker_id" in keys else None,
            lease_until=row["lease_until"] if "lease_until" in keys else None,
            heartbeat_at=row["heartbeat_at"] if "heartbeat_at" in keys else None,
            lease_token=row["lease_token"] if "lease_token" in keys else 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
