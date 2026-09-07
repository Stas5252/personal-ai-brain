"""
Persistent SQLite-backed Ingestion Queue for Knowledge Ingestion Factory.
Supports prioritization, retry with exponential backoff, cancellation, and metrics.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from src.brain.db import get_connection
from src.brain.models.knowledge import IngestionJob, IngestionStatus

class IngestionQueue:
    def __init__(self):
        pass

    def clear(self):
        """Clears all jobs in the queue (primarily for testing)."""
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM ingestion_jobs")
        conn.commit()
        conn.close()

    def enqueue_job(self, source_id: str, priority: int = 10, max_attempts: int = 3) -> IngestionJob:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()

        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO ingestion_jobs (
            job_id, source_id, status, priority, stage, attempts, max_attempts,
            next_retry_at, progress, checkpoint_stage, error_message, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, source_id, IngestionStatus.DISCOVERED.value, priority,
            IngestionStatus.DISCOVERED.value, 0, max_attempts,
            now_str, 0.0, None, None, now_str, now_str
        ))
        conn.commit()
        conn.close()

        return IngestionJob(
            job_id=job_id,
            source_id=source_id,
            status=IngestionStatus.DISCOVERED,
            priority=priority,
            stage=IngestionStatus.DISCOVERED.value,
            max_attempts=max_attempts,
            created_at=now_str,
            updated_at=now_str
        )

    def claim_job(self, worker_id: str = "default_worker", lease_seconds: int = 60) -> Optional[IngestionJob]:
        """
        Atomically claims the highest priority ready or stale job with a lease.
        Prevents dual-execution across multiple workers.
        """
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        lease_until_str = (now + timedelta(seconds=lease_seconds)).isoformat()

        conn = get_connection()
        c = conn.cursor()

        # Find candidate job
        c.execute("""
        SELECT job_id, status FROM ingestion_jobs
        WHERE ((status IN ('DISCOVERED', 'RETRY_PENDING') AND (next_retry_at IS NULL OR next_retry_at <= ?))
            OR (status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE') AND lease_until IS NOT NULL AND lease_until <= ?))
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        """, (now_str, now_str))
        row = c.fetchone()
        if not row:
            conn.close()
            return None

        job_id = row["job_id"]
        # Atomically claim
        c.execute("""
        UPDATE ingestion_jobs
        SET worker_id = ?,
            lease_until = ?,
            heartbeat_at = ?,
            status = 'VALIDATING',
            stage = 'VALIDATING',
            attempts = attempts + 1,
            updated_at = ?
        WHERE job_id = ?
        """, (worker_id, lease_until_str, now_str, now_str, job_id))
        conn.commit()

        c.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
        updated_row = c.fetchone()
        conn.close()

        if updated_row and updated_row["worker_id"] == worker_id:
            return self._row_to_job(updated_row)
        return None

    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: int = 60) -> bool:
        """Extends worker lease if worker still holds the job."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        lease_until_str = (now + timedelta(seconds=lease_seconds)).isoformat()

        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        UPDATE ingestion_jobs
        SET lease_until = ?, heartbeat_at = ?, updated_at = ?
        WHERE job_id = ? AND worker_id = ?
        """, (lease_until_str, now_str, now_str, job_id, worker_id))
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def release_job(self, job_id: str, worker_id: str) -> bool:
        """Releases lease on job (e.g. upon graceful shutdown or worker release)."""
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        UPDATE ingestion_jobs
        SET worker_id = NULL, lease_until = NULL, updated_at = ?
        WHERE job_id = ? AND worker_id = ?
        """, (now_str, job_id, worker_id))
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def reclaim_stale_jobs(self, stale_threshold_seconds: int = 60) -> int:
        """Reclaims jobs whose worker lease expired, resetting them for retry."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        SELECT job_id, attempts, max_attempts FROM ingestion_jobs
        WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
          AND lease_until IS NOT NULL
          AND lease_until <= ?
        """, (now_str,))
        stale_rows = c.fetchall()
        reclaimed = 0

        for row in stale_rows:
            job_id = row["job_id"]
            attempts = row["attempts"]
            max_attempts = row["max_attempts"]
            if attempts >= max_attempts:
                c.execute("""
                UPDATE ingestion_jobs
                SET status = 'FAILED', error_message = 'Worker lease expired and max attempts reached',
                    worker_id = NULL, lease_until = NULL, updated_at = ?
                WHERE job_id = ?
                """, (now_str, job_id))
            else:
                c.execute("""
                UPDATE ingestion_jobs
                SET status = 'RETRY_PENDING',
                    worker_id = NULL,
                    lease_until = NULL,
                    next_retry_at = ?,
                    error_message = 'Worker lease expired; reclaimed for retry',
                    updated_at = ?
                WHERE job_id = ?
                """, (now_str, now_str, job_id))
            reclaimed += 1

        conn.commit()
        conn.close()
        return reclaimed

    def get_next_job(self, worker_id: str = "default_worker", lease_seconds: int = 60) -> Optional[IngestionJob]:
        """Convenience method delegating to claim_job."""
        return self.claim_job(worker_id=worker_id, lease_seconds=lease_seconds)

    def update_progress(self, job_id: str, stage: str, progress: float, checkpoint_stage: Optional[str] = None):
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        UPDATE ingestion_jobs
        SET stage = ?, status = ?, progress = ?, checkpoint_stage = COALESCE(?, checkpoint_stage), updated_at = ?
        WHERE job_id = ?
        """, (stage, stage, progress, checkpoint_stage, now_str, job_id))
        conn.commit()
        conn.close()

    def complete_job(self, job_id: str):
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        UPDATE ingestion_jobs
        SET status = 'COMPLETED', stage = 'COMPLETED', progress = 1.0, updated_at = ?
        WHERE job_id = ?
        """, (now_str, job_id))
        conn.commit()
        conn.close()

    def fail_job(self, job_id: str, error_message: str):
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT attempts, max_attempts FROM ingestion_jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return

        attempts = row["attempts"]
        max_attempts = row["max_attempts"]

        if attempts + 1 < max_attempts:
            # Exponential backoff: 5s, 10s, 20s
            backoff_sec = (2 ** attempts) * 5
            next_retry = (now + timedelta(seconds=backoff_sec)).isoformat()
            c.execute("""
            UPDATE ingestion_jobs
            SET status = 'RETRY_PENDING', attempts = attempts + 1, error_message = ?, next_retry_at = ?, updated_at = ?
            WHERE job_id = ?
            """, (error_message, next_retry, now_str, job_id))
        else:
            # Dead letter / terminal failure
            c.execute("""
            UPDATE ingestion_jobs
            SET status = 'FAILED', attempts = attempts + 1, error_message = ?, updated_at = ?
            WHERE job_id = ?
            """, (error_message, now_str, job_id))

        conn.commit()
        conn.close()

    def cancel_job(self, job_id: str):
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE ingestion_jobs SET status = 'SKIPPED', updated_at = ? WHERE job_id = ?", (now_str, job_id))
        conn.commit()
        conn.close()

    def get_job(self, job_id: str) -> Optional[IngestionJob]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return self._row_to_job(row)
        return None

    def get_stats(self) -> Dict[str, Any]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT status, count(*) as cnt FROM ingestion_jobs GROUP BY status")
        counts = {r["status"]: r["cnt"] for r in c.fetchall()}

        c.execute("SELECT count(*) FROM knowledge_sources")
        total_sources = c.fetchone()[0]

        c.execute("SELECT count(*) FROM knowledge_chunks")
        total_chunks = c.fetchone()[0]

        c.execute("SELECT count(*) FROM knowledge_sources WHERE seen_count > 1")
        duplicates = c.fetchone()[0]
        conn.close()

        return {
            "total_sources": total_sources,
            "total_chunks": total_chunks,
            "duplicates_encountered": duplicates,
            "jobs_discovered": counts.get(IngestionStatus.DISCOVERED.value, 0),
            "jobs_processing": counts.get("VALIDATING", 0) + counts.get("EXTRACTING", 0),
            "jobs_completed": counts.get(IngestionStatus.COMPLETED.value, 0),
            "jobs_failed": counts.get(IngestionStatus.FAILED.value, 0),
            "jobs_retry_pending": counts.get(IngestionStatus.RETRY_PENDING.value, 0),
        }

    def _row_to_job(self, row) -> IngestionJob:
        keys = row.keys() if hasattr(row, "keys") else []
        return IngestionJob(
            job_id=row["job_id"],
            source_id=row["source_id"],
            status=IngestionStatus(row["status"]) if row["status"] in IngestionStatus._value2member_map_ else IngestionStatus.FAILED,
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
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
