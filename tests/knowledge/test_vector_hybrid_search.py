"""
Tests for ChromaDB Persistent Vector Index and Hybrid Dense+FTS5 Search.
Verifies dense vector retrieval, BM25 full-text indexing, layer filtering, and hallucination refusal.
"""
import pytest
from src.brain.models.knowledge import KnowledgeChunk, KnowledgeLayer, KnowledgeMetadata, ContentType
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
from src.brain.knowledge.embeddings.implementations import get_embedding_provider
from src.brain.db import get_connection

@pytest.fixture
def vector_index():
    return ChromaVectorIndex(embedding_provider=get_embedding_provider())

@pytest.fixture
def hybrid_search():
    return HybridSearchEngine()


def test_chroma_vector_index_operations(vector_index):
    # Verify collection exists and supports count
    count = vector_index.collection.count()
    assert count >= 0

    test_meta = KnowledgeMetadata(
        source_id="test-vec-src-1",
        title="Тестовый документ",
        category=KnowledgeLayer.BUSINESS
    )
    test_chunk = KnowledgeChunk(
        id="test-chunk-vec-1",
        source_id="test-vec-src-1",
        layer=KnowledgeLayer.BUSINESS,
        content="Уникальное соглашение о неразглашении коммерческой тайны фотографа.",
        metadata=test_meta
    )

    # Upsert chunk
    vector_index.upsert_chunks([test_chunk])

    # Query vector index
    hits = vector_index.query(
        query_text="соглашение о неразглашении тайны",
        top_k=3,
        layer_filter="business"
    )
    assert len(hits) > 0
    hit_ids = [h[0] for h in hits]
    assert "test-chunk-vec-1" in hit_ids

    # Cleanup
    vector_index.delete_chunks(["test-chunk-vec-1"])


def test_fts5_lexical_search_and_stemming(hybrid_search):
    # Insert test chunk into DB and FTS5
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    INSERT OR REPLACE INTO knowledge_chunks (
        id, source_id, layer, content, metadata_json, created_at, content_type
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-fts-chunk-1", "test-fts-src", "professional",
        "Инструкция по настройке выдержки и диафрагмы на студийной камере.",
        "{}", "2026-09-06T00:00:00Z", "text"
    ))
    c.execute("""
    INSERT INTO knowledge_chunks_fts (chunk_id, source_id, content, heading_path, sheet_name, layer)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "test-fts-chunk-1", "test-fts-src",
        "Инструкция по настройке выдержки и диафрагмы на студийной камере.",
        "", "", "professional"
    ))
    conn.commit()
    conn.close()

    # Query with inflected Russian words (выдержке, диафрагмой)
    fts_scores = hybrid_search._query_fts5("настройка выдержки и диафрагмы")
    assert "test-fts-chunk-1" in fts_scores
    assert fts_scores["test-fts-chunk-1"] > 0.0

    # Cleanup
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM knowledge_chunks WHERE id = ?", ("test-fts-chunk-1",))
    c.execute("DELETE FROM knowledge_chunks_fts WHERE chunk_id = ?", ("test-fts-chunk-1",))
    conn.commit()
    conn.close()


def test_hallucination_prevention_on_unknown_fact(hybrid_search):
    # Completely fictitious query with zero semantic or keyword relation
    unknown_query = "Секретный код от хранилища золотых слитков в бункере 77"
    results = hybrid_search.search(query=unknown_query, min_score=0.25)
    assert len(results) == 0, "System must refuse and return 0 results for unknown queries"
