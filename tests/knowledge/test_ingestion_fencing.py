"""End-to-end lease fencing and retry idempotency regression tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from threading import Event, Thread
import uuid

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.extractors.document_extractor import DocumentExtractor
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.fenced_ingestion import replace_source
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.knowledge.queue.fencing import LeaseLostError, fenced_write, make_fence
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.queue.worker import IngestionWorker
from src.brain.models.knowledge import IngestionStatus


class RecordingVectorIndex:
    def __init__(self, fail_after_replace_once: bool = False):
        self.by_source = {}
        self.fail_after_replace_once = fail_after_replace_once
        self.collection = self

    def get(self, where=None, **kwargs):
        source_id = (where or {}).get("source_id")
        return {"ids": list(self.by_source.get(source_id, {}))}

    def upsert_chunks(self, chunks, embeddings=None):
        for chunk, vector in zip(chunks, embeddings or []):
            self.by_source.setdefault(chunk.source_id, {})[chunk.id] = (
                chunk.content, list(vector)
            )
        if self.fail_after_replace_once:
            self.fail_after_replace_once = False
            raise RuntimeError("injected failure after vector replacement")

    def delete_chunks(self, chunk_ids):
        for rows in self.by_source.values():
            for chunk_id in chunk_ids:
                rows.pop(chunk_id, None)

    def delete_by_source(self, source_id):
        self.by_source.pop(source_id, None)

    def query(self, *args, **kwargs):
        return []


class BlockingTextExtractor:
    def __init__(self, started: Event, release: Event):
        self.started = started
        self.release = release
        self.delegate = DocumentExtractor(strict_pages=False, skip_ocr_if_has_text=True)

    def can_handle(self, extension, mime_type):
        return self.delegate.can_handle(extension, mime_type)

    def extract(self, *args, **kwargs):
        self.started.set()
        assert self.release.wait(timeout=10), "test did not release stale extractor"
        return self.delegate.extract(*args, **kwargs)


def _register_file(factory, tmp_path, source_id):
    path = tmp_path / f"{source_id}.txt"
    path.write_text(f"Уникальный материал {source_id} о студийной фотографии и свете.", encoding="utf-8")
    validation = factory.storage.validate_file(path)
    stored = factory.storage.store_original(path, validation.sha256, validation.safe_filename)
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO knowledge_sources (
                source_id, title, author, date, type, category, storage_path,
                source_path, ingestion_status, checkpoint_stage,
                original_filename, mime_type, file_size, sha256, timestamp,
                tags_json, metadata_json
            ) VALUES (?, ?, 'Author', '2026-09-12', 'document', 'GLOBAL', ?, ?,
                      'DISCOVERED', 'DISCOVERED', ?, 'text/plain', ?, ?, ?, '[]', '{}')
            """,
            (
                source_id, source_id, str(stored), str(stored), path.name,
                validation.file_size, validation.sha256,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return stored


def _expire(job_id):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE ingestion_jobs SET lease_until = ? WHERE job_id = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), job_id),
        )
        connection.commit()
    finally:
        connection.close()


def _snapshot(source_id):
    connection = get_connection()
    try:
        source = dict(connection.execute(
            "SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,)
        ).fetchone())
        chunks = [tuple(row) for row in connection.execute(
            "SELECT * FROM knowledge_chunks WHERE source_id = ? ORDER BY id", (source_id,)
        ).fetchall()]
        fts = [tuple(row) for row in connection.execute(
            """SELECT chunk_id, source_id, content, heading_path, sheet_name, layer
               FROM knowledge_chunks_fts WHERE source_id = ? ORDER BY chunk_id""",
            (source_id,),
        ).fetchall()]
        return source, chunks, fts
    finally:
        connection.close()


def test_stale_fence_rejects_sqlite_write():
    queue = IngestionQueue()
    source_id = f"fence-{uuid.uuid4().hex}"
    connection = get_connection()
    try:
        connection.execute(
            """INSERT INTO knowledge_sources (
                source_id, title, category, ingestion_status, timestamp,
                mime_type, file_size, sha256
            ) VALUES (?, ?, 'GLOBAL', 'DISCOVERED', ?, 'text/plain', 1, ?)""",
            (source_id, source_id, datetime.now(timezone.utc).isoformat(), source_id),
        )
        connection.commit()
    finally:
        connection.close()
    job = queue.enqueue_job(source_id)
    stale = queue.claim_job("stale", lease_seconds=30)
    stale_fence = make_fence(stale)
    _expire(job.job_id)
    assert queue.reclaim_stale_jobs() == 1
    successor = queue.claim_job("successor", lease_seconds=30)
    assert successor.lease_token == stale.lease_token + 1
    with pytest.raises(LeaseLostError):
        with fenced_write(queue, stale_fence) as connection:
            connection.execute(
                "UPDATE knowledge_sources SET title = 'stale' WHERE source_id = ?",
                (source_id,),
            )
    connection = get_connection()
    try:
        assert connection.execute(
            "SELECT title FROM knowledge_sources WHERE source_id = ?", (source_id,)
        ).fetchone()[0] == source_id
    finally:
        connection.execute("DELETE FROM knowledge_sources WHERE source_id = ?", (source_id,))
        connection.commit()
        connection.close()


