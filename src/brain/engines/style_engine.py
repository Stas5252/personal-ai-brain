"""
Style Engine: хранилище авторских образцов, замер голоса автора и бенчмарк.

Именно этот модуль отвечает за то, чтобы ассистент писал как владелица, а не
как обобщённая модель. Каждый текст, который она пометила как «вот так пиши»,
сохраняется в хранилище, измеряется (длина предложений, плотность эмодзи,
характерные слова, пунктуация, доля призывов) — и эти замеры подставляются в
каждый промпт и становятся целью бенчмарка.

Два правила, которые здесь не нарушаются:
  * ничего не выдумывается — при пустом хранилище движок честно сообщает, что
    образцов нет, вместо описания несуществующего авторского голоса;
  * замеры делаются только по её собственным текстам, а не по ответам
    ассистента, если она их явно не одобрила.

Кроме замеров здесь живёт обратная связь: когда она бракует ответ, из её
фразы и из забракованного текста выводятся настоящие стоп-слова. Без этого
кольцо обучения было разомкнуто — антипример сохранялся, но список, который
читают промпт и бенчмарк, не менялся.
"""
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.brain.db import get_connection
from src.brain.models.style import (
    ExemplarCategory,
    ExemplarType,
    StyleBenchmarkResult,
    StyleExemplar,
    StyleProfile,
)

# Голос считается выученным только начиная с этого количества её текстов.
MIN_EXEMPLARS_FOR_VOICE = 3
# Тег, которым помечается описание визуального стиля (для генерации фото).
VISUAL_TAG = "visual_style"
# Короче этого текст не образец стиля, а реплика.
MIN_LEARNABLE_CHARS = 40
# Карточка личности переинжектится в каждый промпт, поэтому она короткая.
MAX_CARD_CHARS = 700

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_SENTENCE_RE = re.compile(r"[.!?]+|\n+")
# Тот же разбор, но со знаком в конце: без него не понять, вопросом ли она
# открывает текст.
_SENTENCE_KEEP_RE = re.compile(r"[^.!?\n]+[.!?]*")
_EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]")

_CTA_KEYWORDS = (
    "напиши",
    "директ",
    "запись",
    "ссылк",
    "бронь",
    "мест",
    "вопрос",
    "комментари",
    "сохраняй",
)

_CATEGORY_MARKERS = [
    (ExemplarCategory.REELS_SCRIPT, ("рилс", "reels", "рилз", "хук", "склейк", "сцена", "кадр 1")),
    (ExemplarCategory.STORIES, ("сторис", "stories", "сторю", "свайп", "опрос", "стикер")),
    (ExemplarCategory.OFFER, ("прайс", "тариф", "пакет", "стоимость", "оффер", "предоплат", "₽")),
    (ExemplarCategory.CLIENT_DM, ("здравствуйте", "добрый день", "добрый вечер", "запишу вас", "свободн")),
    (ExemplarCategory.DESCRIPTION, ("шапка профиля", "описание профиля", " био", "bio")),
]

# Третий слой голоса: не «какие слова», а «как объясняет». Ритм и лексику мы
# уже мерили, а способ объяснения — нет, и именно он выдаёт чужой текст.
_EXPLANATION_MARKERS = [
    ("на примере", ("например", "к примеру", "смотри", "покажу", "как у ", "вот так же")),
    ("через цифры", ("рубл", "₽", "%", " минут", " часа", " часов", " кадр", " раз")),
    ("через чувство", ("чувств", "ощущен", "эмоц", "мурашк", "тепл", "любл", "нежн")),
    ("через шаги", ("шаг ", "во-первых", "сначала", "потом", "дальше", "итог")),
]

# Фразы, после которых она прямо называет запрещённое слово.
_BAN_MARKERS = (
    "убери",
    "уберите",
    "без слова",
    "без слов",
    "не пиши слово",
    "не используй",
    "не употребляй",
    "не говори",
    "бесит слово",
    "ненавижу слово",
    "терпеть не могу",
)
_BAN_QUOTE_RE = re.compile(r"[«\"'`]([^«»\"'`]{2,40})[»\"'`]")
_MAX_BANS_PER_MESSAGE = 5

