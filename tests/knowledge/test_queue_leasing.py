"""
Test Suite: Queue Leasing, Concurrency, Heartbeat, and Stale Job Reclamation.
Verifies that atomic leasing prevents split-brain processing, heartbeats extend leases,
and abandoned jobs are cleanly recovered.
"""
import time
import pytest
from datetime import datetime, timezone, timedelta

from src.brain.db import get_connection
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.models.knowledge import IngestionStatus

@pytest.fixture
def queue():
    q = IngestionQueue()
    q.clear()
    return q


def test_atomic_lease_claiming_prevents_duplicate_workers(queue):
    """Verifies that two workers attempting to claim the same job cannot both get it."""
    job = queue.enqueue_job(source_id="src-lease-test-1", priority=10)

    # Worker 1 claims job
    claimed_1 = queue.claim_job(worker_id="worker-alpha", lease_seconds=30)
    assert claimed_1 is not None
    assert claimed_1.job_id == job.job_id
    assert claimed_1.worker_id == "worker-alpha"
    assert claimed_1.lease_until is not None

    # Worker 2 attempts to claim next job - should be None because job is leased
    claimed_2 = queue.claim_job(worker_id="worker-beta", lease_seconds=30)
    assert claimed_2 is None

    # Complete job
    queue.complete_job(job.job_id)


def test_heartbeat_extends_lease(queue):
    """Verifies that worker heartbeat extends the lease_until timestamp."""
    job = queue.enqueue_job(source_id="src-lease-test-2", priority=10)
    claimed = queue.claim_job(worker_id="worker-gamma", lease_seconds=10)
    initial_lease = claimed.lease_until

    # Worker sends heartbeat with 60s lease
    ok = queue.heartbeat(job_id=job.job_id, worker_id="worker-gamma", lease_seconds=60)
    assert ok is True

    # Check updated lease in DB
    refreshed = queue.get_job(job.job_id)
    assert refreshed.lease_until > initial_lease

    # Another worker cannot heartbeat a job it does not own
    bad_hb = queue.heartbeat(job_id=job.job_id, worker_id="worker-imposter", lease_seconds=60)
    assert bad_hb is False


def test_stale_job_reclamation(queue):
    """Verifies that a job whose lease expired in the past is automatically reclaimed."""
    job = queue.enqueue_job(source_id="src-stale-test-3", priority=10)
    claimed = queue.claim_job(worker_id="worker-crashed", lease_seconds=1)

    # Manually expire the lease in the past
    past_str = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE ingestion_jobs SET lease_until = ? WHERE job_id = ?", (past_str, job.job_id))
    conn.commit()
    conn.close()

    # Reclaim stale jobs
    reclaimed = queue.reclaim_stale_jobs(stale_threshold_seconds=1)
    assert reclaimed >= 1

    # Verify job status reset to RETRY_PENDING and worker_id cleared
    reclaimed_job = queue.get_job(job.job_id)
    assert reclaimed_job.status == "RETRY_PENDING"
    assert reclaimed_job.worker_id is None
    assert reclaimed_job.lease_until is None

    # Now a healthy worker can claim the reclaimed job
    healthy_claim = queue.claim_job(worker_id="worker-healthy", lease_seconds=30)
    assert healthy_claim is not None
    assert healthy_claim.job_id == job.job_id
    assert healthy_claim.worker_id == "worker-healthy"


def test_worker_clean_release(queue):
    """Verifies that release_job clears worker lease attributes."""
    job = queue.enqueue_job(source_id="src-release-test-4", priority=5)
    claimed = queue.claim_job(worker_id="worker-delta", lease_seconds=30)
    assert claimed.worker_id == "worker-delta"

    ok = queue.release_job(job.job_id, "worker-delta")
    assert ok is True

    released_job = queue.get_job(job.job_id)
    assert released_job.worker_id is None
    assert released_job.lease_until is None
