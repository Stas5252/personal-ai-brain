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

    def get_next_job(self) -> Optional[IngestionJob]:
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()

        # Pick highest priority, ready to process
        c.execute("""
        SELECT * FROM ingestion_jobs
        WHERE (status = 'DISCOVERED' OR status = 'RETRY_PENDING')
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        """, (now_str,))
        row = c.fetchone()
        if not row:
            conn.close()
            return None

        job_id = row["job_id"]
        # Mark as PROCESSING immediately
        c.execute("""
        UPDATE ingestion_jobs
        SET status = 'VALIDATING', attempts = attempts + 1, updated_at = ?
        WHERE job_id = ?
        """, (now_str, job_id))
        conn.commit()

        c.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
        updated_row = c.fetchone()
        conn.close()

        return self._row_to_job(updated_row)

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
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