def test_retry_after_vector_failure_replaces_sqlite_fts_exactly_once(tmp_path):
    queue = IngestionQueue()
    vector = RecordingVectorIndex(fail_after_replace_once=True)
    factory = KnowledgeIngestionFactory(vector_index=vector, strict_mode=False)
    source_id = f"retry-{uuid.uuid4().hex}"
    _register_file(factory, tmp_path, source_id)
    job = queue.enqueue_job(source_id)
    assert IngestionWorker(queue, factory, "worker-one", lease_seconds=30).process_next() is False
    assert queue.get_job(job.job_id).status == IngestionStatus.RETRY_PENDING
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE ingestion_jobs SET next_retry_at = ? WHERE job_id = ?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), job.job_id),
        )
        connection.commit()
    finally:
        connection.close()
    assert IngestionWorker(queue, factory, "worker-two", lease_seconds=30).process_next() is True
    completed = queue.get_job(job.job_id)
    assert completed.status == IngestionStatus.COMPLETED
    assert completed.attempts == 2
    connection = get_connection()
    try:
        chunk_ids = {row[0] for row in connection.execute(
            "SELECT id FROM knowledge_chunks WHERE source_id = ?", (source_id,)
        ).fetchall()}
        fts_rows = connection.execute(
            """SELECT chunk_id, COUNT(*) FROM knowledge_chunks_fts
               WHERE source_id = ? GROUP BY chunk_id""", (source_id,)
        ).fetchall()
    finally:
        connection.close()
    assert chunk_ids
    assert {row[0] for row in fts_rows} == chunk_ids
    assert all(row[1] == 1 for row in fts_rows)
    assert set(vector.by_source[source_id]) == chunk_ids
    factory.delete_source(source_id)


def test_reclaimed_worker_cannot_clobber_successor(tmp_path):
    queue = IngestionQueue()
    vector = RecordingVectorIndex()
    started, release = Event(), Event()
    stale_factory = KnowledgeIngestionFactory(
        vector_index=vector,
        document_extractor=BlockingTextExtractor(started, release),
        strict_mode=False,
    )
    successor_factory = KnowledgeIngestionFactory(vector_index=vector, strict_mode=False)
    source_id = f"overlap-{uuid.uuid4().hex}"
    _register_file(successor_factory, tmp_path, source_id)
    job = queue.enqueue_job(source_id)
    claimed = queue.claim_job("worker-stale", lease_seconds=30)
    stale_worker = IngestionWorker(queue, stale_factory, "worker-stale", lease_seconds=30)
    stale_worker._start_heartbeat = lambda _job: None
    result = []
    thread = Thread(target=lambda: result.append(stale_worker.process_job(claimed)))
    thread.start()
    assert started.wait(timeout=10)
    _expire(job.job_id)
    assert queue.reclaim_stale_jobs() == 1
    successor_worker = IngestionWorker(queue, successor_factory, "worker-successor", lease_seconds=30)
    assert successor_worker.process_next() is True
    expected_sqlite = _snapshot(source_id)
    expected_vectors = dict(vector.by_source[source_id])
    release.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert result == [False]
    assert queue.get_job(job.job_id).status == IngestionStatus.COMPLETED
    assert _snapshot(source_id) == expected_sqlite
    assert vector.by_source[source_id] == expected_vectors
    successor_factory.delete_source(source_id)


def test_vector_replace_source_removes_obsolete_tail():
    class Provider:
        dimension = 2

    class Collection:
        def __init__(self):
            self.rows = {}

        def get(self, where=None, **kwargs):
            source = (where or {}).get("source_id")
            return {"ids": [key for key, row in self.rows.items() if row[0]["source_id"] == source]}

        def upsert(self, ids, documents, embeddings, metadatas):
            for key, metadata, document, embedding in zip(ids, metadatas, documents, embeddings):
                self.rows[key] = (metadata, document, embedding)

        def delete(self, ids=None, where=None):
            if ids is not None:
                for key in ids:
                    self.rows.pop(key, None)

    def chunk(chunk_id):
        return SimpleNamespace(
            id=chunk_id, source_id="source", content=chunk_id,
            layer=SimpleNamespace(value="GLOBAL"),
            content_type=SimpleNamespace(value="text"), page_number=None,
            slide_number=None, sheet_name=None, start_time=None, end_time=None,
            heading_path=None, metadata=SimpleNamespace(title="title"), created_at="now",
        )

    index = object.__new__(ChromaVectorIndex)
    index.embedding_provider = Provider()
    index.collection = Collection()
    first = [chunk("source-chk-1"), chunk("source-chk-2")]
    replace_source(index, "source", first, [[1, 0], [0, 1]])
    replace_source(index, "source", first[:1], [[1, 0]])
    assert set(index.collection.rows) == {"source-chk-1"}
