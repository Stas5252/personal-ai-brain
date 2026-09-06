"""
Embedding Provider Implementations:
- ChromaOnnxEmbeddingProvider (Local ONNX all-MiniLM-L6-v2)
- GeminiEmbeddingProvider (Google Gemini text-embedding-004)
- HashFallbackEmbeddingProvider (Fast deterministic unit-normalized TF/n-gram vectorizer)
"""
import os
import math
import hashlib
import requests
from typing import List, Optional

from src.brain.knowledge.embeddings.provider import EmbeddingProvider
from src.brain.config import EMBEDDING_PROVIDER_TYPE, GEMINI_API_KEY

class ChromaOnnxEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        from chromadb.utils import embedding_functions
        self._fn = embedding_functions.DefaultEmbeddingFunction()

    @property
    def provider_name(self) -> str:
        return "chroma_onnx_all_MiniLM_L6_v2"

    @property
    def dimension(self) -> int:
        return 384

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned = [t if t.strip() else "пустой текст" for t in texts]
        return self._fn(cleaned)

    def embed_query(self, text: str) -> List[float]:
        cleaned = text if text.strip() else "пустой запрос"
        return self._fn([cleaned])[0]

class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.api_key}"

    @property
    def provider_name(self) -> str:
        return "gemini_text_embedding_004"

    @property
    def dimension(self) -> int:
        return 768

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Single or small batch requests
        results = []
        for t in texts:
            results.append(self.embed_query(t))
        return results

    def embed_query(self, text: str) -> List[float]:
        if not self.api_key:
            # Fallback to local if no API key
            return HashFallbackEmbeddingProvider().embed_query(text)
        try:
            payload = {
                "model": "models/text-embedding-004",
                "content": {"parts": [{"text": text[:2048]}]}
            }
            res = requests.post(self.url, json=payload, timeout=10)
            if res.status_code == 200:
                return res.json()["embedding"]["values"]
        except Exception:
            pass
        return HashFallbackEmbeddingProvider().embed_query(text)

class HashFallbackEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashing vectorizer with 128 dimensions and unit normalization."""
    def __init__(self, dim: int = 128):
        self._dim = dim

    @property
    def provider_name(self) -> str:
        return f"hash_deterministic_{self._dim}d"

    @property
    def name(self) -> str:
        return "hash_fallback"

    @property
    def dimension(self) -> int:
        return self._dim

    def _hash_vector(self, text: str) -> List[float]:
        vec = [0.0] * self._dim
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec

        # Token and bigram hashing
        for idx, w in enumerate(words):
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16) % self._dim
            vec[h] += 1.0
            if idx > 0:
                bigram = f"{words[idx-1]}_{w}"
                h2 = int(hashlib.sha256(bigram.encode("utf-8")).hexdigest(), 16) % self._dim
                vec[h2] += 1.5

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._hash_vector(text)

def get_embedding_provider(provider_type: Optional[str] = None) -> EmbeddingProvider:
    ptype = provider_type or EMBEDDING_PROVIDER_TYPE
    if ptype == "gemini":
        return GeminiEmbeddingProvider()
    elif ptype == "hash_fallback":
        return HashFallbackEmbeddingProvider()
    else:
        try:
            return ChromaOnnxEmbeddingProvider()
        except Exception:
            return HashFallbackEmbeddingProvider()