_STOPWORDS = {
    "а", "без", "более", "больше", "будет", "будто", "бы", "был", "была", "были", "было", "быть",
    "вам", "вас", "ведь", "весь", "вдруг", "вот", "впрочем", "все", "всегда", "всего", "всех",
    "всю", "вы", "где", "да", "даже", "два", "для", "до", "другой", "его", "ее", "её", "ей",
    "ему", "если", "есть", "еще", "ещё", "же", "за", "зачем", "здесь", "и", "из", "или", "им",
    "иногда", "их", "как", "какая", "какой", "когда", "конечно", "которые", "которых", "кто",
    "куда", "ли", "лучше", "между", "меня", "мне", "много", "может", "можно", "мой", "моя", "мы",
    "на", "над", "надо", "наконец", "нас", "не", "него", "нее", "неё", "ней", "нельзя", "нет",
    "ни", "нибудь", "никогда", "ним", "них", "ничего", "но", "ну", "об", "один", "он", "она",
    "они", "опять", "от", "очень", "перед", "по", "под", "после", "потом", "потому", "почти",
    "при", "про", "раз", "разве", "с", "сам", "свою", "себе", "себя", "сейчас", "со", "совсем",
    "так", "такой", "там", "тебя", "тем", "теперь", "то", "тогда", "того", "тоже", "только",
    "том", "тот", "три", "тут", "ты", "у", "уж", "уже", "хорошо", "хоть", "чего", "чем", "через",
    "что", "чтоб", "чтобы", "чуть", "эта", "эти", "это", "этого", "этой", "этом", "этот", "эту",
    "я",
}


def _sentences(text: str) -> List[str]:
    """Разбивает текст на предложения, сохраняя знак в конце."""
    return [s.strip() for s in _SENTENCE_KEEP_RE.findall(text or "") if s.strip()]


def classify_opening(sentence: str) -> str:
    """Чем она открывает текст: вопросом, цифрой, короткой фразой, утверждением."""
    body = (sentence or "").strip()
    if not body:
        return ""
    words = _WORD_RE.findall(body)
    if body.endswith("?"):
        return "вопросом"
    if words and words[0].isdigit():
        return "цифрой"
    if len(words) <= 4:
        return "короткой фразой"
    return "утверждением"


def classify_closing(sentence: str) -> str:
    """Чем она закрывает текст: вопросом, призывом, короткой точкой, мыслью."""
    body = (sentence or "").strip()
    if not body:
        return ""
    lowered = body.lower()
    words = _WORD_RE.findall(body)
    if body.endswith("?"):
        return "вопросом"
    if any(marker in lowered for marker in _CTA_KEYWORDS):
        return "призывом"
    if len(words) <= 4:
        return "короткой точкой"
    return "развёрнутой мыслью"


def extract_explicit_bans(phrase: str) -> List[str]:
    """Достаёт слова, которые она сама назвала запрещёнными.

    «так не пиши» — это вердикт без содержания, из него ничего не выводится.
    А «убери "дорогие мои"» — прямое указание, и оно не должно угадываться:
    берём ровно то, что она написала в кавычках или после «убери».
    """
    body = (phrase or "").strip()
    if not body:
        return []
    lowered = body.lower()
    found: List[str] = []

    for match in _BAN_QUOTE_RE.findall(body):
        candidate = match.strip(" .,;:!?-–—").lower()
        if len(candidate) >= 2:
            found.append(candidate)

    if not found:
        for marker in _BAN_MARKERS:
            start = lowered.find(marker)
            while start != -1:
                tail = body[start + len(marker):]
                tail = tail.split(",")[0].split(".")[0].split(" и ")[0]
                words = [w for w in tail.strip().split() if w]
                candidate = " ".join(words[:4]).strip(" .,;:!?-–—«»\"'`").lower()
                if len(candidate) >= 2:
                    found.append(candidate)
                start = lowered.find(marker, start + 1)

    result: List[str] = []
    for candidate in found:
        if candidate in {"это", "текст", "ответ", "так"}:
            continue
        if "не пиши" in candidate or "не надо" in candidate:
            continue
        if candidate not in result:
            result.append(candidate)
    return result[:_MAX_BANS_PER_MESSAGE]


