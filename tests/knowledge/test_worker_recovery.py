"""Worker crash recovery and checkpoint resumption tests."""
from datetime import datetime, timedelta, timezone

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.queue.worker import IngestionWorker


@pytest.fixture
def queue():
    value = IngestionQueue()
    value.clear()
    return value


@pytest.fixture
def factory():
    return KnowledgeIngestionFactory()


def test_worker_crash_and_checkpoint_resumption(queue, factory, tmp_path):
    import uuid

    unique = uuid.uuid4().hex[:8]
    source_id = f"rec-src-{unique}"
    test_file = tmp_path / f"crash_recovery_{unique}.txt"
    test_file.write_text(
        f"Фотостудия предлагает студийные портреты и аренду света {unique} на 2 часа.",
        encoding="utf-8",
    )
    validation = factory.storage.validate_file(test_file)
    stored_path = factory.storage.store_original(
        test_file, validation.sha256, validation.safe_filename
    )

    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO knowledge_sources (
                source_id, title, author, date, type, category, storage_path,
                source_path, ingestion_status, checkpoint_stage,
                original_filename, mime_type, file_size, sha256, timestamp,
                tags_json, metadata_json
            ) VALUES (?, 'Crash Recovery Guide', 'Author', '2026-09-06',
                      'document', 'PROFESSIONAL', ?, ?, 'PROCESSING',
                      'EXTRACTING', 'crash_recovery_test.txt', 'text/plain',
                      ?, ?, ?, '[]', '{}')
            """,
            (
                source_id,
                str(stored_path),
                str(stored_path),
                validation.file_size,
                validation.sha256,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    job = queue.enqueue_job(source_id=source_id, priority=10)
    worker_1 = IngestionWorker(
        queue=queue, factory=factory, worker_id="worker-crash-1", lease_seconds=2
    )
    claimed = queue.claim_job(worker_id=worker_1.worker_id, lease_seconds=2)
    assert queue.update_progress(
        job.job_id,
        stage="EXTRACTING",
        progress=0.3,
        checkpoint_stage="EXTRACTING",
        worker_id=worker_1.worker_id,
        lease_token=claimed.lease_token,
    )

    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
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

    worker_2 = IngestionWorker(
        queue=queue, factory=factory, worker_id="worker-recovery-2", lease_seconds=30
    )
    assert worker_2.process_next() is True
    completed = queue.get_job(job.job_id)
    assert completed.status == "COMPLETED"
    assert completed.progress == 1.0

    connection = get_connection()
    try:
        chunk_count = connection.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,)
        ).fetchone()[0]
    finally:
        connection.close()
    assert 0 < chunk_count <= 5
    factory.delete_source(source_id)
