"""Persistent vector and FTS5 hybrid-search tests."""
from datetime import datetime, timezone

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.embeddings.implementations import get_embedding_provider
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.models.knowledge import KnowledgeChunk, KnowledgeLayer, KnowledgeMetadata


@pytest.fixture
def vector_index():
    return ChromaVectorIndex(embedding_provider=get_embedding_provider())


@pytest.fixture
def hybrid_search():
    return HybridSearchEngine()


def test_chroma_vector_index_operations(vector_index):
    assert vector_index.collection.count() >= 0
    metadata = KnowledgeMetadata(
        source_id="test-vec-src-1",
        title="Тестовый документ",
        category=KnowledgeLayer.BUSINESS,
    )
    chunk = KnowledgeChunk(
        id="test-chunk-vec-1",
        source_id="test-vec-src-1",
        layer=KnowledgeLayer.BUSINESS,
        content="Уникальное соглашение о неразглашении коммерческой тайны фотографа.",
        metadata=metadata,
    )
    vector_index.upsert_chunks([chunk])
    hits = vector_index.query(
        query_text="соглашение о неразглашении тайны",
        top_k=3,
        layer_filter="business",
    )
    assert "test-chunk-vec-1" in [hit[0] for hit in hits]
    vector_index.delete_chunks(["test-chunk-vec-1"])


def test_fts5_lexical_search_and_stemming(hybrid_search):
    source_id = "test-fts-src"
    chunk_id = "test-fts-chunk-1"
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO knowledge_sources (
                source_id, title, category, ingestion_status, timestamp,
                mime_type, file_size, sha256
            ) VALUES (?, 'FTS test', 'PROFESSIONAL', 'COMPLETED', ?,
                      'text/plain', 1, 'fts-test-sha')
            """,
            (source_id, datetime.now(timezone.utc).isoformat()),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO knowledge_chunks (
                id, source_id, layer, content, metadata_json, created_at, content_type
            ) VALUES (?, ?, 'PROFESSIONAL', ?, '{}', ?, 'text')
            """,
            (
                chunk_id,
                source_id,
                "Инструкция по настройке выдержки и диафрагмы на студийной камере.",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO knowledge_chunks_fts (
                chunk_id, source_id, content, heading_path, sheet_name, layer
            ) VALUES (?, ?, ?, '', '', 'PROFESSIONAL')
            """,
            (
                chunk_id,
                source_id,
                "Инструкция по настройке выдержки и диафрагмы на студийной камере.",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    scores = hybrid_search._query_fts5("настройка выдержки и диафрагмы")
    assert scores[chunk_id] > 0.0
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM knowledge_chunks_fts WHERE chunk_id = ?", (chunk_id,)
        )
        connection.execute(
            "DELETE FROM knowledge_sources WHERE source_id = ?", (source_id,)
        )
        connection.commit()
    finally:
        connection.close()


def test_hallucination_prevention_on_unknown_fact(hybrid_search):
    results = hybrid_search.search(
        query="Секретный код от хранилища золотых слитков в бункере 77",
        min_score=0.25,
    )
    assert results == []
