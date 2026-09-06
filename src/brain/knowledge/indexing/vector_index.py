"""
ChromaDB Vector Index Manager for Knowledge Ingestion Factory.
Provides persistent storage, metadata filtering, and chunk lifecycle operations.
"""
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import chromadb
from chromadb.config import Settings

from src.brain.config import VECTOR_DB_DIR
from src.brain.models.knowledge import KnowledgeChunk
from src.brain.knowledge.embeddings.provider import EmbeddingProvider

COLLECTION_NAME = "brain_knowledge_vectors"

class ChromaVectorIndex:
    def __init__(self, vector_dir: Path = VECTOR_DB_DIR, embedding_provider: Optional[EmbeddingProvider] = None):
        self.vector_dir = Path(vector_dir)
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.vector_dir))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Personal AI Brain Multimodal Knowledge Vectors"}
        )
        self.embedding_provider = embedding_provider

    def upsert_chunks(self, chunks: List[KnowledgeChunk], embeddings: Optional[List[List[float]]] = None):
        """Indexes chunks into ChromaDB with rich metadata for filtering."""
        if not chunks:
            return

        ids = [c.id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = []

        for c in chunks:
            m = {
                "source_id": c.source_id,
                "layer": c.layer.value,
                "content_type": c.content_type.value,
                "page_number": c.page_number or -1,
                "slide_number": c.slide_number or -1,
                "sheet_name": c.sheet_name or "",
                "start_time": c.start_time if c.start_time is not None else -1.0,
                "end_time": c.end_time if c.end_time is not None else -1.0,
                "heading_path": c.heading_path or "",
                "title": c.metadata.title,
                "created_at": c.created_at
            }
            metadatas.append(m)

        if embeddings is not None:
            self.collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        elif self.embedding_provider is not None:
            embeds = self.embedding_provider.embed_documents(documents)
            self.collection.upsert(ids=ids, documents=documents, embeddings=embeds, metadatas=metadatas)
        else:
            # Let Chroma compute embeddings if default function is active
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(
        self,
        query_text: str,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
        layer_filter: Optional[str] = None,
        source_filter: Optional[str] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Queries vector index by vector or text, returning (chunk_id, similarity_score, metadata)."""
        where_filter = None
        conditions = []
        if layer_filter:
            layer_val = str(layer_filter)
            conditions.append({"layer": {"$in": [layer_val, layer_val.upper(), layer_val.lower()]}})
        if source_filter:
            conditions.append({"source_id": source_filter})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        if query_embedding is not None:
            res = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter
            )
        elif self.embedding_provider is not None:
            q_emb = self.embedding_provider.embed_query(query_text)
            res = self.collection.query(
                query_embeddings=[q_emb],
                n_results=top_k,
                where=where_filter
            )
        else:
            res = self.collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where=where_filter
            )

        results = []
        if res and res.get("ids") and res["ids"][0]:
            ids = res["ids"][0]
            distances = res["distances"][0] if res.get("distances") else [0.0] * len(ids)
            metas = res["metadatas"][0] if res.get("metadatas") else [{}] * len(ids)

            for cid, dist, meta in zip(ids, distances, metas):
                # Convert L2 distance to [0, 1] cosine-like similarity
                sim = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
                results.append((cid, sim, meta))

        return results

    def delete_by_source(self, source_id: str):
        """Deletes all vector embeddings associated with a given source_id."""
        try:
            self.collection.delete(where={"source_id": source_id})
        except Exception:
            pass

    def delete_chunk(self, chunk_id: str):
        """Deletes specific chunk from ChromaDB."""
        try:
            self.collection.delete(ids=[chunk_id])
        except Exception:
            pass

    def delete_chunks(self, chunk_ids: List[str]):
        """Deletes multiple chunks from ChromaDB by IDs."""
        if not chunk_ids:
            return
        try:
            self.collection.delete(ids=chunk_ids)
        except Exception:
            pass

    def count(self) -> int:
        return self.collection.count()
