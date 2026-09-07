"""
Test Suite: Hardened Source Deletion and Multi-Store Purging.
Verifies: Ingest -> Search Verification -> Delete -> Verify zero zombie chunks
in SQLite knowledge_chunks, FTS5 virtual index, and ChromaDB vector index.
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from src.brain.api.app import app
from src.brain.db import get_connection
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.knowledge.embeddings.implementations import get_embedding_provider

@pytest.fixture
def client():
    return TestClient(app, headers={"Authorization": "Bearer test-brain-key"})

@pytest.fixture
def factory():
    return KnowledgeIngestionFactory()


def test_full_source_deletion_purges_sqlite_fts_and_chroma(client, factory, tmp_path):
    import uuid
    uid = uuid.uuid4().hex[:8]
    unique_marker = f"ЭксклюзивныйКлючУдаления_{uid}"
    test_doc = tmp_path / "deletion_verification.txt"
    test_doc.write_text(f"Документ для проверки полного удаления: {unique_marker} должен исчезнуть.", encoding="utf-8")

    meta, chunks = factory.ingest_file(test_doc, force=True)
    source_id = meta.source_id
    assert len(chunks) > 0

    # 2. Verify search hit before deletion
    search_res = client.post("/knowledge/search", json={"query": unique_marker, "limit": 3})
    assert search_res.status_code == 200
    hits_before = search_res.json()["results"]
    assert len(hits_before) > 0
    assert any(unique_marker in h["chunk"]["content"] for h in hits_before)

    # 3. Call DELETE /knowledge/sources/{source_id}
    del_res = client.delete(f"/knowledge/sources/{source_id}")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "deleted"
    assert del_data["purged_chunks"] == len(chunks)

    # 4. Verify SQLite knowledge_sources has 0 rows for source_id
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == 0

    # 5. Verify SQLite knowledge_chunks has 0 rows for source_id
    c.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == 0

    # 6. Verify SQLite FTS5 has 0 rows matching unique marker
    c.execute("SELECT COUNT(*) FROM knowledge_chunks_fts WHERE content MATCH ?", (unique_marker,))
    assert c.fetchone()[0] == 0
    conn.close()

    # 7. Verify ChromaDB vector index no longer contains chunk IDs
    v_idx = ChromaVectorIndex(embedding_provider=get_embedding_provider())
    chunk_ids = [c.id for c in chunks]
    chroma_res = v_idx.collection.get(ids=chunk_ids)
    assert len(chroma_res["ids"]) == 0

    # 8. Post-deletion search returns zero results
    search_after = client.post("/knowledge/search", json={"query": unique_marker, "limit": 3})
    assert search_after.status_code == 200
    assert len(search_after.json()["results"]) == 0
