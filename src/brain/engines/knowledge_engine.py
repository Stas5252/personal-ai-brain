"""
Hierarchical Knowledge Engine with 6 Layers, Metadata, and Source Traceability.
"""
import uuid
import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from src.brain.db import get_connection
from src.brain.models.knowledge import (
    KnowledgeLayer, KnowledgeMetadata, KnowledgeChunk, SourceTrace, HallucinationType
)

logger = logging.getLogger(__name__)

# Chunks can land in SQLite and still be missing from the vector index. That
# used to happen in total silence, so the knowledge base looked healthy while
# semantic search quietly degraded to keyword matching.
_VECTOR_SYNC_FAILURES = 0

# Below this a match is noise rather than an answer.
MIN_LEXICAL_SCORE = 0.15


def vector_sync_failures() -> int:
    """How many sources failed to reach the vector index in this process."""
    return _VECTOR_SYNC_FAILURES


class KnowledgeEngine:
    def __init__(self):
        pass

    def add_source(
        self,
        title: str,
        content: str,
        layer: KnowledgeLayer,
        source_type: str = "document",
        author: str = "Owner",
        subcategory: Optional[str] = None,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        client: Optional[str] = None,
        source_path: Optional[str] = None,
        visual_description: Optional[str] = None,
        ocr_text: Optional[str] = None
    ) -> Tuple[KnowledgeMetadata, List[KnowledgeChunk]]:
        source_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        meta = KnowledgeMetadata(
            source_id=source_id,
            title=title,
            author=author,
            date=date_str,
            type=source_type,
            category=layer,
            subcategory=subcategory,
            tags=tags or [],
            project=project,
            client=client,
            source_path=source_path,
            timestamp=now_str,
            visual_description=visual_description,
            ocr_text=ocr_text
        )
        
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO knowledge_sources (
            source_id, title, author, date, type, category, subcategory,
            tags_json, project, client, language, source_path, timestamp,
            confidence, visual_description, ocr_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meta.source_id, meta.title, meta.author, meta.date, meta.type,
            meta.category.value, meta.subcategory, json.dumps(meta.tags),
            meta.project, meta.client, meta.language, meta.source_path,
            meta.timestamp, meta.confidence, meta.visual_description, meta.ocr_text
        ))
        
        # Split content into chunks (paragraphs/sections)
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [content.strip()]
            
        chunks = []
        for idx, p in enumerate(paragraphs):
            chunk_id = f"{source_id}-chk-{idx+1}"
            chunk = KnowledgeChunk(
                id=chunk_id,
                source_id=source_id,
                layer=layer,
                content=p,
                metadata=meta,
                created_at=now_str
            )
            chunks.append(chunk)
            c.execute("""
            INSERT INTO knowledge_chunks (id, source_id, layer, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (chunk.id, chunk.source_id, chunk.layer.value, chunk.content, meta.model_dump_json(), chunk.created_at))

            # Sync FTS5
            c.execute("""
            INSERT INTO knowledge_chunks_fts (chunk_id, source_id, content, heading_path, sheet_name, layer)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (chunk.id, chunk.source_id, chunk.content, meta.title, "", chunk.layer.value))
            
        conn.commit()
        conn.close()

        # Sync ChromaDB Vector Index
        try:
            from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
            from src.brain.knowledge.embeddings.implementations import get_embedding_provider
            v_index = ChromaVectorIndex(embedding_provider=get_embedding_provider())
            v_index.upsert_chunks(chunks)
        except Exception:
            # Not fatal: the chunks are already in SQLite and FTS5, so lexical
            # retrieval still finds them. But it must never be silent again.
            global _VECTOR_SYNC_FAILURES
            _VECTOR_SYNC_FAILURES += 1
            logger.warning(
                "Vector index sync failed for source %s (%r); %d chunk(s) are searchable "
                "through SQLite/FTS5 only. Semantic search is degraded until this is fixed.",
                source_id, title, len(chunks), exc_info=True,
            )

        return meta, chunks

    def retrieve(
        self,
        query: str,
        layer: Optional[KnowledgeLayer] = None,
        project: Optional[str] = None,
        client: Optional[str] = None,
        limit: int = 4
    ) -> List[Tuple[KnowledgeChunk, float, SourceTrace]]:
        """
        Executes hybrid vector + lexical search across all 6 layers.
        Falls back to lexical matching if the vector store is uninitialized or
        returns nothing, so a broken index degrades the answer instead of
        emptying it.
        """
        from src.brain.knowledge.text_match import lexical_score, query_topic, topic_bonus

        try:
            from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
            engine = HybridSearchEngine()
            hybrid_results = engine.search(
                query=query,
                layer=layer,
                project_id=project,
                client_id=client,
                top_k=limit
            )
            if hybrid_results:
                return hybrid_results
            logger.info("Hybrid search returned nothing for %r; retrying lexically.", query)
        except Exception:
            logger.warning(
                "Hybrid search unavailable for %r; falling back to the lexical scan.",
                query, exc_info=True,
            )

        # Robust lexical fallback
        conn = get_connection()
        c = conn.cursor()
        sql = "SELECT * FROM knowledge_chunks WHERE 1=1"
        params = []
        if layer:
            sql += " AND layer = ?"
            params.append(layer.value)
            
        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            return []

        # The question is routed into the same nine topics the course corpus is
        # indexed under, so a pricing question prefers pricing lessons.
        topic = query_topic(query)
        scored_chunks = []
        
        for r in rows:
            try:
                meta = KnowledgeMetadata(**json.loads(r["metadata_json"]))
            except Exception:
                # One unreadable row must not empty the whole answer.
                logger.warning("Skipping chunk %s: unreadable metadata.", r["id"], exc_info=True)
                continue

            if project and meta.project and meta.project != project:
                continue
            if client and meta.client and meta.client != client:
                continue

            score = lexical_score(query, r["content"])
            if score > 0.0:
                # Topic agreement only strengthens a chunk that already matched;
                # it can never pull in an unrelated one.
                score = min(1.0, score + topic_bonus(topic, meta.subcategory))

            if score > MIN_LEXICAL_SCORE:
                chunk = KnowledgeChunk(
                    id=r["id"],
                    source_id=r["source_id"],
                    layer=KnowledgeLayer(r["layer"]),
                    content=r["content"],
                    metadata=meta,
                    score=score,
                    created_at=r["created_at"]
                )
                trace = SourceTrace(
                    source_id=meta.source_id,
                    title=meta.title,
                    layer=chunk.layer,
                    chunk_id=chunk.id,
                    confidence=round(score, 2),
                    snippet=chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content,
                    page_number=meta.page_number,
                    slide_number=meta.slide_number,
                    sheet_name=meta.sheet_name,
                    start_time=meta.start_time,
                    end_time=meta.end_time
                )
                scored_chunks.append((chunk, score, trace))
                
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:limit]

    def evaluate_hallucination(self, query: str, retrieved_chunks: List[Any], answer: str) -> HallucinationType:
        """
        Classifies whether the response is grounded, inferential, general knowledge, or unknown.
        """
        if not retrieved_chunks:
            # If nothing was retrieved and answer states lack of info
            if any(w in answer.lower() for w in ["не найден", "не указан", "not found", "нет информаци", "не содержит"]):
                return HallucinationType.UNKNOWN
            return HallucinationType.GENERAL_KNOWLEDGE
            
        # If retrieved chunks exist, check if answer references retrieved facts
        all_chunk_text = " ".join([c[0].content.lower() for c in retrieved_chunks])
        ans_words = set(re.findall(r"\w+", answer.lower()))
        chunk_words = set(re.findall(r"\w+", all_chunk_text))
        
        overlap = ans_words.intersection(chunk_words)
        if len(overlap) >= 3:
            return HallucinationType.GROUNDED
        return HallucinationType.INFERENCE
