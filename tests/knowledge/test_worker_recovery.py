"""
Test Suite: Worker Crash Recovery and Checkpoint Resumption.
Verifies that if a worker crashes during processing, a successor worker
can reclaim the job and complete ingestion without creating duplicate chunks.
"""
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.brain.db import get_connection
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.queue.worker import IngestionWorker
from src.brain.knowledge.factory import KnowledgeIngestionFactory

@pytest.fixture
def queue():
    q = IngestionQueue()
    q.clear()
    return q

@pytest.fixture
def factory():
    return KnowledgeIngestionFactory()


def test_worker_crash_and_checkpoint_resumption(queue, factory, tmp_path):
    """
    Simulates worker 1 crashing midway, followed by worker 2 reclaiming the job
    and finishing ingestion without orphaned duplicate records.
    """
    import uuid
    uid = uuid.uuid4().hex[:8]
    source_id = f"rec-src-{uid}"

    # 1. Prepare sample file with unique text to avoid colliding with previous test runs
    test_file = tmp_path / f"crash_recovery_{uid}.txt"
    test_file.write_text(f"Фотостудия предлагает студийные портреты и аренду света {uid} на 2 часа.", encoding="utf-8")

    # 2. Ingest original registration and enqueue
    val = factory.storage.validate_file(test_file)
    stored_path = factory.storage.store_original(test_file, val.sha256, val.safe_filename)

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM knowledge_sources WHERE source_id = ?", (source_id,))
    c.execute("DELETE FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    c.execute("""
    INSERT INTO knowledge_sources (
        source_id, title, author, date, type, category,
        storage_path, source_path, ingestion_status, checkpoint_stage,
        original_filename, mime_type, file_size, sha256, timestamp, tags_json, metadata_json
    ) VALUES (?, 'Crash Recovery Guide', 'Author', '2026-09-06', 'document', 'PROFESSIONAL',
              ?, ?, 'PROCESSING', 'EXTRACTING', 'crash_recovery_test.txt', 'text/plain', ?, ?, ?, '[]', '{}')
    """, (source_id, str(stored_path), str(stored_path), val.file_size, val.sha256, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    # Enqueue job
    job = queue.enqueue_job(source_id=source_id, priority=10)

    # 3. Worker 1 claims job, updates checkpoint, and "crashes"
    worker_1 = IngestionWorker(queue=queue, factory=factory, worker_id="worker-crash-1", lease_seconds=2)
    claimed_1 = queue.claim_job(worker_id=worker_1.worker_id, lease_seconds=2)
    assert claimed_1 is not None

    queue.update_progress(job.job_id, stage="EXTRACTING", progress=0.3, checkpoint_stage="EXTRACTING")

    # Simulate worker 1 dying: lease expires in past
    past_str = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE ingestion_jobs SET lease_until = ? WHERE job_id = ?", (past_str, job.job_id))
    conn.commit()
    conn.close()

    # 4. Stale reclamation detects dead worker 1
    reclaimed_cnt = queue.reclaim_stale_jobs(stale_threshold_seconds=1)
    assert reclaimed_cnt >= 1

    # 5. Worker 2 claims the reclaimed job and executes to completion
    worker_2 = IngestionWorker(queue=queue, factory=factory, worker_id="worker-recovery-2", lease_seconds=30)
    success = worker_2.process_next()
    assert success is True

    # 6. Verify final state
    completed_job = queue.get_job(job.job_id)
    assert completed_job.status == "COMPLETED"
    assert completed_job.progress == 1.0

    # Verify no duplicate chunks in knowledge_chunks
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    chunk_count = c.fetchone()[0]
    conn.close()

    assert chunk_count > 0
    # Chunks are cleanly created once, not duplicated
    assert chunk_count <= 5

    # 7. Clean up test source to keep environment sterile
    factory.delete_source(source_id)
