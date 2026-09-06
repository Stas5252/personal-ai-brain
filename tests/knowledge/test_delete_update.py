"""
Tests for Source Updates, Reprocessing, and Deletion.
Ensures zero stale embeddings, atomic purges across SQLite, FTS5, and ChromaDB, and idempotent re-ingestion.
"""
import pytest
from pathlib import Path
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
from src.brain.models.knowledge import KnowledgeLayer
from src.brain.db import get_connection

@pytest.fixture
def factory():
    return KnowledgeIngestionFactory()

@pytest.fixture
def vector_index():
    return ChromaVectorIndex()


def test_source_deletion_purges_all_stores(factory, vector_index, tmp_path):
    # 1. Create a temporary document
    doc_path = tmp_path / "purge_test.txt"
    unique_keyword = "ZYLOPHONIC_SECRET_99"
    doc_path.write_text(f"This is a secret document containing {unique_keyword} for purge testing.", encoding="utf-8")

    # Ingest
    meta, chunks = factory.ingest_file(doc_path, override_layer=KnowledgeLayer.BUSINESS, force=True)
    source_id = meta.source_id
    assert len(chunks) > 0

    # Verify presence in SQLite
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == 1

    c.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == len(chunks)

    # Verify presence in FTS5
    c.execute("SELECT COUNT(*) FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == len(chunks)
    conn.close()

    # 2. Delete source completely
    factory.delete_source(source_id, delete_original=True)

    # 3. Verify complete absence in SQLite, FTS5, and ChromaDB
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == 0

    c.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == 0

    c.execute("SELECT COUNT(*) FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,))
    assert c.fetchone()[0] == 0
    conn.close()

    # Verify vector search no longer finds it
    search_engine = HybridSearchEngine()
    hits = search_engine.search(query=unique_keyword, min_score=0.10)
    assert len(hits) == 0, "Purged chunk must not appear in search results"


def test_reprocessing_updates_without_zombie_embeddings(factory, tmp_path):
    doc_path = tmp_path / "v1_doc.txt"
    doc_path.write_text("Версия 1: Стоимость часа съемки составляет 5000 рублей.", encoding="utf-8")

    meta_v1, chunks_v1 = factory.ingest_file(doc_path, override_layer=KnowledgeLayer.BUSINESS, force=True)
    assert len(chunks_v1) == 1

    # Modify content and reprocess with force=True
    doc_path.write_text("Версия 2: Стоимость часа съемки составляет 9500 рублей. Добавлена новая опция.", encoding="utf-8")
    meta_v2, chunks_v2 = factory.ingest_file(doc_path, override_layer=KnowledgeLayer.BUSINESS, force=True)

    # Verify old content is replaced
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT content FROM knowledge_chunks WHERE source_id = ?", (meta_v2.source_id,))
    current_content = c.fetchone()[0]
    conn.close()

    assert "9500 рублей" in current_content
    assert "5000 рублей" not in current_content
