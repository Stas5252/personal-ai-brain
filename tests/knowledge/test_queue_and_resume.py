"""Queue priority, retries, and source checkpoint tests."""
from datetime import datetime, timedelta, timezone

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.state_machine import IngestionStateMachine
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


def _make_ready(job_id: str) -> None:
    ready_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE ingestion_jobs SET next_retry_at = ? WHERE job_id = ?",
            (ready_at, job_id),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def queue():
    value = IngestionQueue()
    value.clear()
    return value


def test_queue_priority_ordering(queue):
    for source_id in ("src-low", "src-high", "src-mid"):
        _register_source(source_id)
    low = queue.enqueue_job(source_id="src-low", priority=1)
    high = queue.enqueue_job(source_id="src-high", priority=10)
    mid = queue.enqueue_job(source_id="src-mid", priority=5)

    claimed_high = queue.get_next_job(worker_id="priority-worker")
    assert claimed_high.job_id == high.job_id
    assert queue.complete_job(high.job_id, "priority-worker", claimed_high.lease_token)
    claimed_mid = queue.get_next_job(worker_id="priority-worker")
    assert claimed_mid.job_id == mid.job_id
    assert queue.complete_job(mid.job_id, "priority-worker", claimed_mid.lease_token)
    claimed_low = queue.get_next_job(worker_id="priority-worker")
    assert claimed_low.job_id == low.job_id
    assert queue.complete_job(low.job_id, "priority-worker", claimed_low.lease_token)


def test_retry_and_exponential_backoff(queue):
    _register_source("src-retry-test")
    job = queue.enqueue_job(source_id="src-retry-test", priority=5)

    first = queue.claim_job("retry-worker")
    assert queue.fail_job(job.job_id, "Network timeout error", "retry-worker", first.lease_token)
    failed_once = queue.get_job(job.job_id)
    assert failed_once.status == IngestionStatus.RETRY_PENDING
    assert failed_once.retry_count == 1
    assert "Network timeout" in failed_once.error

    _make_ready(job.job_id)
    second = queue.claim_job("retry-worker")
    assert queue.fail_job(job.job_id, "Error 2", "retry-worker", second.lease_token)
    _make_ready(job.job_id)
    third = queue.claim_job("retry-worker")
    assert queue.fail_job(job.job_id, "Error 3", "retry-worker", third.lease_token)
    final = queue.get_job(job.job_id)
    assert final.status == IngestionStatus.FAILED
    assert final.retry_count == 3


def test_state_machine_checkpoint_and_resume():
    source_id = "sm-test-src"
    connection = get_connection()
    try:
        connection.execute("DELETE FROM knowledge_sources WHERE source_id = ?", (source_id,))
        connection.commit()
    finally:
        connection.close()
    machine = IngestionStateMachine(source_id=source_id)
    assert machine.current_status == IngestionStatus.DISCOVERED
    machine.transition(IngestionStatus.VALIDATING, progress=0.1)
    machine.transition(IngestionStatus.EXTRACTING, progress=0.3)
    assert machine.get_checkpoint() == {"stage": "EXTRACTING", "progress": 0.3}
    machine.transition(IngestionStatus.NORMALIZING, progress=0.4)
    machine.transition(IngestionStatus.CLASSIFYING, progress=0.5)
    machine.transition(IngestionStatus.CHUNKING, progress=0.6)
    machine.transition(IngestionStatus.EMBEDDING, progress=0.8)
    machine.transition(IngestionStatus.INDEXING, progress=0.9)
    machine.transition(IngestionStatus.VERIFYING, progress=0.95)
    machine.transition(IngestionStatus.COMPLETED, progress=1.0)
    assert machine.current_status == IngestionStatus.COMPLETED