def contrast_terms(
    bad_texts: List[str], good_texts: List[str], limit: int = 3
) -> List[str]:
    """Выражения, которые есть в забракованном тексте и отсутствуют в её.

    Пары приоритетнее одиночных слов: «дорогие мои» — безопасный запрет, а
    «работа» запрещать нельзя, иначе бот перестанет писать по-русски. Поэтому
    одиночное слово попадает в кандидаты только если оно длинное и в её
    текстах не встречается ни разу.
    """
    def rows(texts: Optional[List[str]]) -> List[List[str]]:
        return [[w.lower() for w in _WORD_RE.findall(t or "")] for t in (texts or []) if t]

    good_words: set = set()
    good_pairs: set = set()
    for row in rows(good_texts):
        good_words.update(row)
        good_pairs.update(f"{a} {b}" for a, b in zip(row, row[1:]))

    word_counts: Counter = Counter()
    pair_counts: Counter = Counter()
    for row in rows(bad_texts):
        for word in row:
            if len(word) >= 6 and word not in _STOPWORDS and not word.isdigit():
                word_counts[word] += 1
        for first, second in zip(row, row[1:]):
            if len(first) < 3 or len(second) < 3:
                continue
            if first in _STOPWORDS and second in _STOPWORDS:
                continue
            pair_counts[f"{first} {second}"] += 1

    result: List[str] = []
    for pair, _ in pair_counts.most_common():
        if len(result) >= limit:
            return result
        if pair in good_pairs:
            continue
        if all(word in good_words for word in pair.split()):
            continue
        result.append(pair)

    for word, _ in word_counts.most_common():
        if len(result) >= limit:
            break
        if word in good_words:
            continue
        if any(word in existing.split() for existing in result):
            continue
        result.append(word)
    return result[:limit]


def build_voice_card(profile: Any, voice: Optional[Dict[str, Any]] = None) -> str:
    """Короткая карточка «за кого я пишу» — она уходит в каждый промпт.

    Через длинный диалог базовая модель перетягивает персону на себя, и текст
    начинает звучать нейтрально. Лечится не длинным описанием, а коротким
    напоминанием в каждом запросе.
    """
    voice = voice or {}
    identity = str(getattr(profile, "identity", "") or "").strip()
    niche = str(getattr(profile, "niche", "") or "").strip()
    city = str(getattr(profile, "city", "") or "").strip()
    tone = str(getattr(profile, "tone", "") or "").strip()
    forbidden = [
        str(w).strip()
        for w in (getattr(profile, "forbidden_words", None) or [])
        if str(w).strip()
    ]

    rows = ["### ЗА КОГО Я ПИШУ (держать в каждом ответе):"]
    who = ", ".join(part for part in (identity, niche, city) if part)
    if who:
        rows.append(f"- Автор: {who}.")
    if tone:
        rows.append(f"- Тон: {tone}.")
    if voice.get("learned"):
        rhythm = f"- Ритм: ~{voice.get('sentence_length_avg')} слов в предложении"
        emoji = str(voice.get("emoji_frequency") or "").strip().lower()
        rows.append(f"{rhythm}, {emoji}." if emoji else f"{rhythm}.")
        habits = []
        if voice.get("opening_habit"):
            habits.append(f"открываю {voice['opening_habit']}")
        if voice.get("closing_habit"):
            habits.append(f"закрываю {voice['closing_habit']}")
        if voice.get("explanation_habit"):
            habits.append(f"объясняю {voice['explanation_habit']}")
        if habits:
            rows.append("- " + ", ".join(habits) + ".")
    if forbidden:
        rows.append("- Никогда: " + ", ".join(f"«{w}»" for w in forbidden[:8]) + ".")
    if len(rows) == 1:
        return ""
    return "\n".join(rows)[:MAX_CARD_CHARS]


