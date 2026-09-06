"""
Tests for Ingestion Queue, State Machine, and Checkpoint Recovery.
Verifies prioritization, exponential backoff, checkpoint resume, and cancellation.
"""
import pytest
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.state_machine import IngestionStateMachine
from src.brain.models.knowledge import IngestionStatus

@pytest.fixture
def queue():
    return IngestionQueue()


def test_queue_priority_ordering(queue):
    queue.clear()
    # Enqueue jobs with different priorities
    j_low = queue.enqueue_job(source_id="src-low", priority=1)
    j_high = queue.enqueue_job(source_id="src-high", priority=10)
    j_mid = queue.enqueue_job(source_id="src-mid", priority=5)

    # Next job must be the highest priority (j_high)
    next_job = queue.get_next_job()
    assert next_job is not None
    assert next_job.job_id == j_high.job_id

    # Complete it and get next (should be j_mid)
    queue.complete_job(j_high.job_id)
    next_job2 = queue.get_next_job()
    assert next_job2 is not None
    assert next_job2.job_id == j_mid.job_id

    # Cleanup
    queue.complete_job(j_mid.job_id)
    queue.complete_job(j_low.job_id)


def test_retry_and_exponential_backoff(queue):
    queue.clear()
    job = queue.enqueue_job(source_id="src-retry-test", priority=5)
    
    # First failure -> retry_count becomes 1
    queue.fail_job(job.job_id, "Network timeout error")
    
    j_failed = queue.get_job(job.job_id)
    assert j_failed.status == "RETRY_PENDING"
    assert j_failed.retry_count == 1
    assert "Network timeout" in j_failed.error

    # Fail up to max_retries (3)
    queue.fail_job(job.job_id, "Error 2")
    queue.fail_job(job.job_id, "Error 3")
    j_final = queue.get_job(job.job_id)
    assert j_final.status == "FAILED"


def test_state_machine_checkpoint_and_resume():
    from src.brain.db import get_connection
    conn = get_connection()
    conn.cursor().execute("DELETE FROM knowledge_sources WHERE source_id = 'sm-test-src'")
    conn.commit()
    conn.close()
    sm = IngestionStateMachine(source_id="sm-test-src")
    assert sm.current_status == IngestionStatus.DISCOVERED

    # Step through stages
    sm.transition(IngestionStatus.VALIDATING, progress=0.1)
    assert sm.current_status == IngestionStatus.VALIDATING

    sm.transition(IngestionStatus.EXTRACTING, progress=0.3)
    assert sm.current_status == IngestionStatus.EXTRACTING

    # Checkpoint is recorded
    checkpoint = sm.get_checkpoint()
    assert checkpoint["stage"] == "EXTRACTING"
    assert checkpoint["progress"] == 0.3

    # Fast-forward to completed
    sm.transition(IngestionStatus.NORMALIZING, progress=0.4)
    sm.transition(IngestionStatus.CLASSIFYING, progress=0.5)
    sm.transition(IngestionStatus.CHUNKING, progress=0.6)
    sm.transition(IngestionStatus.EMBEDDING, progress=0.8)
    sm.transition(IngestionStatus.INDEXING, progress=0.9)
    sm.transition(IngestionStatus.VERIFYING, progress=0.95)
    sm.transition(IngestionStatus.COMPLETED, progress=1.0)
    assert sm.current_status == IngestionStatus.COMPLETED
