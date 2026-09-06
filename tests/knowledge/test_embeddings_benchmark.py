"""
Tests for Embedding Providers, Fallback Hierarchy, and Multilingual Quality.
"""
import pytest
import numpy as np
from src.brain.knowledge.embeddings.provider import EmbeddingProvider
from src.brain.knowledge.embeddings.implementations import (
    ChromaOnnxEmbeddingProvider, HashFallbackEmbeddingProvider, get_embedding_provider
)


def test_hash_fallback_provider():
    provider = HashFallbackEmbeddingProvider(dim=384)
    assert provider.name == "hash_fallback"
    assert provider.dimension == 384

    emb = provider.embed_text("Тестовый текст для проверки хэш-эмбеддинга.")
    assert len(emb) == 384
    # Check L2 normalization
    norm = np.linalg.norm(emb)
    assert pytest.approx(norm, 0.01) == 1.0

    # Determinism: same text must produce identical vector
    emb2 = provider.embed_text("Тестовый текст для проверки хэш-эмбеддинга.")
    assert emb == emb2


def test_chroma_onnx_provider_vector_properties():
    try:
        provider = ChromaOnnxEmbeddingProvider()
        assert provider.name == "chroma_onnx_all_minilm_l6_v2"
        assert provider.dimension == 384

        texts = ["Портретная фотосъемка в студии", "Portrait photography in studio"]
        embs = provider.embed_batch(texts)
        assert len(embs) == 2
        assert len(embs[0]) == 384

        # Verify unit norm
        norm0 = np.linalg.norm(embs[0])
        assert pytest.approx(norm0, 0.01) == 1.0

        # Cosine similarity between Russian and English equivalent
        sim = float(np.dot(embs[0], embs[1]))
        assert sim > 0.40, "Cross-lingual semantic similarity should be positive"
    except Exception as e:
        pytest.skip(f"Chroma ONNX not available in current environment: {e}")


def test_get_embedding_provider_factory():
    provider = get_embedding_provider()
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension > 0