def measure_voice(texts: List[str]) -> Dict[str, Any]:
    """Чистый замер авторского голоса по набору её текстов.

    Без БД и без сети — поэтому легко тестируется и не может соврать: всё,
    что возвращается, посчитано по переданным текстам.
    """
    clean = [t.strip() for t in (texts or []) if t and t.strip()]
    voice: Dict[str, Any] = {
        "exemplar_count": len(clean),
        "learned": len(clean) >= MIN_EXEMPLARS_FOR_VOICE,
        "sentence_length_avg": 0.0,
        "emoji_per_text": 0.0,
        "emoji_frequency": "",
        "paragraph_structure": "",
        "punctuation_habits": "",
        "opening_habit": "",
        "closing_habit": "",
        "explanation_habit": "",
        "signature_words": [],
        "signature_phrases": [],
        "cta_rate": 0.0,
        "categories": {},
    }
    if not clean:
        voice["learned"] = False
        return voice

    sentence_lengths: List[int] = []
    emoji_counts: List[int] = []
    paragraph_lengths: List[int] = []
    dashes = ellipses = exclamations = questions = 0
    cta_hits = 0
    word_docs: Counter = Counter()
    word_total: Counter = Counter()
    bigrams: Counter = Counter()
    openings: Counter = Counter()
    closings: Counter = Counter()
    explanations: Counter = Counter()

    for text in clean:
        for chunk in _SENTENCE_RE.split(text):
            words = _WORD_RE.findall(chunk)
            if len(words) >= 2:
                sentence_lengths.append(len(words))

        emoji_counts.append(len(_EMOJI_RE.findall(text)))

        for paragraph in re.split(r"\n\s*\n", text):
            lines = [line for line in paragraph.splitlines() if line.strip()]
            if lines:
                paragraph_lengths.append(len(lines))

        dashes += text.count("—") + text.count(" - ")
        ellipses += text.count("…") + text.count("...")
        exclamations += text.count("!")
        questions += text.count("?")

        lowered = text.lower()
        if any(marker in lowered for marker in _CTA_KEYWORDS):
            cta_hits += 1

        parts = _sentences(text)
        if parts:
            opening = classify_opening(parts[0])
            closing = classify_closing(parts[-1])
            if opening:
                openings[opening] += 1
            if closing:
                closings[closing] += 1
        for label, markers in _EXPLANATION_MARKERS:
            if any(marker in lowered for marker in markers):
                explanations[label] += 1

        meaningful = [
            w.lower()
            for w in _WORD_RE.findall(text)
            if len(w) >= 4 and w.lower() not in _STOPWORDS and not w.isdigit()
        ]
        word_total.update(meaningful)
        word_docs.update(set(meaningful))
        for first, second in zip(meaningful, meaningful[1:]):
            bigrams[f"{first} {second}"] += 1

    count = len(clean)
    voice["sentence_length_avg"] = (
        round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0.0
    )
    voice["emoji_per_text"] = round(sum(emoji_counts) / count, 1)
    voice["cta_rate"] = round(cta_hits / count, 2)

    if count >= 2:
        ranked = [word for word, docs in word_docs.most_common(80) if docs >= 2]
    else:
        ranked = [word for word, total in word_total.most_common(80) if total >= 2]
    voice["signature_words"] = ranked[:12]
    voice["signature_phrases"] = [phrase for phrase, n in bigrams.most_common(40) if n >= 2][:6]

    if openings:
        voice["opening_habit"] = openings.most_common(1)[0][0]
    if closings:
        voice["closing_habit"] = closings.most_common(1)[0][0]
    if explanations:
        voice["explanation_habit"] = " и ".join(
            label for label, _ in explanations.most_common(2)
        )

    emoji_per_text = voice["emoji_per_text"]
    if emoji_per_text < 0.5:
        voice["emoji_frequency"] = "Почти без эмодзи"
    elif emoji_per_text <= 2.0:
        voice["emoji_frequency"] = f"Редко, ~{emoji_per_text} на текст"
    elif emoji_per_text <= 5.0:
        voice["emoji_frequency"] = f"Умеренно, ~{emoji_per_text} на текст"
    else:
        voice["emoji_frequency"] = f"Часто, ~{emoji_per_text} на текст"

    avg_paragraph = (
        round(sum(paragraph_lengths) / len(paragraph_lengths), 1) if paragraph_lengths else 0.0
    )
    if avg_paragraph <= 1.5:
        voice["paragraph_structure"] = "Абзацы по одной строке, много воздуха между блоками"
    elif avg_paragraph <= 3.0:
        voice["paragraph_structure"] = f"Короткие абзацы, ~{avg_paragraph} строки"
    else:
        voice["paragraph_structure"] = f"Плотные абзацы, ~{avg_paragraph} строк"

    habits: List[str] = []
    if dashes / count >= 1.0:
        habits.append("часто ставит тире")
    if ellipses / count >= 1.0:
        habits.append("любит многоточия")
    elif ellipses == 0:
        habits.append("без многоточий")
    if exclamations / count >= 2.0:
        habits.append("эмоциональные восклицания")
    elif exclamations == 0:
        habits.append("без восклицательных знаков")
    if questions / count >= 1.0:
        habits.append("задаёт вопросы читателю")
    voice["punctuation_habits"] = ", ".join(habits) if habits else "нейтральная пунктуация"

    return voice


