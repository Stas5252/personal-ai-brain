"""
Style Engine with Exemplars Vault and Style Benchmark Evaluation.
"""
import uuid
import json
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from src.brain.db import get_connection
from src.brain.models.style import (
    StyleProfile, StyleExemplar, ExemplarType, ExemplarCategory, StyleBenchmarkResult
)

class StyleEngine:
    def __init__(self):
        pass

    def add_exemplar(
        self,
        title: str,
        content: str,
        exemplar_type: ExemplarType = ExemplarType.GOOD_EXAMPLE,
        category: ExemplarCategory = ExemplarCategory.POST,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> StyleExemplar:
        ex_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        
        exemplar = StyleExemplar(
            id=ex_id,
            title=title,
            content=content.strip(),
            exemplar_type=exemplar_type,
            category=category,
            tags=tags or [],
            notes=notes,
            created_at=now_str
        )
        
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO style_exemplars (
            id, title, content, exemplar_type, category, tags_json, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exemplar.id, exemplar.title, exemplar.content,
            exemplar.exemplar_type.value, exemplar.category.value,
            json.dumps(exemplar.tags), exemplar.notes, exemplar.created_at
        ))
        conn.commit()
        conn.close()
        return exemplar

    def get_exemplars(
        self,
        category: Optional[ExemplarCategory] = None,
        exemplar_type: Optional[ExemplarType] = None,
        limit: int = 5
    ) -> List[StyleExemplar]:
        conn = get_connection()
        c = conn.cursor()
        sql = "SELECT * FROM style_exemplars WHERE 1=1"
        params = []
        if category:
            sql += " AND category = ?"
            params.append(category.value)
        if exemplar_type:
            sql += " AND exemplar_type = ?"
            params.append(exemplar_type.value)
            
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        
        items = []
        for r in rows:
            items.append(StyleExemplar(
                id=r["id"],
                title=r["title"],
                content=r["content"],
                exemplar_type=ExemplarType(r["exemplar_type"]),
                category=ExemplarCategory(r["category"]),
                tags=json.loads(r["tags_json"] or "[]"),
                notes=r["notes"],
                created_at=r["created_at"]
            ))
        return items

    def build_style_instructions(self, profile: StyleProfile, category: Optional[ExemplarCategory] = None) -> str:
        """
        Assembles prompt-injectable style directives and relevant exemplars.
        """
        good_examples = self.get_exemplars(category=category, exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=2)
        
        lines = [
            "### СТИЛЬ И ТОНАЛЬНОСТЬ АВТОРА:",
            f"- Тон: {profile.tone}",
            f"- Юмор: {profile.humor}",
            f"- Структура текста: {profile.paragraph_structure}",
            f"- Длина предложений: средняя ~{int(profile.sentence_length_avg)} слов, ритмичный слог.",
            f"- Эмодзи: {profile.emoji_frequency}.",
            f"- Пунктуация: {profile.punctuation_habits}."
        ]
        
        if profile.forbidden_expressions:
            lines.append(f"- ЗАПРЕЩЕННЫЕ СЛОВА И КЛИШЕ: {', '.join(profile.forbidden_expressions)}")
            
        if profile.preferred_expressions:
            lines.append(f"- Характерные авторские фразы: {', '.join(profile.preferred_expressions)}")
            
        if good_examples:
            lines.append("\n### ЭТАЛОННЫЕ ПРИМЕРЫ АВТОРСКОГО ТЕКСТА (GOOD EXAMPLES):")
            for idx, ex in enumerate(good_examples):
                lines.append(f"--- Пример {idx+1} ({ex.title}) ---\n{ex.content}\n")
                
        return "\n".join(lines)

    def evaluate_benchmark(self, text: str, profile: StyleProfile, forbidden_words: Optional[List[str]] = None) -> StyleBenchmarkResult:
        """
        Calculates measurable benchmark across 5 style metrics:
        1. vocabulary_similarity (overlap with good examples / vocabulary)
        2. sentence_rhythm_score (proximity to target avg sentence length)
        3. emoji_density_score (ratio of emojis)
        4. cta_presence_score (presence of Call to Action)
        5. forbidden_violations (count of forbidden words)
        """
        # 1. Sentence rhythm
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 3]
        if sentences:
            words_per_sent = [len(re.findall(r"\w+", s)) for s in sentences]
            avg_len = sum(words_per_sent) / len(words_per_sent)
            # Deviation from target (target = profile.sentence_length_avg)
            dev = abs(avg_len - profile.sentence_length_avg)
            rhythm_score = max(0.0, min(1.0, 1.0 - (dev / 15.0)))
        else:
            rhythm_score = 0.5
            
        # 2. Vocabulary similarity with stored good exemplars
        good_ex = self.get_exemplars(exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=5)
        good_words = set()
        for ex in good_ex:
            good_words.update(re.findall(r"\w+", ex.content.lower()))
        if profile.vocabulary:
            good_words.update([w.lower() for w in profile.vocabulary])
            
        text_words = set(re.findall(r"\w+", text.lower()))
        if good_words and text_words:
            overlap = text_words.intersection(good_words)
            vocab_sim = min(1.0, len(overlap) / (len(text_words) * 0.40))
        else:
            vocab_sim = 0.75
            
        # 3. Emoji density
        emojis = re.findall(r"[\U00010000-\U0010ffff]", text)
        emoji_count = len(emojis)
        # Optimal: 1-4 emojis for typical post
        if 1 <= emoji_count <= 5:
            emoji_score = 1.0
        elif emoji_count == 0:
            emoji_score = 0.8
        else:
            emoji_score = max(0.2, 1.0 - (emoji_count - 5) * 0.15)
            
        # 4. CTA presence
        cta_keywords = ["напиши", "директ", "запись", "ссылк", "бронь", "мест", "вопрос", "комментари", "сохраняй"]
        has_cta = any(k in text.lower() for k in cta_keywords)
        cta_score = 1.0 if has_cta else 0.5
        
        # 5. Forbidden words violations
        all_forbidden = list(profile.forbidden_expressions)
        if forbidden_words:
            all_forbidden.extend(forbidden_words)
            
        violations = 0
        for f in all_forbidden:
            if f.lower() in text.lower():
                violations += 1
                
        # Overall Score
        overall = 0.30 * vocab_sim + 0.25 * rhythm_score + 0.20 * emoji_score + 0.25 * cta_score
        if violations > 0:
            overall = max(0.0, overall - (violations * 0.40))
            
        notes = f"Avg sent len: {round(avg_len if sentences else 0, 1)} words; Emojis: {emoji_count}; CTA: {'YES' if has_cta else 'NO'}; Violations: {violations}"
        
        return StyleBenchmarkResult(
            vocabulary_similarity=round(vocab_sim, 2),
            sentence_rhythm_score=round(rhythm_score, 2),
            emoji_density_score=round(emoji_score, 2),
            cta_presence_score=round(cta_score, 2),
            forbidden_violations=violations,
            overall_score=round(overall, 2),
            notes=notes
        )
