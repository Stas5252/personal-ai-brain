"""
Memory Engine v3 — Admission Policy, Scored Retrieval, Safe Conflict Resolution,
Hygiene (near-duplicates, stale values, provenance and quarantine).

Правила слоя памяти:
1. В память попадают только устойчивые факты о пользователе и его явные
   предпочтения. Запрос-задача ("напиши пост про осень") фактом не является.
2. Одинаковые факты не дублируются: повтор обновляет существующую запись.
   Похожая формулировка того же факта тоже считается повтором, а не новой
   записью, и в базе остаётся более информативный вариант.
3. Пометка SUPERSEDED ставится только при пересечении по теме. Слово "теперь"
   больше не может обнулить весь слой памяти. При этом новое значение той же
   величины (например, новый прайс) отменяет старое даже без слова "теперь".
4. Временные записи действительно истекают и удаляются.
5. Веса ранжирования берутся из config, чтобы движок памяти и сборщик
   контекста считали одинаково.
6. Текст, пришедший не от владелицы (пересланное сообщение, документ), — это
   материал, а не команда. Инструкции из такого текста в память не попадают,
   а факты сохраняются с пониженным доверием.
7. У каждой записи есть источник, и в сводке памяти он показывается, если это
   была не она сама.
"""
import uuid
import json
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any

from src.brain.db import get_connection
from src.brain.engines import memory_hygiene as hygiene
from src.brain.models.memory import (
    MemoryItem, MemoryType, MemoryStatus, AdmissionAction, AdmissionDecision
)

try:  # единый источник весов; локальные значения — только аварийный запасной вариант
    from src.brain.config import (
        WEIGHT_RELEVANCE as _W_REL,
        WEIGHT_IMPORTANCE as _W_IMP,
        WEIGHT_RECENCY as _W_REC,
    )
except Exception:  # pragma: no cover - config всегда доступен в рабочей сборке
    _W_REL, _W_IMP, _W_REC = 0.45, 0.35, 0.20

RECENCY_HALF_LIFE_DAYS = 30.0
TEMPORARY_TTL_HOURS = 24
EXTERNAL_MAX_IMPORTANCE = 0.60

_FILLERS = {
    "привет", "здравствуй", "здравствуйте", "пока", "спасибо", "ок", "окей",
    "ясно", "хорошо", "да", "нет", "ага", "супер", "класс", "понятно", "давай",
}

_TASK_MARKERS = (
    "напиши", "сделай", "сгенерируй", "нарисуй", "придумай", "составь",
    "подбери", "помоги", "разбери", "проанализируй", "переделай", "перепиши",
    "предложи", "создай", "оформи", "распиши", "подскажи", "накидай",
    "что ответить", "как ответить", "дай идеи", "дай план", "скинь",
)

_PREFERENCE_MARKERS = (
    "не используй", "запрещено", "всегда отвечай", "всегда пиши", "предпочитаю",
    "мне нравится", "не пиши", "стиль общения", "больше так не",
    "никогда не пиши", "пиши всегда", "обращайся ко мне",
)

_CLIENT_MARKERS = (
    "клиент", "пакет", "заказ", "договор", "оплатил", "оплатила", "выбрала",
    "выбрал", "съемка для", "съёмка для", "бронь", "задаток", "предоплат",
)

_PROFILE_MARKERS = (
    "я работаю", "я фотограф", "мой город", "моя студия", "моя специализация",
    "я снимаю", "меня зовут", "моя ниша", "я живу", "мой профиль", "мой блог",
)

_TEMPORARY_MARKERS = (
    "сегодня хочу", "сейчас думаю", "в эту минуту", "надо сегодня",
    "планирую сегодня", "на этой неделе хочу", "завтра надо",
)

_SELF_MARKERS = (
    "я ", "мой ", "моя ", "мои ", "моё ", "мое ", "меня", "мне ",
    "у нас", "наш ", "наша ", "наши ",
)

_OVERRIDE_MARKERS = (
    "теперь", "больше не", "изменилось", "с этого момента", "отныне",
    "поменял", "поменяла", "сменил", "сменила", "перешла", "перешел", "перешёл",
)

_STOPWORDS = {
    "и", "в", "во", "не", "на", "с", "со", "что", "как", "для", "это", "по",
    "то", "же", "бы", "ли", "или", "из", "за", "от", "до", "у", "о", "об",
    "а", "но", "да", "так", "еще", "ещё", "уже", "есть", "быть", "был",
    "была", "чтобы", "если", "когда", "где", "кто", "вот", "там", "тут",
    "они", "она", "он", "мы", "вы", "ты", "я", "мне", "мой", "моя", "меня",
    "очень", "просто", "надо", "нужно", "можно", "буду", "была", "этот", "эта",
}

