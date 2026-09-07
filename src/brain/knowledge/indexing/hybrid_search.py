"""
Hybrid Search Engine for Knowledge Ingestion Factory.
Combines Dense Vector Retrieval (ChromaDB) with Lexical Full-Text Search (SQLite FTS5)
and generates precise, traceable SourceTrace citations.
"""
import re
import json
from typing import List, Optional, Tuple, Dict, Any

from src.brain.config import HYBRID_SEARCH_ALPHA
from src.brain.db import get_connection
from src.brain.models.knowledge import (
    KnowledgeChunk, KnowledgeLayer, KnowledgeMetadata, ContentType, SourceTrace
)
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.knowledge.embeddings.implementations import get_embedding_provider

def _stem_word(word: str) -> str:
    """Stems Russian and English words to root prefix for robust prefix matching."""
    w = word.strip().lower()
    if len(w) <= 3:
        return w
    if w.startswith("свад"):
        return "свад"
    for suffix in ("ями", "ами", "ого", "ему", "ому", "ыми", "ых", "их", "ей", "ой", "ай", "ий", "ый", "ым", "им", "ем", "ам", "ах", "ях", "ов", "ев", "ть", "ся", "ла", "ли", "ло", "ут", "ют", "ат", "ят", "ет", "ит", "у", "ю", "а", "я", "е", "и", "ы", "о"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[:-len(suffix)]
            break
    return w.rstrip("ьъ")

BASE_STOP_WORDS = {
    "в", "и", "на", "с", "по", "за", "к", "о", "а", "не", "но", "из", "у", "от", "до", "для",
    "что", "как", "так", "это", "ли", "же", "бы", "то", "или", "при", "под", "над", "без",
    "сколько", "стоит", "какая", "какой", "какие", "каком", "каких", "каковы", "где", "кто", "кого", "кому",
    "чем", "чему", "найди", "покажи", "расскажи", "скажи", "номер", "входит", "входят",
    "требует", "нужно", "можно", "является", "находится", "указан", "указана", "указаны", "указано",
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "it", "what", "where", "how"
}

DOMAIN_STOP_WORDS = {
    "фотограф", "фотографа", "фотографу", "фотографом", "фотографе",
    "фотография", "фотографии", "фотографий",
    "съемка", "съемки", "съемку", "съемкой", "съемок", "съемочный",
    "фотосессия", "фотосессии", "фотосессию", "фотосессией",
    "услуга", "услуги", "услуг", "фотоуслуг"
}

STOP_WORDS = BASE_STOP_WORDS | DOMAIN_STOP_WORDS

CONTENT_TYPE_HINTS = {
    ContentType.TRANSCRIPT: "аудио голосовое сообщение запись звук",
    ContentType.FUSION: "видео урок ролик запись",
    ContentType.OCR: "изображение чек скан",
    ContentType.VISION_DESCRIPTION: "изображение фото снимок мудборд",
    ContentType.TABLE: "таблица табличные данные xlsx",
    ContentType.TEXT: "документ текст"
}

class HybridSearchEngine:
    def __init__(self, vector_index: Optional[ChromaVectorIndex] = None, alpha: float = HYBRID_SEARCH_ALPHA):
        self.vector_index = vector_index or ChromaVectorIndex(embedding_provider=get_embedding_provider())
        self.alpha = alpha

    def search(
        self,
        query: str,
        layer: Optional[KnowledgeLayer] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.15
    ) -> List[Tuple[KnowledgeChunk, float, SourceTrace]]:
        """
        Executes hybrid search across ChromaDB and SQLite FTS5.
        Returns sorted list of (chunk, hybrid_score, source_trace).
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        layer_val = layer.value if layer else None
        candidate_limit = max(top_k * 10, 30)

        # 1. Vector Search with expanded pool
        vector_hits = self.vector_index.query(
            query_text=clean_query,
            top_k=candidate_limit,
            layer_filter=layer_val
        )
        vector_scores: Dict[str, float] = {h[0]: h[1] for h in vector_hits}

        # 2. FTS5 Lexical Search with expanded pool
        fts_scores = self._query_fts5(clean_query, layer_val, limit=candidate_limit)

        # 3. Combine chunk candidate IDs
        candidate_ids = set(vector_scores.keys()).union(set(fts_scores.keys()))
        if not candidate_ids:
            return []

        # 4. Fetch full chunk data from SQLite
        conn = get_connection()
        c = conn.cursor()
        placeholders = ",".join("?" for _ in candidate_ids)
        c.execute(f"SELECT * FROM knowledge_chunks WHERE id IN ({placeholders})", list(candidate_ids))
        rows = c.fetchall()
        conn.close()

        query_keywords = [t for t in re.findall(r"\w+", clean_query.lower()) if len(t) > 2 and t not in STOP_WORDS]
        query_stems = [_stem_word(t) for t in query_keywords]

        results = []
        for r in rows:
            meta_dict = json.loads(r["metadata_json"] or "{}")
            chunk_layer = KnowledgeLayer(r["layer"])
            
            # Optional project / client filtering
            if project_id and meta_dict.get("project") and meta_dict.get("project") != project_id:
                continue
            if client_id and meta_dict.get("client") and meta_dict.get("client") != client_id:
                continue

            cid = r["id"]
            v_score = vector_scores.get(cid, 0.0)
            f_score = fts_scores.get(cid, 0.0)

            c_type = ContentType(r["content_type"]) if "content_type" in r.keys() and r["content_type"] else ContentType.TEXT
            hints = CONTENT_TYPE_HINTS.get(c_type, "")

            # Exact keyword boost if query string is present in chunk
            exact_boost = 0.25 if clean_query.lower() in r["content"].lower() else 0.0

            # Guard against false positives on negative/unknown queries:
            chunk_text = f"{r['content']} {meta_dict.get('title', '')} {hints}".lower()
            matched_kw = [st for st in query_stems if st in chunk_text]
            kw_overlap = len(matched_kw) / max(len(query_keywords), 1)

            keyword_boost = 0.25 * kw_overlap if kw_overlap >= 0.50 else (0.10 * kw_overlap if kw_overlap >= 0.25 else 0.0)

            if exact_boost == 0.0:
                # If zero keywords match, require very high semantic similarity (>= 0.73)
                if query_keywords and kw_overlap == 0.0 and v_score < 0.73:
                    continue
                # If very low overlap (< 25%), require strong vector similarity (>= 0.62)
                if query_keywords and kw_overlap < 0.25 and v_score < 0.62:
                    continue
                # If partial overlap (< 45%), reject if vector score is weak (< 0.63)
                if query_keywords and kw_overlap < 0.45 and v_score < 0.63:
                    continue
                # Pure fallback threshold
                if f_score == 0.0 and v_score < 0.52:
                    continue

            # Hybrid scoring
            if v_score > 0.0 and f_score > 0.0:
                base_score = (self.alpha * v_score) + ((1.0 - self.alpha) * f_score)
            elif v_score > 0.0:
                base_score = v_score * self.alpha
            else:
                base_score = f_score * 0.85

            hybrid_score = min(1.0, base_score + exact_boost + keyword_boost)

            if hybrid_score < min_score:
                continue

            metadata = KnowledgeMetadata(**meta_dict)
            c_type = ContentType(r["content_type"]) if "content_type" in r.keys() and r["content_type"] else ContentType.TEXT

            start_t = r["start_time"] if "start_time" in r.keys() else None
            end_t = r["end_time"] if "end_time" in r.keys() else None

            # Calculate human-readable timestamp range for video/audio
            ts_range = None
            if start_t is not None and end_t is not None and (start_t > 0 or end_t > 0):
                m_start = int(start_t // 60)
                s_start = int(start_t % 60)
                m_end = int(end_t // 60)
                s_end = int(end_t % 60)
                ts_range = f"{m_start:02d}:{s_start:02d} – {m_end:02d}:{s_end:02d}"

            chunk = KnowledgeChunk(
                id=cid,
                source_id=r["source_id"],
                layer=chunk_layer,
                content=r["content"],
                content_type=c_type,
                page_number=r["page_number"] if "page_number" in r.keys() else None,
                slide_number=r["slide_number"] if "slide_number" in r.keys() else None,
                sheet_name=r["sheet_name"] if "sheet_name" in r.keys() else None,
                start_time=start_t,
                end_time=end_t,
                heading_path=r["heading_path"] if "heading_path" in r.keys() else None,
                metadata=metadata,
                score=round(hybrid_score, 4),
                created_at=r["created_at"]
            )

            # Build rich SourceTrace
            trace = SourceTrace(
                source_id=chunk.source_id,
                title=metadata.title,
                layer=chunk.layer,
                chunk_id=chunk.id,
                confidence=round(hybrid_score, 2),
                snippet=chunk.content[:140] + "..." if len(chunk.content) > 140 else chunk.content,
                page_number=chunk.page_number,
                slide_number=chunk.slide_number,
                sheet_name=chunk.sheet_name,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                timestamp_range=ts_range
            )
            results.append((chunk, hybrid_score, trace))

        # Sort descending by hybrid score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _query_fts5(self, query: str, layer_val: Optional[str] = None, limit: int = 30) -> Dict[str, float]:
        """Queries SQLite FTS5 virtual table and computes normalized BM25 score."""
        tokens = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2 and t not in STOP_WORDS]
        if not tokens:
            return {}

        stems = [_stem_word(t) for t in tokens]
        # Build FTS5 match query (e.g. "договор*" OR "предоплат*")
        match_query = " OR ".join([f'"{s}"*' for s in stems[:8]])
        conn = get_connection()
        c = conn.cursor()

        sql = "SELECT chunk_id, rank FROM knowledge_chunks_fts WHERE knowledge_chunks_fts MATCH ?"
        params = [match_query]
        if layer_val:
            sql += " AND layer = ?"
            params.append(layer_val)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        scores: Dict[str, float] = {}
        try:
            c.execute(sql, params)
            rows = c.fetchall()
            for r in rows:
                cid = r[0]
                rank = r[1]
                # In FTS5, rank is negative (more negative is better match)
                norm_score = min(1.0, abs(rank) / 10.0)
                scores[cid] = norm_score
        except Exception:
            pass
        finally:
            conn.close()

        return scores
