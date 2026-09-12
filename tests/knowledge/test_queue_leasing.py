"""Queue concurrency, heartbeat, reclamation, release, and fencing tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.models.knowledge import IngestionStatus


def _register_source(source_id: str) -> None:
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO knowledge_sources (
                source_id, title, category, ingestion_status, timestamp,
                mime_type, file_size, sha256
            ) VALUES (?, ?, 'GLOBAL', 'DISCOVERED', ?, 'text/plain', 1, ?)
            """,
            (source_id, source_id, datetime.now(timezone.utc).isoformat(), source_id),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def queue():
    value = IngestionQueue()
    value.clear()
    return value


def test_atomic_lease_claiming_prevents_duplicate_workers(queue):
    _register_source("src-lease-test-1")
    job = queue.enqueue_job(source_id="src-lease-test-1", priority=10)
    barrier = Barrier(2)

    def claim(worker_id):
        barrier.wait()
        return queue.claim_job(worker_id=worker_id, lease_seconds=30)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-alpha", "worker-beta")))
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].job_id == job.job_id
    assert winners[0].lease_token == 1
    assert queue.complete_job(
        job.job_id, winners[0].worker_id, winners[0].lease_token
    )


def test_heartbeat_extends_lease(queue):
    _register_source("src-lease-test-2")
    job = queue.enqueue_job(source_id="src-lease-test-2", priority=10)
    claimed = queue.claim_job(worker_id="worker-gamma", lease_seconds=10)
    initial_lease = claimed.lease_until
    assert queue.heartbeat(
        job.job_id,
        "worker-gamma",
        lease_seconds=60,
        lease_token=claimed.lease_token,
    )
    assert queue.get_job(job.job_id).lease_until > initial_lease
    assert not queue.heartbeat(
        job.job_id,
        "worker-imposter",
        lease_seconds=60,
        lease_token=claimed.lease_token,
    )


def test_stale_job_reclamation_and_fencing(queue):
    _register_source("src-stale-test-3")
    job = queue.enqueue_job(source_id="src-stale-test-3", priority=10)
    stale = queue.claim_job(worker_id="worker-crashed", lease_seconds=30)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE ingestion_jobs SET lease_until = ? WHERE job_id = ?",
            (past, job.job_id),
        )
        connection.commit()
    finally:
        connection.close()

    assert queue.reclaim_stale_jobs(stale_threshold_seconds=1) == 1
    reclaimed = queue.get_job(job.job_id)
    assert reclaimed.status == IngestionStatus.RETRY_PENDING
    assert reclaimed.worker_id is None
    healthy = queue.claim_job(worker_id="worker-healthy", lease_seconds=30)
    assert healthy.lease_token == stale.lease_token + 1
    assert not queue.complete_job(job.job_id, "worker-crashed", stale.lease_token)
    assert queue.complete_job(job.job_id, "worker-healthy", healthy.lease_token)


def test_worker_clean_release_becomes_retry_pending(queue):
    _register_source("src-release-test-4")
    job = queue.enqueue_job(source_id="src-release-test-4", priority=5)
    claimed = queue.claim_job(worker_id="worker-delta", lease_seconds=30)
    assert queue.release_job(job.job_id, "worker-delta", claimed.lease_token)
    released = queue.get_job(job.job_id)
    assert released.status == IngestionStatus.RETRY_PENDING
    assert released.worker_id is None
    assert released.lease_until is None
