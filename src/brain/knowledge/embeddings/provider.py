"""
Embedding Provider Abstraction for Knowledge Ingestion Factory.
"""
from abc import ABC, abstractmethod
from typing import List

class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name/identifier of the embedding provider."""
        pass

    @property
    def name(self) -> str:
        return self.provider_name

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors."""
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a batch of document chunks."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Generates embedding for a single search query."""
        pass

    def embed_text(self, text: str) -> List[float]:
        """Generates embedding for a single text (alias for embed_query)."""
        return self.embed_query(text)