class StyleEngine:
    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    @staticmethod
    def _row_to_exemplar(row) -> StyleExemplar:
        return StyleExemplar(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            exemplar_type=ExemplarType(row["exemplar_type"]),
            category=ExemplarCategory(row["category"]),
            tags=json.loads(row["tags_json"] or "[]"),
            notes=row["notes"],
            created_at=row["created_at"],
        )

    @staticmethod
    def detect_category(text: str) -> ExemplarCategory:
        """Определяет тип образца по содержимому, без вопросов пользователю."""
        lowered = (text or "").lower()
        for category, markers in _CATEGORY_MARKERS:
            if any(marker in lowered for marker in markers):
                return category
        return ExemplarCategory.POST

    @staticmethod
    def _title_from(content: str) -> str:
        first = next((line.strip() for line in (content or "").splitlines() if line.strip()), "")
        first = re.sub(r"\s+", " ", first)
        if not first:
            return "Образец стиля"
        return first[:57] + "…" if len(first) > 58 else first

    def _safe_exemplars(self, **kwargs) -> List[StyleExemplar]:
        """Чтение хранилища не должно ронять генерацию ответа."""
        try:
            return self.get_exemplars(**kwargs)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # storage
    # ------------------------------------------------------------------
    def add_exemplar(
        self,
        title: str,
        content: str,
        exemplar_type: ExemplarType = ExemplarType.GOOD_EXAMPLE,
        category: ExemplarCategory = ExemplarCategory.POST,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> StyleExemplar:
        body = (content or "").strip()
        if not body:
            raise ValueError("Пустой текст нельзя сохранить как образец стиля.")
        normalized = self._normalize(body)

        conn = get_connection()
        c = conn.cursor()

        # Один и тот же текст не должен лежать в хранилище дважды: дубликаты
        # искажают замер голоса.
        c.execute("SELECT * FROM style_exemplars WHERE exemplar_type = ?", (exemplar_type.value,))
        for row in c.fetchall():
            if self._normalize(row["content"]) == normalized:
                conn.close()
                return self._row_to_exemplar(row)

        exemplar = StyleExemplar(
            id=str(uuid.uuid4()),
            title=(title or self._title_from(body)).strip(),
            content=body,
            exemplar_type=exemplar_type,
            category=category,
            tags=tags or [],
            notes=notes,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        c.execute(
            """
        INSERT INTO style_exemplars (
            id, title, content, exemplar_type, category, tags_json, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                exemplar.id,
                exemplar.title,
                exemplar.content,
                exemplar.exemplar_type.value,
                exemplar.category.value,
                json.dumps(exemplar.tags),
                exemplar.notes,
                exemplar.created_at,
            ),
        )
        conn.commit()
        conn.close()
        return exemplar

    def learn_from_text(
        self,
        content: str,
        exemplar_type: ExemplarType = ExemplarType.GOOD_EXAMPLE,
        title: Optional[str] = None,
        category: Optional[ExemplarCategory] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> Optional[StyleExemplar]:
        """Запоминает присланный текст как образец. None — если это не текст, а реплика."""
        body = (content or "").strip()
        if len(body) < MIN_LEARNABLE_CHARS:
            return None
        return self.add_exemplar(
            title=title or self._title_from(body),
            content=body,
            exemplar_type=exemplar_type,
            category=category or self.detect_category(body),
            tags=tags,
            notes=notes,
        )

    def learn_visual_style(self, description: str) -> Optional[StyleExemplar]:
        """Запоминает описание визуального стиля — оно уходит в генерацию фото."""
        body = (description or "").strip()
        if len(body) < 10:
            return None
        return self.add_exemplar(
            title="Визуальный стиль",
            content=body,
            exemplar_type=ExemplarType.GOOD_EXAMPLE,
            category=ExemplarCategory.DESCRIPTION,
            tags=[VISUAL_TAG],
            notes="Подставляется в промпт генерации изображений",
        )

    def visual_signature(self, limit: int = 3) -> str:
        rows = self._safe_exemplars(
            category=ExemplarCategory.DESCRIPTION, limit=limit, tag=VISUAL_TAG
        )
        return " ".join(ex.content.strip() for ex in rows if ex.content.strip())[:800]

    def get_exemplars(
        self,
        category: Optional[ExemplarCategory] = None,
        exemplar_type: Optional[ExemplarType] = None,
        limit: int = 5,
        tag: Optional[str] = None,
    ) -> List[StyleExemplar]:
        conn = get_connection()
        c = conn.cursor()
        sql = "SELECT * FROM style_exemplars WHERE 1=1"
        params: List[Any] = []
        if category:
            sql += " AND category = ?"
            params.append(category.value)
        if exemplar_type:
            sql += " AND exemplar_type = ?"
            params.append(exemplar_type.value)
        if tag:
            sql += " AND tags_json LIKE ?"
            params.append(f"%{tag}%")

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        return [self._row_to_exemplar(r) for r in rows]

    def delete_exemplar(self, exemplar_id: str) -> bool:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM style_exemplars WHERE id = ?", (exemplar_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        return bool(deleted)

    def forget_exemplars(self, phrase: str) -> int:
        """Удаляет образцы, в которых встречается фраза. Возвращает число удалённых."""
        needle = self._normalize(phrase)
        if len(needle) < 3:
            return 0
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, title, content FROM style_exemplars")
        doomed = [
            row["id"]
            for row in c.fetchall()
            if needle in self._normalize(row["content"]) or needle in self._normalize(row["title"])
        ]
        for exemplar_id in doomed:
            c.execute("DELETE FROM style_exemplars WHERE id = ?", (exemplar_id,))
        conn.commit()
        conn.close()
        return len(doomed)

    # ------------------------------------------------------------------
    # measured voice
    # ------------------------------------------------------------------
    def analyze_voice(self, limit: int = 30) -> Dict[str, Any]:
        """Замеряет голос по сохранённым образцам (визуальные описания не в счёт)."""
        samples = [
            ex
            for ex in self._safe_exemplars(exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=limit)
            if VISUAL_TAG not in (ex.tags or [])
        ]
        voice = measure_voice([ex.content for ex in samples])
        categories: Dict[str, int] = {}
        for ex in samples:
            categories[ex.category.value] = categories.get(ex.category.value, 0) + 1
        voice["categories"] = categories
        return voice

    def forbidden_candidates(
        self, sample_text: Optional[str] = None, limit: int = 3
    ) -> List[str]:
        """Кандидаты в стоп-слова: что есть в забракованном и нет в её текстах.

        Используется, когда она забраковала ответ, но не назвала слова. Тогда
        запрет выводится контрастом, а не догадкой.
        """
        bad_texts: List[str] = []
        if sample_text and sample_text.strip():
            bad_texts.append(sample_text)
        else:
            bad_texts = [
                ex.content
                for ex in self._safe_exemplars(exemplar_type=ExemplarType.BAD_EXAMPLE, limit=5)
            ]
        good_texts = [
            ex.content
            for ex in self._safe_exemplars(exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=20)
            if VISUAL_TAG not in (ex.tags or [])
        ]
        if not bad_texts:
            return []
        return contrast_terms(bad_texts, good_texts, limit=limit)

    def voice_card(
        self, profile: Any = None, voice: Optional[Dict[str, Any]] = None
    ) -> str:
        """Карточка личности для переинжекта в каждый промпт."""
        if profile is None:
            try:
                from src.brain.engines.profile_engine import ProfileEngine

                profile = ProfileEngine().get_profile()
            except Exception:
                profile = None
        voice = voice if voice is not None else self.analyze_voice()
        return build_voice_card(profile, voice)

    def derive_profile(
        self, base: StyleProfile, voice: Optional[Dict[str, Any]] = None
    ) -> StyleProfile:
        """Подменяет дефолтные значения профиля замерами по её текстам."""
        voice = voice if voice is not None else self.analyze_voice()
        if not voice.get("learned"):
            return base

        data = base.model_dump()
        if voice.get("sentence_length_avg"):
            data["sentence_length_avg"] = voice["sentence_length_avg"]
        if voice.get("emoji_frequency"):
            data["emoji_frequency"] = voice["emoji_frequency"]
        if voice.get("paragraph_structure"):
            data["paragraph_structure"] = voice["paragraph_structure"]
        if voice.get("punctuation_habits"):
            data["punctuation_habits"] = voice["punctuation_habits"]

        vocabulary = list(dict.fromkeys([*(data.get("vocabulary") or []), *voice["signature_words"]]))
        data["vocabulary"] = vocabulary[:24]
        phrases = list(
            dict.fromkeys([*(data.get("preferred_expressions") or []), *voice["signature_phrases"]])
        )
        data["preferred_expressions"] = phrases[:12]
        return StyleProfile(**data)

    def vault_summary(self) -> Dict[str, Any]:
        """Что бот уже выучил — для команды /стиль."""
        by_type: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        total = 0
        last_added = None
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute(
                "SELECT exemplar_type, category, COUNT(*) AS n FROM style_exemplars "
                "GROUP BY exemplar_type, category"
            )
            for row in c.fetchall():
                n = int(row["n"])
                total += n
                by_type[row["exemplar_type"]] = by_type.get(row["exemplar_type"], 0) + n
                by_category[row["category"]] = by_category.get(row["category"], 0) + n
            c.execute("SELECT MAX(created_at) AS last_added FROM style_exemplars")
            row = c.fetchone()
            last_added = row["last_added"] if row else None
            conn.close()
        except Exception:
            pass
        return {
            "total": total,
            "by_type": by_type,
            "by_category": by_category,
            "last_added": last_added,
            "voice": self.analyze_voice(),
        }

    # ------------------------------------------------------------------
    # prompt + benchmark
    # ------------------------------------------------------------------
    def build_style_instructions(
        self, profile: StyleProfile, category: Optional[ExemplarCategory] = None
    ) -> str:
        """Собирает стилевые директивы: замеры по её текстам + эталоны + антипримеры."""
        voice = self.analyze_voice()
        effective = self.derive_profile(profile, voice)

        lines: List[str] = []
        card = self.voice_card(voice=voice)
        if card:
            lines.extend([card, ""])

        lines.extend([
            "### СТИЛЬ И ТОНАЛЬНОСТЬ АВТОРА:",
            f"- Тон: {effective.tone}",
            f"- Юмор: {effective.humor}",
            f"- Структура текста: {effective.paragraph_structure}",
            f"- Длина предложений: средняя ~{int(effective.sentence_length_avg)} слов, ритмичный слог.",
            f"- Эмодзи: {effective.emoji_frequency}.",
            f"- Пунктуация: {effective.punctuation_habits}.",
        ])

        if effective.forbidden_expressions:
            lines.append(
                f"- ЗАПРЕЩЕННЫЕ СЛОВА И КЛИШЕ: {', '.join(effective.forbidden_expressions)}"
            )
        if effective.preferred_expressions:
            lines.append(
                f"- Характерные авторские связки: {', '.join(effective.preferred_expressions)}"
            )

        if voice["learned"]:
            lines.append("")
            lines.append(f"### ЗАМЕРЕНО ПО {voice['exemplar_count']} ЕЁ ТЕКСТАМ:")
            lines.append(
                f"- Средняя длина предложения: {voice['sentence_length_avg']} слов — держись этой длины."
            )
            lines.append(f"- Эмодзи: {voice['emoji_frequency']} — не превышай эту норму.")
            if voice["signature_words"]:
                lines.append(
                    "- Слова, которые она действительно использует: "
                    + ", ".join(voice["signature_words"])
                )
            if voice["signature_phrases"]:
                lines.append("- Её связки: " + "; ".join(voice["signature_phrases"]))
            if voice.get("opening_habit"):
                lines.append(f"- Начинает текст {voice['opening_habit']} — начни так же.")
            if voice.get("closing_habit"):
                lines.append(f"- Заканчивает {voice['closing_habit']} — закончи так же.")
            if voice.get("explanation_habit"):
                lines.append(
                    f"- Объясняет {voice['explanation_habit']} — объясняй тем же способом."
                )
            if voice["cta_rate"] >= 0.5:
                lines.append("- Она почти всегда заканчивает призывом — сохрани его.")
            elif voice["cta_rate"] <= 0.2:
                lines.append("- Она редко ставит призыв в конце — не навязывай CTA.")
            lines.append("- Цель: текст должен быть неотличим от примеров ниже.")
        else:
            lines.append("")
            lines.append(
                f"### ОБРАЗЦОВ ЕЁ ТЕКСТОВ ПОКА МАЛО ({voice['exemplar_count']} из "
                f"{MIN_EXEMPLARS_FOR_VOICE}). Не выдумывай авторский голос и не имитируй чужой: "
                "пиши просто, живо и по делу, без штампов."
            )

        good: List[StyleExemplar] = []
        seen: set = set()
        if category:
            for ex in self._safe_exemplars(
                category=category, exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=2
            ):
                if VISUAL_TAG in (ex.tags or []):
                    continue
                good.append(ex)
                seen.add(ex.id)
        for ex in self._safe_exemplars(exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=5):
            if len(good) >= 3:
                break
            if ex.id in seen or VISUAL_TAG in (ex.tags or []):
                continue
            good.append(ex)
            seen.add(ex.id)

        if good:
            lines.append("\n### ЭТАЛОННЫЕ ПРИМЕРЫ АВТОРСКОГО ТЕКСТА (GOOD EXAMPLES):")
            for idx, ex in enumerate(good):
                lines.append(f"--- Пример {idx + 1} ({ex.title}) ---\n{ex.content}\n")

        bad = self._safe_exemplars(exemplar_type=ExemplarType.BAD_EXAMPLE, limit=2)
        if bad:
            lines.append("### ТАК ПИСАТЬ НЕЛЬЗЯ (она это забраковала):")
            for idx, ex in enumerate(bad):
                lines.append(f"--- Антипример {idx + 1} ({ex.title}) ---\n{ex.content}\n")

        return "\n".join(lines)

    def evaluate_benchmark(
        self,
        text: str,
        profile: StyleProfile,
        forbidden_words: Optional[List[str]] = None,
        voice: Optional[Dict[str, Any]] = None,
    ) -> StyleBenchmarkResult:
        """
        Считает бенчмарк по 5 метрикам. Если голос выучен, целями становятся
        замеры по её текстам, а не значения по умолчанию:
        1. vocabulary_similarity — пересечение с её лексикой
        2. sentence_rhythm_score — близость к её длине предложения
        3. emoji_density_score — близость к её норме эмодзи
        4. cta_presence_score — призыв (не штрафуется, если она его не ставит)
        5. forbidden_violations — стоп-слова
        """
        voice = voice if voice is not None else self.analyze_voice()
        learned = bool(voice.get("learned"))

        target_length = profile.sentence_length_avg
        if learned and voice.get("sentence_length_avg"):
            target_length = float(voice["sentence_length_avg"])

        # 1. Ритм предложений
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 3]
        avg_len = 0.0
        if sentences:
            words_per_sent = [len(re.findall(r"\w+", s)) for s in sentences]
            avg_len = sum(words_per_sent) / len(words_per_sent)
            dev = abs(avg_len - target_length)
            rhythm_score = max(0.0, min(1.0, 1.0 - (dev / 15.0)))
        else:
            rhythm_score = 0.5

        # 2. Лексика: пересечение с её образцами и словарём профиля
        good_ex = [
            ex
            for ex in self._safe_exemplars(exemplar_type=ExemplarType.GOOD_EXAMPLE, limit=5)
            if VISUAL_TAG not in (ex.tags or [])
        ]
        good_words = set()
        for ex in good_ex:
            good_words.update(re.findall(r"\w+", ex.content.lower()))
        if profile.vocabulary:
            good_words.update([w.lower() for w in profile.vocabulary])
        good_words.update(voice.get("signature_words") or [])

        text_words = set(re.findall(r"\w+", text.lower()))
        if good_words and text_words:
            overlap = text_words.intersection(good_words)
            vocab_sim = min(1.0, len(overlap) / (len(text_words) * 0.40))
        else:
            vocab_sim = 0.75

        # 3. Эмодзи
        emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]", text))
        if learned:
            deviation = abs(emoji_count - float(voice.get("emoji_per_text") or 0.0))
            emoji_score = max(0.2, min(1.0, 1.0 - max(0.0, deviation - 1.0) * 0.15))
        elif 1 <= emoji_count <= 5:
            emoji_score = 1.0
        elif emoji_count == 0:
            emoji_score = 0.8
        else:
            emoji_score = max(0.2, 1.0 - (emoji_count - 5) * 0.15)

        # 4. Призыв к действию
        has_cta = any(k in text.lower() for k in _CTA_KEYWORDS)
        if has_cta:
            cta_score = 1.0
        elif learned and float(voice.get("cta_rate") or 0.0) <= 0.2:
            cta_score = 1.0
        else:
            cta_score = 0.5

        # 5. Стоп-слова
        all_forbidden = list(profile.forbidden_expressions)
        if forbidden_words:
            all_forbidden.extend(forbidden_words)

        violations = 0
        for word in all_forbidden:
            if word and word.lower() in text.lower():
                violations += 1

        overall = 0.30 * vocab_sim + 0.25 * rhythm_score + 0.20 * emoji_score + 0.25 * cta_score
        if violations > 0:
            overall = max(0.0, overall - (violations * 0.40))

        notes = (
            f"Avg sent len: {round(avg_len, 1)} (target {round(target_length, 1)}); "
            f"Emojis: {emoji_count}; CTA: {'YES' if has_cta else 'NO'}; "
            f"Violations: {violations}; Vault: {voice.get('exemplar_count', 0)}"
        )

        return StyleBenchmarkResult(
            vocabulary_similarity=round(vocab_sim, 2),
            sentence_rhythm_score=round(rhythm_score, 2),
            emoji_density_score=round(emoji_score, 2),
            cta_presence_score=round(cta_score, 2),
            forbidden_violations=violations,
            overall_score=round(overall, 2),
            notes=notes,
        )