DOMAIN_SYNONYMS: Dict[str, set] = {
    "объектив": {"объектив", "оптика", "линза", "стекло", "фокусное", "85mm", "50mm", "35mm", "24-70", "70-200"},
    "оптика": {"объектив", "оптика", "линза", "стекло", "фокусное", "85mm", "50mm", "35mm"},
    "свет": {"свет", "вспышка", "софтбокс", "рефлектор", "октобокс", "студийный"},
    "портрет": {"портрет", "портрета", "портретной", "лицо"},
    "цена": {"цена", "прайс", "пакет", "стоимость", "тариф"},
    "прайс": {"цена", "прайс", "пакет", "стоимость", "тариф"},
    "клиент": {"клиент", "клиентка", "заказчик", "невеста", "пара"},
}


def _normalize(text: str) -> str:
    """Приводит фразу к виду, по которому сравниваются дубликаты."""
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _significant_words(text: str) -> set:
    return {
        w for w in re.findall(r"\w+", (text or "").lower())
        if len(w) > 3 and w not in _STOPWORDS
    }


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Разбирает ISO-время и всегда возвращает aware-datetime в UTC."""
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def recency_score(created_at: Optional[str], updated_at: Optional[str] = None) -> float:
    """Настоящий период полураспада: 30 дней — 0.5, 60 дней — 0.25."""
    dt = _parse_dt(updated_at) or _parse_dt(created_at)
    if dt is None:
        return 0.5
    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    return max(0.0, min(1.0, 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)))


class MemoryEngine:
    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # Admission
    # ------------------------------------------------------------------
    def evaluate_admission(self, text: str) -> AdmissionDecision:
        """
        Решает, что делать с фразой: сохранить, сохранить временно или пропустить.

        Ключевое отличие от v1: по умолчанию фраза НЕ сохраняется. Раньше любое
        сообщение длиннее 8 символов падало в память как FACT 0.50, из-за чего
        база забивалась командами вида "напиши пост про осень".
        """
        raw = (text or "").strip()
        t = raw.lower()

        if len(t) < 8 or t.strip("!?.,") in _FILLERS:
            return AdmissionDecision(action=AdmissionAction.IGNORE, reason="Conversational filler")

        if any(p in t for p in _PREFERENCE_MARKERS):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="User preference rule detected",
                memory_type=MemoryType.PREFERENCE,
                importance=0.95,
                confidence=0.95,
                extracted_fact=raw,
            )

        if any(t.startswith(m) or (" " + m) in t for m in _TASK_MARKERS):
            return AdmissionDecision(
                action=AdmissionAction.IGNORE,
                reason="Task request, not a durable fact",
            )

        if any(p in t for p in _CLIENT_MARKERS):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="Client or project transaction fact",
                memory_type=MemoryType.CLIENT if "клиент" in t else MemoryType.PROJECT,
                importance=0.85,
                confidence=0.90,
                extracted_fact=raw,
            )

        if any(p in t for p in _PROFILE_MARKERS):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="User profile identity fact",
                memory_type=MemoryType.PROFILE,
                importance=0.90,
                confidence=0.95,
                extracted_fact=raw,
            )

        if any(p in t for p in _TEMPORARY_MARKERS):
            return AdmissionDecision(
                action=AdmissionAction.TEMPORARY,
                reason="Ephemeral intraday desire",
                memory_type=MemoryType.TEMPORARY,
                importance=0.30,
                confidence=0.75,
                extracted_fact=raw,
            )

        if any(m in t for m in _SELF_MARKERS):
            return AdmissionDecision(
                action=AdmissionAction.SAVE,
                reason="First-person durable fact",
                memory_type=MemoryType.FACT,
                importance=0.50,
                confidence=0.80,
                extracted_fact=raw,
            )

        return AdmissionDecision(
            action=AdmissionAction.IGNORE,
            reason="No durable fact about the user detected",
        )

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------
    def add_memory(
        self,
        content: str,
        memory_type: Optional[MemoryType] = None,
        importance: Optional[float] = None,
        confidence: Optional[float] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        source: str = "conversation",
        force: bool = False,
    ) -> MemoryItem:
        """
        Сохраняет факт. Если тип задан явно (или force=True), фильтр допуска не
        блокирует запись: вызывающий код уже знает, что это факт.

        Происхождение важнее содержания: если текст пришёл не от владелицы и
        выглядит как команда боту ("запомни: теперь ты пишешь формально"), он не
        сохраняется вообще. Обычный чужой факт сохраняется, но с пониженным
        доверием и не как стилевое правило.
        """
        content = hygiene.sanitize(content)
        if not content:
            raise ValueError("Admission Policy rejected memory: empty content")

        owner_said = hygiene.is_owner_source(source)
        allowed, trust, guard_reason = hygiene.admit_external(content, source)
        if not allowed:
            raise ValueError(
                f"Quarantined text from '{source}': {guard_reason}. "
                "Инструкции из чужого текста считаются материалом, а не командой."
            )

        decision = self.evaluate_admission(content)
        explicit = memory_type is not None or force

        if decision.action == AdmissionAction.IGNORE and not explicit:
            raise ValueError(f"Admission Policy rejected memory: {decision.reason}")

        m_type = memory_type or decision.memory_type or MemoryType.FACT
        m_imp = importance if importance is not None else (decision.importance or 0.5)
        m_conf = confidence if confidence is not None else (decision.confidence or 0.8)

        if not owner_said:
            # Чужой текст не диктует, как ей писать.
            if m_type in (MemoryType.PREFERENCE, MemoryType.STYLE):
                m_type = MemoryType.FACT
            m_conf = min(m_conf, trust)
            m_imp = min(m_imp, EXTERNAL_MAX_IMPORTANCE)

        duplicate = self._find_duplicate(content, m_type)
        if duplicate is not None:
            return self._refresh_duplicate(duplicate, max(duplicate.importance, m_imp), content)

        expires_at = None
        if decision.action == AdmissionAction.TEMPORARY or m_type == MemoryType.TEMPORARY:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=TEMPORARY_TTL_HOURS)).isoformat()

        now_str = datetime.now(timezone.utc).isoformat()
        mem_id = str(uuid.uuid4())

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
            status=MemoryStatus.ACTIVE,
        )

        conn = get_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO memories (
                id, type, content, importance, confidence, created_at, updated_at,
                source, project_id, client_id, expires_at, status, superseded_by, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id, item.type.value, item.content, item.importance, item.confidence,
                item.created_at, item.updated_at, item.source, item.project_id,
                item.client_id, item.expires_at, item.status.value, item.superseded_by,
                json.dumps(item.tags),
            ),
        )
        conn.commit()
        conn.close()
        return item

    def _find_duplicate(self, content: str, m_type: MemoryType) -> Optional[MemoryItem]:
        """
        Ищет активную запись того же типа с тем же смыслом.

        Раньше сравнение было посимвольным, поэтому "Я снимаю свадьбы в Саратове"
        и "Снимаю свадьбы в Саратове" становились двумя фактами, и в сводке
        памяти одно и то же повторялось дважды.
        """
        target = _normalize(content)
        if not target:
            return None
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM memories WHERE type = ? AND status = 'ACTIVE'", (m_type.value,))
        rows = c.fetchall()
        conn.close()

        best_row = None
        best_score = 0.0
        for r in rows:
            candidate = r["content"] or ""
            if _normalize(candidate) == target:
                return self._row_to_item(r)
            score = hygiene.similarity(content, candidate)
            if score > best_score:
                best_score, best_row = score, r

        if best_row is not None and best_score >= hygiene.NEAR_DUPLICATE_THRESHOLD:
            return self._row_to_item(best_row)
        return None

    def _refresh_duplicate(
        self,
        item: MemoryItem,
        importance: float,
        new_content: Optional[str] = None,
    ) -> MemoryItem:
        """Обновляет повтор. Если новая формулировка подробнее — она и остаётся."""
        now_str = datetime.now(timezone.utc).isoformat()
        content = item.content
        if new_content and len(new_content.strip()) > len(item.content or ""):
            content = new_content.strip()

        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE memories SET content = ?, importance = ?, updated_at = ? WHERE id = ?",
            (content, importance, now_str, item.id),
        )
        conn.commit()
        conn.close()
        item.content = content
        item.importance = importance
        item.updated_at = now_str
        return item

    def _resolve_conflicts(self, new_content: str, m_type: MemoryType, new_mem_id: str):
        """
        Помечает устаревшие записи как SUPERSEDED — но только те, что пересекаются
        с новой по теме.

        В v1 любое слово "теперь" помечало устаревшими ВСЕ активные записи этого
        типа, то есть одно сообщение стирало всю память. Теперь требуется общая
        тема: минимум два значимых общих слова.

        Дополнительно работает проверка значения: новый прайс на ту же услугу,
        другой город или отказ от жанра отменяют прежнюю запись даже без слов
        "теперь" и "больше не". Разные услуги с разными ценами при этом остаются
        обе — предмет должен совпадать.
        """
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, content FROM memories WHERE type = ? AND status = 'ACTIVE'", (m_type.value,))
        active_items = c.fetchall()

        t_new = (new_content or "").lower()
        new_words = _significant_words(new_content)
        has_override = any(k in t_new for k in _OVERRIDE_MARKERS)
        superseded = 0

        for row in active_items:
            old_id = row["id"]
            old_raw = row["content"] or ""
            old_content = old_raw.lower()
            old_words = _significant_words(old_content)
            overlap = len(new_words & old_words)

            is_conflict = False

            # 1. Прямой стилевой конфликт: коротко против подробно.
            if m_type in (MemoryType.PREFERENCE, MemoryType.STYLE):
                if ("кратк" in t_new and ("подробн" in old_content or "академич" in old_content)) or \
                   (("подробн" in t_new or "академич" in t_new) and "кратк" in old_content):
                    is_conflict = True

            # 2. Запрет отменяет прежнее разрешение по той же теме.
            if not is_conflict and "не используй" in t_new and "используй" in old_content \
                    and "не используй" not in old_content and overlap >= 1:
                is_conflict = True

            # 3. Явная замена факта: "теперь", "больше не", "сменила" — только по своей теме.
            if not is_conflict and has_override and overlap >= 2:
                is_conflict = True

            # 4. Изменившееся значение той же величины: цена, город, камера, аккаунт.
            if not is_conflict and hygiene.detect_value_conflict(new_content, old_raw):
                is_conflict = True

            if is_conflict:
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute(
                    "UPDATE memories SET status = 'SUPERSEDED', superseded_by = ?, updated_at = ? WHERE id = ?",
                    (new_mem_id, now_str, old_id),
                )
                superseded += 1

        conn.commit()
        conn.close()
        return superseded

    def consolidate(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Ночная уборка: сворачивает накопившиеся повторы одного факта в одну запись.

        Записи не удаляются, а помечаются SUPERSEDED со ссылкой на оставшуюся,
        поэтому историю всегда можно поднять. Возвращает число свёрнутых строк.
        """
        types = [memory_type] if memory_type is not None else list(MemoryType)
        merged = 0

        for t in types:
            items = self.get_memories(status=MemoryStatus.ACTIVE, memory_type=t)
            if len(items) < 2:
                continue
            payload = [
                {
                    "id": i.id,
                    "content": i.content,
                    "importance": i.importance,
                    "updated_at": i.updated_at or i.created_at or "",
                }
                for i in items
            ]
            groups = hygiene.consolidation_groups(payload)
            if not groups:
                continue

            now_str = datetime.now(timezone.utc).isoformat()
            conn = get_connection()
            c = conn.cursor()
            for group in groups:
                keeper = group.get("keeper")
                duplicates = [d for d in (group.get("duplicates") or []) if d and d != keeper]
                if not keeper or not duplicates:
                    continue
                for dup_id in duplicates:
                    c.execute(
                        "UPDATE memories SET status = 'SUPERSEDED', superseded_by = ?, updated_at = ? WHERE id = ?",
                        (keeper, now_str, dup_id),
                    )
                    merged += 1
            conn.commit()
            conn.close()

        return merged

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------
    def _row_to_item(self, r) -> MemoryItem:
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
            tags=json.loads(r["tags_json"] or "[]"),
        )

    def get_memories(
        self,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        memory_type: Optional[MemoryType] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[MemoryItem]:
        conn = get_connection()
        c = conn.cursor()
        query = "SELECT * FROM memories WHERE status = ?"
        params: List[Any] = [status.value]

        if memory_type:
            query += " AND type = ?"
            params.append(memory_type.value)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)
        if not include_expired:
            query += " AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?)"
            params.append(datetime.now(timezone.utc).isoformat())

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return [self._row_to_item(r) for r in rows]

    def purge_expired(self) -> int:
        """Физически удаляет временные записи, у которых вышел срок."""
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at != '' AND expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        removed = c.rowcount or 0
        conn.commit()
        conn.close()
        return removed

    def _relevance(self, query_words: set, m: MemoryItem, query_lower: str) -> float:
        mem_words = set(re.findall(r"\w+", m.content.lower()))
        if not mem_words or not query_words:
            return 0.0

        common = query_words & mem_words
        syn_hits = 0
        for qw in query_words:
            if qw in DOMAIN_SYNONYMS and DOMAIN_SYNONYMS[qw] & mem_words:
                syn_hits += 1

        base_len = len(common) + (syn_hits * 2)
        relevance = base_len / min(max(len(query_words), 1), 10)

        if re.search(r"\b(стиль|ответ|правило|клиент|цена|прайс)\b", query_lower):
            if m.type in (MemoryType.PREFERENCE, MemoryType.STYLE):
                relevance = max(relevance, 0.40)

        if not common and not syn_hits and m.type != MemoryType.PREFERENCE:
            relevance = 0.05

        return min(1.0, relevance)

    def retrieve_relevant_memories(
        self,
        query: str,
        limit: int = 5,
        min_relevance: float = 0.15,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Скор: WEIGHT_RELEVANCE * relevance + WEIGHT_IMPORTANCE * importance +
        WEIGHT_RECENCY * recency — те же веса, что и в сборщике контекста.

        Правила стиля (PREFERENCE) не выбрасываются по релевантности и всегда
        занимают до двух мест в выдаче: без них бот перестаёт писать "как я".
        """
        self.purge_expired()
        active_mems = self.get_memories(status=MemoryStatus.ACTIVE, project_id=project_id, client_id=client_id)
        if not active_mems:
            return []

        query_lower = (query or "").lower()
        query_words = {w for w in re.findall(r"\w+", query_lower) if w not in _STOPWORDS}
        scored: List[Tuple[MemoryItem, float]] = []

        for m in active_mems:
            relevance = self._relevance(query_words, m, query_lower)
            if relevance < min_relevance and m.type != MemoryType.PREFERENCE:
                continue
            score = (
                _W_REL * relevance
                + _W_IMP * float(m.importance or 0.0)
                + _W_REC * recency_score(m.created_at, m.updated_at)
            )
            scored.append((m, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:limit]

        # Гарантированное место для стилевых правил.
        prefs = [p for p in scored if p[0].type == MemoryType.PREFERENCE][:2]
        for pref in prefs:
            if any(existing[0].id == pref[0].id for existing in top):
                continue
            replaced = False
            for idx in range(len(top) - 1, -1, -1):
                if top[idx][0].type != MemoryType.PREFERENCE:
                    top[idx] = pref
                    replaced = True
                    break
            if not replaced and len(top) < limit:
                top.append(pref)

        top.sort(key=lambda x: x[1], reverse=True)
        return top

    def digest(self, limit: int = 20) -> List[str]:
        """
        Человекочитаемый список того, что бот реально помнит.

        Если факт пришёл не от неё (пересланное сообщение, документ), источник
        подписывается: так видно, откуда бот это взял, и легко поправить.
        """
        items = self.get_memories(status=MemoryStatus.ACTIVE)
        items.sort(key=lambda m: (float(m.importance or 0.0), m.updated_at or ""), reverse=True)
        lines = []
        for m in items[:limit]:
            line = f"[{m.type.value}] {m.content}"
            if not hygiene.is_owner_source(m.source):
                line += f" ({hygiene.source_label(m.source)})"
            lines.append(line)
        return lines

    def stats(self) -> Dict[str, Any]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT status, COUNT(*) AS n FROM memories GROUP BY status")
        by_status = {r["status"]: r["n"] for r in c.fetchall()}
        c.execute("SELECT type, COUNT(*) AS n FROM memories WHERE status = 'ACTIVE' GROUP BY type")
        by_type = {r["type"]: r["n"] for r in c.fetchall()}
        c.execute("SELECT source, COUNT(*) AS n FROM memories WHERE status = 'ACTIVE' GROUP BY source")
        by_source = {(r["source"] or "unknown"): r["n"] for r in c.fetchall()}
        conn.close()
        return {"by_status": by_status, "active_by_type": by_type, "active_by_source": by_source}

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def update_memory(self, memory_id: str, new_content: str, importance: Optional[float] = None) -> MemoryItem:
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        if importance is not None:
            c.execute(
                "UPDATE memories SET content = ?, importance = ?, updated_at = ? WHERE id = ?",
                (new_content.strip(), importance, now_str, memory_id),
            )
        else:
            c.execute(
                "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
                (new_content.strip(), now_str, memory_id),
            )
        conn.commit()

        c.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            raise ValueError(f"Memory {memory_id} not found")
        return self._row_to_item(r)

    def delete_memory(self, memory_id: str):
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        conn.close()

    def forget_matching(self, phrase: str) -> int:
        """Удаляет записи, содержащие фразу. Нужно для команды "забудь про ..."."""
        needle = _normalize(phrase)
        if not needle:
            return 0
        removed = 0
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, content FROM memories")
        rows = c.fetchall()
        for r in rows:
            if needle in _normalize(r["content"]):
                c.execute("DELETE FROM memories WHERE id = ?", (r["id"],))
                removed += 1
        conn.commit()
        conn.close()
        return removed

    def purge_all(self):
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM memories")
        conn.commit()
        conn.close()
