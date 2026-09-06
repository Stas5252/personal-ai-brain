"""
Hierarchical Knowledge Engine with 6 Layers, Metadata, and Source Traceability.
"""
import uuid
import json
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from src.brain.db import get_connection
from src.brain.models.knowledge import (
    KnowledgeLayer, KnowledgeMetadata, KnowledgeChunk, SourceTrace, HallucinationType
)

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
            
        conn.commit()
        conn.close()
        return meta, chunks

    def retrieve(
        self,
        query: str,
        layer: Optional[KnowledgeLayer] = None,
        project: Optional[str] = None,
        client: Optional[str] = None,
        limit: int = 4
    ) -> List[Tuple[KnowledgeChunk, float, SourceTrace]]:
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
            
        query_words = set(re.findall(r"\w+", query.lower()))
        scored_chunks = []
        
        for r in rows:
            meta = KnowledgeMetadata(**json.loads(r["metadata_json"]))
            
            # Optional project / client filtering
            if project and meta.project and meta.project != project:
                continue
            if client and meta.client and meta.client != client:
                continue
                
            chunk_words = set(re.findall(r"\w+", r["content"].lower()))
            common = query_words.intersection(chunk_words)
            
            if not common:
                score = 0.0
            else:
                score = len(common) / max(len(query_words), 1)
                
            # Exact phrase boost
            if query.lower() in r["content"].lower():
                score = max(score, 0.95)
                
            if score > 0.15:
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
                    snippet=chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content
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
