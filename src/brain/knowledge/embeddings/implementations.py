"""Production embedding provider implementations."""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List, Optional

import requests

from src.brain.config import EMBEDDING_PROVIDER_TYPE, GEMINI_API_KEY
from src.brain.knowledge.embeddings.provider import EmbeddingProvider

GEMINI_EMBEDDING_BASE_URL = os.environ.get(
    "GEMINI_EMBEDDING_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
).rstrip("/")
GEMINI_EMBEDDING_MODEL = os.environ.get(
    "GEMINI_EMBEDDING_MODEL", "text-embedding-004"
).strip()
MAX_EMBEDDING_CHARS = 8_000
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class EmbeddingProviderError(RuntimeError):
    """An embedding provider is unavailable or returned an invalid vector."""


def _validate_vector(vector, expected_dimension: int) -> List[float]:
    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError) as exc:
        raise EmbeddingProviderError("Embedding response is not a numeric vector") from exc
    if len(values) != expected_dimension:
        raise EmbeddingProviderError(
            f"Embedding dimension mismatch: expected {expected_dimension}, got {len(values)}"
        )
    if not all(math.isfinite(value) for value in values):
        raise EmbeddingProviderError("Embedding response contains NaN or infinity")
    return values


class ChromaOnnxEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        try:
            from chromadb.utils import embedding_functions

            self._fn = embedding_functions.DefaultEmbeddingFunction()
        except Exception as exc:
            raise EmbeddingProviderError("Local ONNX embedding provider is unavailable") from exc

    @property
    def provider_name(self) -> str:
        return "chroma_onnx_all_MiniLM_L6_v2"

    @property
    def dimension(self) -> int:
        return 384

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned = [text if text.strip() else "пустой текст" for text in texts]
        vectors = self._fn(cleaned)
        return [_validate_vector(vector, self.dimension) for vector in vectors]

    def embed_query(self, text: str) -> List[float]:
        cleaned = text if text.strip() else "пустой запрос"
        return _validate_vector(self._fn([cleaned])[0], self.dimension)


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        session=None,
    ):
        self.api_key = (api_key or GEMINI_API_KEY or "").strip()
        if not self.api_key:
            raise EmbeddingProviderError("GEMINI_API_KEY is required for Gemini embeddings")
        self.model = (model or GEMINI_EMBEDDING_MODEL).strip()
        if not _MODEL_RE.fullmatch(self.model):
            raise EmbeddingProviderError("Invalid Gemini embedding model name")
        self.url = f"{(base_url or GEMINI_EMBEDDING_BASE_URL).rstrip('/')}/models/{self.model}:embedContent"
        self.session = session or requests.Session()

    @property
    def provider_name(self) -> str:
        return f"gemini_{self.model}"

    @property
    def dimension(self) -> int:
        return 768

    def _embed(self, text: str, task_type: str) -> List[float]:
        payload = {
            "model": f"models/{self.model}",
            "taskType": task_type,
            "content": {"parts": [{"text": (text or "пустой текст")[:MAX_EMBEDDING_CHARS]}]},
        }
        try:
            response = self.session.post(
                self.url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json=payload,
                timeout=(3.05, 30),
            )
        except requests.RequestException as exc:
            raise EmbeddingProviderError("Gemini embedding request failed") from exc
        if response.status_code != 200:
            # Do not include the URL, headers, response body, or API key.
            raise EmbeddingProviderError(
                f"Gemini embedding provider returned HTTP {response.status_code}"
            )
        try:
            vector = response.json()["embedding"]["values"]
        except (ValueError, KeyError, TypeError) as exc:
            raise EmbeddingProviderError("Gemini embedding response is malformed") from exc
        return _validate_vector(vector, self.dimension)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text, "RETRIEVAL_DOCUMENT") for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text, "RETRIEVAL_QUERY")


class HashFallbackEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashing vectorizer intended for tests and explicit fallback mode."""

    def __init__(self, dim: int = 128):
        if dim <= 0:
            raise ValueError("dim must be positive")
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
        vector = [0.0] * self._dim
        words = text.lower().split()
        if not words:
            vector[0] = 1.0
            return vector
        for index, word in enumerate(words):
            position = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % self._dim
            vector[position] += 1.0
            if index > 0:
                bigram = f"{words[index - 1]}_{word}"
                second = int(hashlib.sha256(bigram.encode("utf-8")).hexdigest(), 16) % self._dim
                vector[second] += 1.5
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._hash_vector(text)


def get_embedding_provider(provider_type: Optional[str] = None) -> EmbeddingProvider:
    provider = (provider_type or EMBEDDING_PROVIDER_TYPE or "").strip().lower()
    if provider == "gemini":
        return GeminiEmbeddingProvider()
    if provider == "hash_fallback":
        return HashFallbackEmbeddingProvider()
    if provider in {"chroma_onnx", "onnx"}:
        return ChromaOnnxEmbeddingProvider()
    raise EmbeddingProviderError(f"Unsupported EMBEDDING_PROVIDER_TYPE: {provider!r}")
