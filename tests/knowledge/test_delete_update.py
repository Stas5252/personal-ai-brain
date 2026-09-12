"""Source reprocessing and deletion across SQLite, FTS5, and Chroma."""
from pathlib import Path

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.embeddings.implementations import get_embedding_provider
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.models.knowledge import KnowledgeLayer


@pytest.fixture
def factory():
    return KnowledgeIngestionFactory()


@pytest.fixture
def vector_index():
    return ChromaVectorIndex(embedding_provider=get_embedding_provider())


def test_source_deletion_purges_all_stores(factory, vector_index, tmp_path):
    import uuid

    uid = uuid.uuid4().hex[:8]
    unique_keyword = f"ZYLOPHONIC_SECRET_{uid}"
    document = tmp_path / f"purge_test_{uid}.txt"
    document.write_text(
        f"This is a secret document containing {unique_keyword} for purge testing.",
        encoding="utf-8",
    )
    source, chunks = factory.ingest_file(
        document, override_layer=KnowledgeLayer.BUSINESS, force=True
    )
    source_id = source.source_id
    assert chunks

    connection = get_connection()
    assert connection.execute(
        "SELECT COUNT(*) FROM knowledge_sources WHERE source_id = ?", (source_id,)
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,)
    ).fetchone()[0] == len(chunks)
    assert connection.execute(
        "SELECT COUNT(*) FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,)
    ).fetchone()[0] == len(chunks)
    connection.close()

    factory.delete_source(source_id, delete_original=True)

    connection = get_connection()
    assert connection.execute(
        "SELECT COUNT(*) FROM knowledge_sources WHERE source_id = ?", (source_id,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?", (source_id,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,)
    ).fetchone()[0] == 0
    connection.close()

    hits = HybridSearchEngine().search(query=unique_keyword, min_score=0.10)
    assert hits == []


def test_reprocessing_updates_without_zombie_embeddings(factory, tmp_path):
    document = tmp_path / "v1_doc.txt"
    document.write_text(
        "Версия 1: Стоимость часа съемки составляет 5000 рублей.", encoding="utf-8"
    )
    _, chunks_v1 = factory.ingest_file(
        document, override_layer=KnowledgeLayer.BUSINESS, force=True
    )
    assert len(chunks_v1) == 1

    document.write_text(
        "Версия 2: Стоимость часа съемки составляет 9500 рублей. Добавлена новая опция.",
        encoding="utf-8",
    )
    source_v2, _ = factory.ingest_file(
        document, override_layer=KnowledgeLayer.BUSINESS, force=True
    )
    connection = get_connection()
    content = connection.execute(
        "SELECT content FROM knowledge_chunks WHERE source_id = ?", (source_v2.source_id,)
    ).fetchone()[0]
    connection.close()
    assert "9500 рублей" in content
    assert "5000 рублей" not in content
