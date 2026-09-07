"""
Memory Engine with Admission Policy, Scored Retrieval, and Conflict Resolution.
"""
import uuid
import json
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any
from src.brain.db import get_connection
from src.brain.models.memory import (
    MemoryItem, MemoryType, MemoryStatus, AdmissionAction, AdmissionDecision
)

class MemoryEngine:
    def __init__(self):
        pass

    def evaluate_admission(self, text: str) -> AdmissionDecision:
        """
        Determines whether an utterance should be saved, updated, ignored, or kept temporarily.
        """
        t = text.lower().strip()
        
        # 1. Ignored utterances (greetings, short affirmations, filler)
        if len(t) < 8 or t in ["привет", "здравствуй", "пока", "спасибо", "ок", "ясно", "хорошо", "да", "нет"]:
            return AdmissionDecision(action=AdmissionAction.IGNORE, reason="Conversational filler")
            
        # 2. Preference statements
        if any(p in t for p in ["не используй", "запрещено", "всегда отвечай", "предпочитаю", "мне нравится", "не пиши", "стиль общения"]):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="User preference rule detected",
                memory_type=MemoryType.PREFERENCE,
                importance=0.95,
                confidence=0.95,
                extracted_fact=text.strip()
            )
            
        # 3. Client / Project facts
        if any(p in t for p in ["клиент", "пакет", "заказ", "договор", "оплатил", "выбрала", "выбрал", "съемка для"]):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="Client or project transaction fact",
                memory_type=MemoryType.CLIENT if "клиент" in t else MemoryType.PROJECT,
                importance=0.85,
                confidence=0.90,
                extracted_fact=text.strip()
            )
            
        # 4. Identity / Profile facts
        if any(p in t for p in ["я работаю", "я фотограф", "мой город", "моя студия", "моя специализация", "я снимаю"]):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="User profile identity fact",
                memory_type=MemoryType.PROFILE,
                importance=0.90,
                confidence=0.95,
                extracted_fact=text.strip()
            )
            
        # 5. Temporary / Ephemeral desires
        if any(p in t for p in ["сегодня хочу", "сейчас думаю", "в эту минуту", "надо сегодня", "планирую сегодня"]):
            return AdmissionDecision(
                action=AdmissionAction.TEMPORARY,
                reason="Ephemeral intraday desire",
                memory_type=MemoryType.TEMPORARY,
                importance=0.30,
                confidence=0.75,
                extracted_fact=text.strip()
            )
            
        # 6. General durable facts
        return AdmissionDecision(
            action=AdmissionAction.SAVE,
            reason="General factual knowledge statement",
            memory_type=MemoryType.FACT,
            importance=0.50,
            confidence=0.80,
            extracted_fact=text.strip()
        )

    def add_memory(
        self,
        content: str,
        memory_type: Optional[MemoryType] = None,
        importance: Optional[float] = None,
        confidence: Optional[float] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        source: str = "conversation"
    ) -> MemoryItem:
        # Check admission if not pre-classified
        decision = self.evaluate_admission(content)
        if decision.action == AdmissionAction.IGNORE:
            raise ValueError(f"Admission Policy rejected memory: {decision.reason}")
            
        m_type = memory_type or decision.memory_type
        m_imp = importance if importance is not None else decision.importance
        m_conf = confidence if confidence is not None else decision.confidence
        
        expires_at = None
        if decision.action == AdmissionAction.TEMPORARY:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
        now_str = datetime.now(timezone.utc).isoformat()
        mem_id = str(uuid.uuid4())
        
        # Conflict Resolution Check
        self._resolve_conflicts(content, m_type, new_mem_id=mem_id)
        
        item = MemoryItem(
            id=mem_id,
            type=m_type,
            content=content.strip(),
            importance=m_imp,
            confidence=m_conf,
            created_at=now_str,
            updated_at=now_str,
            source=source,
            project_id=project_id,
            client_id=client_id,
            expires_at=expires_at,
            status=MemoryStatus.ACTIVE
        )
        
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO memories (
            id, type, content, importance, confidence, created_at, updated_at,
            source, project_id, client_id, expires_at, status, superseded_by, tags_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.id, item.type.value, item.content, item.importance, item.confidence,
            item.created_at, item.updated_at, item.source, item.project_id,
            item.client_id, item.expires_at, item.status.value, item.superseded_by,
            json.dumps(item.tags)
        ))
        conn.commit()
        conn.close()
        return item

    def _resolve_conflicts(self, new_content: str, m_type: MemoryType, new_mem_id: str):
        """
        Detects opposing/superseding facts and marks older contradicting memories as SUPERSEDED.
        """
        conn = get_connection()
        c = conn.cursor()
        
        # Check active memories of the same type
        c.execute("SELECT id, content FROM memories WHERE type = ? AND status = 'ACTIVE'", (m_type.value,))
        active_items = c.fetchall()
        
        t_new = new_content.lower()
        
        for row in active_items:
            old_id = row["id"]
            old_content = row["content"].lower()
            
            is_conflict = False
            # Check style / brevity conflict
            if ("кратк" in t_new and ("подробн" in old_content or "академич" in old_content)) or \
               (("подробн" in t_new or "академич" in t_new) and "кратк" in old_content):
                is_conflict = True
            elif ("не используй" in t_new and "используй" in old_content and not "не используй" in old_content):
                is_conflict = True
            elif ("теперь" in t_new or "изменилось" in t_new or "больше не" in t_new):
                # Temporal override keywords
                is_conflict = True
                
            if is_conflict:
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("""
                UPDATE memories
                SET status = 'SUPERSEDED', superseded_by = ?, updated_at = ?
                WHERE id = ?
                """, (new_mem_id, now_str, old_id))
                
        conn.commit()
        conn.close()

    def get_memories(
        self,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        memory_type: Optional[MemoryType] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None
    ) -> List[MemoryItem]:
        conn = get_connection()
        c = conn.cursor()
        query = "SELECT * FROM memories WHERE status = ?"
        params = [status.value]
        
        if memory_type:
            query += " AND type = ?"
            params.append(memory_type.value)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)
            
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        
        items = []
        for r in rows:
            items.append(MemoryItem(
                id=r["id"],
                type=MemoryType(r["type"]),
                content=r["content"],
                importance=r["importance"],
                confidence=r["confidence"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                source=r["source"],
                project_id=r["project_id"],
                client_id=r["client_id"],
                expires_at=r["expires_at"],
                status=MemoryStatus(r["status"]),
                superseded_by=r["superseded_by"],
                tags=json.loads(r["tags_json"] or "[]")
            ))
        return items

    def retrieve_relevant_memories(
        self,
        query: str,
        limit: int = 5,
        min_relevance: float = 0.15,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Calculates score: 0.50 * relevance + 0.30 * importance + 0.20 * recency.
        Excludes memories below min_relevance so irrelevant facts do not pollute prompt.
        """
        active_mems = self.get_memories(status=MemoryStatus.ACTIVE, project_id=project_id, client_id=client_id)
        if not active_mems:
            return []
            
        query_words = set(re.findall(r"\w+", query.lower()))
        scored_mems = []
        now = datetime.now(timezone.utc)
        
        DOMAIN_SYNONYMS = {
            "объектив": {"объектив", "оптика", "линза", "стекло", "фокусное", "85mm", "50mm", "35mm", "24-70", "70-200"},
            "оптика": {"объектив", "оптика", "линза", "стекло", "фокусное", "85mm", "50mm", "35mm"},
            "свет": {"свет", "вспышка", "софтбокс", "рефлектор", "октобокс", "студийный"},
            "портрет": {"портрет", "портрета", "портретной", "лицо"},
            "цена": {"цена", "прайс", "пакет", "стоимость", "тариф"}
        }

        for m in active_mems:
            mem_words = set(re.findall(r"\w+", m.content.lower()))
            
            # Semantic lexical relevance
            common = query_words.intersection(mem_words)
            syn_hits = 0
            for qw in query_words:
                if qw in DOMAIN_SYNONYMS and DOMAIN_SYNONYMS[qw].intersection(mem_words):
                    syn_hits += 1

            if not mem_words:
                relevance = 0.0
            else:
                base_len = len(common) + (syn_hits * 2)
                relevance = base_len / min(max(len(query_words), 1), 10)
                # Boost if exact phrase or high domain relevance
                if re.search(r"\b(стиль|ответ|правило|клиент|цена|прайс)\b", query.lower()):
                    if m.type in [MemoryType.PREFERENCE, MemoryType.STYLE]:
                        relevance = max(relevance, 0.40)
                        
            # If query is completely unrelated, keep relevance low
            if len(common) == 0 and syn_hits == 0 and m.type not in [MemoryType.PREFERENCE]:
                relevance = 0.05
                
            # Filter strictly irrelevant memories
            if relevance < min_relevance and m.type != MemoryType.PREFERENCE:
                continue
                
            # Recency decay (half-life of 30 days)
            try:
                m_dt = datetime.fromisoformat(m.created_at)
                age_days = (now - m_dt).total_seconds() / 86400.0
                recency = max(0.0, 1.0 - (age_days / 30.0))
            except:
                recency = 1.0
                
            score = 0.50 * relevance + 0.30 * m.importance + 0.20 * recency
            scored_mems.append((m, score))
            
        scored_mems.sort(key=lambda x: x[1], reverse=True)
        return scored_mems[:limit]

    def update_memory(self, memory_id: str, new_content: str, importance: Optional[float] = None) -> MemoryItem:
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        if importance is not None:
            c.execute("UPDATE memories SET content = ?, importance = ?, updated_at = ? WHERE id = ?",
                      (new_content.strip(), importance, now_str, memory_id))
        else:
            c.execute("UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
                      (new_content.strip(), now_str, memory_id))
        conn.commit()
        
        c.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            raise ValueError(f"Memory {memory_id} not found")
        return MemoryItem(
            id=r["id"],
            type=MemoryType(r["type"]),
            content=r["content"],
            importance=r["importance"],
            confidence=r["confidence"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            source=r["source"],
            project_id=r["project_id"],
            client_id=r["client_id"],
            expires_at=r["expires_at"],
            status=MemoryStatus(r["status"]),
            superseded_by=r["superseded_by"],
            tags=json.loads(r["tags_json"] or "[]")
        )

    def delete_memory(self, memory_id: str):
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        conn.close()

    def purge_all(self):
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM memories")
        conn.commit()
        conn.close()
