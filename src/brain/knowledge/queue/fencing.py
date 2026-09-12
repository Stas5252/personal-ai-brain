"""Lease capabilities that fence SQLite and external ingestion side effects."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Iterator, TypeVar

from src.brain.db import get_connection
from src.brain.models.knowledge import IngestionJob, IngestionStatus

_T = TypeVar("_T")


class LeaseLostError(RuntimeError):
    """Raised before a stale ingestion attempt can perform a side effect."""


@dataclass(frozen=True, slots=True)
class LeaseFence:
    job_id: str
    source_id: str
    worker_id: str
    lease_token: int


def make_fence(job: IngestionJob) -> LeaseFence:
    if not job.worker_id or job.lease_token <= 0:
        raise ValueError("a claimed job with a positive lease token is required")
    return LeaseFence(job.job_id, job.source_id, job.worker_id, job.lease_token)


def _assert_live(connection, queue, fence: LeaseFence) -> None:
    row = connection.execute(
        """
        SELECT 1 FROM ingestion_jobs
        WHERE job_id = ? AND source_id = ? AND worker_id = ? AND lease_token = ?
          AND lease_until IS NOT NULL AND lease_until > ?
          AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED', 'DUPLICATE')
        """,
        (
            fence.job_id, fence.source_id, fence.worker_id,
            fence.lease_token, queue._now().isoformat(),
        ),
    ).fetchone()
    if row is None:
        raise LeaseLostError(
            f"Ingestion lease lost for job {fence.job_id}; stale worker is fenced"
        )


@contextmanager
def fenced_write(queue, fence: LeaseFence) -> Iterator[Any]:
    """Hold SQLite's writer lock from lease validation through side effects."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        _assert_live(connection, queue, fence)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def run_fenced_effect(
    queue,
    fence: LeaseFence,
    effect: Callable[[], _T],
    *,
    renew_for_seconds: int,
) -> _T:
    """Run Chroma mutation while claim/reclaim token turnover is locked out."""
    if renew_for_seconds <= 0:
        raise ValueError("renew_for_seconds must be positive")
    with fenced_write(queue, fence) as connection:
        result = effect()
        now = queue._now()
        updated = connection.execute(
            """
            UPDATE ingestion_jobs
            SET lease_until = ?, heartbeat_at = ?, updated_at = ?
            WHERE job_id = ? AND source_id = ? AND worker_id = ? AND lease_token = ?
            """,
            (
                (now + timedelta(seconds=renew_for_seconds)).isoformat(),
                now.isoformat(), now.isoformat(), fence.job_id, fence.source_id,
                fence.worker_id, fence.lease_token,
            ),
        )
        if updated.rowcount != 1:
            raise LeaseLostError(f"Lease disappeared during job {fence.job_id}")
        return result


def transition(
    queue,
    fence: LeaseFence,
    status: IngestionStatus,
    progress: float,
    *,
    error_message: str | None = None,
) -> None:
    """Atomically transition source and job under the same fence."""
    now = queue._now().isoformat()
    with fenced_write(queue, fence) as connection:
        source = connection.execute(
            """
            UPDATE knowledge_sources
            SET ingestion_status = ?, checkpoint_stage = ?, error_message = ?, timestamp = ?
            WHERE source_id = ?
            """,
            (status.value, status.value, error_message, now, fence.source_id),
        )
        job = connection.execute(
            """
            UPDATE ingestion_jobs
            SET status = ?, stage = ?, checkpoint_stage = ?, error_message = ?,
                progress = ?, updated_at = ? WHERE job_id = ?
            """,
            (
                status.value, status.value, status.value, error_message,
                progress, now, fence.job_id,
            ),
        )
        if source.rowcount != 1 or job.rowcount != 1:
            raise ValueError("fenced source or job disappeared")


def finalize(queue, fence: LeaseFence) -> bool:
    now = queue._now().isoformat()
    with fenced_write(queue, fence) as connection:
        source = connection.execute(
            """
            UPDATE knowledge_sources SET ingestion_status = 'COMPLETED',
                checkpoint_stage = 'COMPLETED', error_message = NULL, timestamp = ?
            WHERE source_id = ?
            """,
            (now, fence.source_id),
        )
        job = connection.execute(
            """
            UPDATE ingestion_jobs SET status = 'COMPLETED', stage = 'COMPLETED',
                checkpoint_stage = 'COMPLETED', progress = 1.0,
                error_message = NULL, worker_id = NULL, lease_until = NULL,
                heartbeat_at = NULL, next_retry_at = NULL, updated_at = ?
            WHERE job_id = ?
            """,
            (now, fence.job_id),
        )
        return source.rowcount == 1 and job.rowcount == 1


def fail_owned(queue, fence: LeaseFence, error_message: str) -> bool:
    """Fail/retry a still-owned attempt; return False when it is already stale."""
    safe_error = str(error_message or "Unknown ingestion error")[:2000]
    try:
        with fenced_write(queue, fence) as connection:
            row = connection.execute(
                "SELECT attempts, max_attempts FROM ingestion_jobs WHERE job_id = ?",
                (fence.job_id,),
            ).fetchone()
            now = queue._now()
            if row["attempts"] < row["max_attempts"]:
                status = IngestionStatus.RETRY_PENDING
                delay = min(300, 5 * (2 ** max(0, row["attempts"] - 1)))
                next_retry = (now + timedelta(seconds=delay)).isoformat()
            else:
                status = IngestionStatus.FAILED
                next_retry = None
            connection.execute(
                """
                UPDATE knowledge_sources SET ingestion_status = ?, checkpoint_stage = ?,
                    error_message = ?, timestamp = ? WHERE source_id = ?
                """,
                (status.value, status.value, safe_error, now.isoformat(), fence.source_id),
            )
            result = connection.execute(
                """
                UPDATE ingestion_jobs SET status = ?, stage = ?, error_message = ?,
                    next_retry_at = ?, worker_id = NULL, lease_until = NULL,
                    heartbeat_at = NULL, updated_at = ? WHERE job_id = ?
                """,
                (
                    status.value, status.value, safe_error, next_retry,
                    now.isoformat(), fence.job_id,
                ),
            )
            return result.rowcount == 1
    except LeaseLostError:
        return False
