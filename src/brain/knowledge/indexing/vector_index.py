"""Dimension-safe ChromaDB vector index manager."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb

from src.brain.config import VECTOR_DB_DIR
from src.brain.knowledge.embeddings.provider import EmbeddingProvider
from src.brain.models.knowledge import KnowledgeChunk

COLLECTION_NAME = "brain_knowledge_vectors"
SPEC_FILENAME = ".embedding-spec.json"
SPEC_SCHEMA_VERSION = 1


class VectorCollectionMismatch(RuntimeError):
    """The configured provider does not match the persisted vector space."""


class ChromaVectorIndex:
    def __init__(
        self,
        vector_dir: Path = VECTOR_DB_DIR,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        if embedding_provider is None:
            raise ValueError("embedding_provider is required for a persistent vector index")
        self.vector_dir = Path(vector_dir)
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider
        self.client = chromadb.PersistentClient(path=str(self.vector_dir))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Personal AI Brain Multimodal Knowledge Vectors"},
        )
        self._validate_persisted_spec()

    @property
    def expected_spec(self) -> Dict[str, Any]:
        return {
            "schema_version": SPEC_SCHEMA_VERSION,
            "provider": self.embedding_provider.provider_name,
            "dimension": int(self.embedding_provider.dimension),
        }

    def _sample_dimension(self) -> Optional[int]:
        if self.collection.count() <= 0:
            return None
        sample = self.collection.get(limit=1, include=["embeddings"])
        embeddings = sample.get("embeddings") if sample else None
        if embeddings is None or len(embeddings) == 0:
            return None
        return len(embeddings[0])

    def _validate_persisted_spec(self) -> None:
        path = self.vector_dir / SPEC_FILENAME
        expected = self.expected_spec
        if path.exists():
            try:
                actual = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise VectorCollectionMismatch("Persisted embedding spec is unreadable") from exc
            if actual != expected:
                raise VectorCollectionMismatch(
                    "Configured embedding provider does not match the persisted vector collection; reindex is required"
                )
            return

        sampled_dimension = self._sample_dimension()
        if sampled_dimension is not None and sampled_dimension != expected["dimension"]:
            raise VectorCollectionMismatch(
                f"Persisted vector dimension is {sampled_dimension}, configured provider requires {expected['dimension']}"
            )
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(expected, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, path)

    def _validate_embeddings(self, embeddings, expected_count: int) -> List[List[float]]:
        if len(embeddings) != expected_count:
            raise ValueError(
                f"Embedding count mismatch: expected {expected_count}, got {len(embeddings)}"
            )
        result: List[List[float]] = []
        expected_dimension = int(self.embedding_provider.dimension)
        for vector in embeddings:
            values = [float(value) for value in vector]
            if len(values) != expected_dimension:
                raise VectorCollectionMismatch(
                    f"Vector dimension mismatch: expected {expected_dimension}, got {len(values)}"
                )
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Vector contains NaN or infinity")
            result.append(values)
        return result

    def upsert_chunks(
        self,
        chunks: List[KnowledgeChunk],
        embeddings: Optional[List[List[float]]] = None,
    ):
        if not chunks:
            return
        ids = [chunk.id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            metadatas.append(
                {
                    "source_id": chunk.source_id,
                    "layer": chunk.layer.value,
                    "content_type": chunk.content_type.value,
                    "page_number": chunk.page_number or -1,
                    "slide_number": chunk.slide_number or -1,
                    "sheet_name": chunk.sheet_name or "",
                    "start_time": chunk.start_time if chunk.start_time is not None else -1.0,
                    "end_time": chunk.end_time if chunk.end_time is not None else -1.0,
                    "heading_path": chunk.heading_path or "",
                    "title": chunk.metadata.title,
                    "created_at": chunk.created_at,
                }
            )
        vectors = embeddings
        if vectors is None:
            vectors = self.embedding_provider.embed_documents(documents)
        validated = self._validate_embeddings(vectors, len(chunks))
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=validated,
            metadatas=metadatas,
        )

    def query(
        self,
        query_text: str,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
        layer_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        conditions = []
        if layer_filter:
            value = str(layer_filter)
            conditions.append({"layer": {"$in": [value, value.upper(), value.lower()]}})
        if source_filter:
            conditions.append({"source_id": source_filter})
        where_filter = None
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        vector = query_embedding
        if vector is None:
            vector = self.embedding_provider.embed_query(query_text)
        validated = self._validate_embeddings([vector], 1)[0]
        response = self.collection.query(
            query_embeddings=[validated], n_results=top_k, where=where_filter
        )

        results: List[Tuple[str, float, Dict[str, Any]]] = []
        if response and response.get("ids") and response["ids"][0]:
            ids = response["ids"][0]
            distances = response.get("distances", [[0.0] * len(ids)])[0]
            metadatas = response.get("metadatas", [[{}] * len(ids)])[0]
            for chunk_id, distance, metadata in zip(ids, distances, metadatas):
                similarity = max(0.0, min(1.0, 1.0 - (float(distance) / 2.0)))
                results.append((chunk_id, similarity, metadata or {}))
        return results

    def delete_by_source(self, source_id: str):
        self.collection.delete(where={"source_id": source_id})

    def delete_chunk(self, chunk_id: str):
        self.collection.delete(ids=[chunk_id])

    def delete_chunks(self, chunk_ids: List[str]):
        if chunk_ids:
            self.collection.delete(ids=chunk_ids)

    def count(self) -> int:
        return self.collection.count()
