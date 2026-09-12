"""Embedding credentials, dimensions, and persisted vector-space invariants."""
from types import SimpleNamespace

import pytest

from src.brain.knowledge.embeddings.implementations import (
    EmbeddingProviderError,
    GeminiEmbeddingProvider,
    HashFallbackEmbeddingProvider,
)
from src.brain.knowledge.indexing.vector_index import (
    ChromaVectorIndex,
    VectorCollectionMismatch,
)
from src.brain.models.knowledge import (
    ContentType,
    KnowledgeChunk,
    KnowledgeLayer,
    KnowledgeMetadata,
)


class SessionDouble:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def response(status=200, vector=None):
    values = [0.0] * 768 if vector is None else vector
    return SimpleNamespace(status_code=status, json=lambda: {"embedding": {"values": values}})


def test_gemini_key_uses_header_not_url_or_error_text():
    secret = "super-secret-provider-key"
    session = SessionDouble(response())
    provider = GeminiEmbeddingProvider(api_key=secret, session=session)
    assert len(provider.embed_query("test")) == 768
    url, kwargs = session.calls[0]
    assert "{" not in url and "}" not in url
    assert "key=" not in url and secret not in url
    assert kwargs["headers"]["x-goog-api-key"] == secret
    assert kwargs["json"]["taskType"] == "RETRIEVAL_QUERY"


def test_gemini_failure_never_changes_embedding_space():
    provider = GeminiEmbeddingProvider(
        api_key="secret", session=SessionDouble(response(status=429))
    )
    with pytest.raises(EmbeddingProviderError, match="HTTP 429"):
        provider.embed_query("retry later")


def test_invalid_gemini_dimension_is_rejected():
    provider = GeminiEmbeddingProvider(
        api_key="secret", session=SessionDouble(response(vector=[0.0] * 128))
    )
    with pytest.raises(EmbeddingProviderError, match="dimension mismatch"):
        provider.embed_query("wrong vector")


def test_persisted_collection_rejects_provider_switch(tmp_path):
    first_provider = HashFallbackEmbeddingProvider(dim=128)
    first = ChromaVectorIndex(tmp_path, embedding_provider=first_provider)
    metadata = KnowledgeMetadata(
        source_id="source-1", title="Test", category=KnowledgeLayer.GLOBAL
    )
    chunk = KnowledgeChunk(
        id="chunk-1",
        source_id="source-1",
        layer=KnowledgeLayer.GLOBAL,
        content="dimension safety",
        content_type=ContentType.TEXT,
        metadata=metadata,
    )
    first.upsert_chunks([chunk])

    with pytest.raises(VectorCollectionMismatch, match="reindex is required"):
        ChromaVectorIndex(
            tmp_path, embedding_provider=HashFallbackEmbeddingProvider(dim=64)
        )
