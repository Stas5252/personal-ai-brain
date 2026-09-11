"""Pure rules for memory deduplication, conflict detection and provenance."""
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

OWNER = "conversation"
VOICE = "voice"
ONBOARDING = "onboarding"
PROFILE = "profile"
FORWARDED = "forwarded"
DOCUMENT = "document"
DERIVED = "derived"
_OWNER_SOURCES = {OWNER, VOICE, ONBOARDING, PROFILE, "owner", "user"}
SOURCE_LABELS = {
    OWNER: "сказала сама",
    VOICE: "сказала голосом",
    ONBOARDING: "из знакомства",
    PROFILE: "из анкеты",
    FORWARDED: "из пересланного сообщения",
    DOCUMENT: "из документа",
    DERIVED: "бот вывел сам",
}
UNKNOWN_SOURCE_LABEL = "источник неизвестен"
TRUST_OWNER = 1.0
TRUST_EXTERNAL = 0.5
TRUST_QUARANTINED = 0.0
NEAR_DUPLICATE_THRESHOLD = 0.82
NUMERIC_SUBJECT_MATCH = 0.60
ATTRIBUTE_SUBJECT_MATCH = 0.30
MAX_MEMORY_CHARS = 600
REASON_NEGATION = "negation"
REASON_OVERRIDE = "explicit_override"
REASON_NUMERIC = "numeric_change"
REASON_ATTRIBUTE = "attribute_change"
REASON_INJECTION = "external_instruction_quarantined"

_STOPWORDS = {
    "это", "тогда", "потом", "очень", "просто", "надо", "нужно", "можно",
    "буду", "была", "было", "были", "этот", "эта", "эти", "также", "если",
    "чтобы", "когда", "который", "которая", "которое", "меня", "тебя",
    "себя", "свои", "свой", "своя", "еще", "уже", "очен", "обычно",
    "иногда", "вообще",
}
_OVERRIDE_MARKERS = (
    "теперь", "с этого момента", "отныне", "изменилось", "поменял", "поменяла",
    "сменил", "сменила", "перешла", "перешел", "обновила", "подняла цен",
    "подняла прайс",
)
_NEGATION_MARKERS = (
    "больше не", "уже не", "перестал", "перестала", "не снимаю", "не работаю",
    "не беру", "отказалась", "отказался", "никогда не",
)
_SINGLE_VALUE_ATTRIBUTES: Dict[str, Tuple[str, ...]] = {
    "прайс": ("прайс", "цен", "стоимост", "стоит", "тариф"),
    "город": ("живу", "мой город", "переехал", "переехала"),
    "камера": ("камера", "камеру", "снимаю на", "тушк"),
    "ниша": ("моя ниша", "нишу", "специализ"),
    "аккаунт": ("инстаграм", "instagram", "инста", "мой аккаунт"),
    "телефон": ("телефон", "мой номер"),
    "почта": ("почта", "email", "e-mail", "мейл"),
}
_INJECTION_MARKERS = (
    "запомни", "запиши в памят", "сохрани в памят", "теперь ты", "отныне ты",
    "ты должен", "ты должна", "игнорируй", "забудь все", "новые инструкции",
    "новая инструкция", "твоя новая роль", "веди себя как", "system:",
    "система:", "ignore previous", "ignore all previous", "disregard previous",
    "you must", "you are now", "act as", "remember that you", "new instructions",
)
_NUM_RE = re.compile(r"\d[\d\s\u00a0\u202f.,]*")
_THOUSANDS_RE = re.compile(r"(\d+)\s*[кk]\b", re.IGNORECASE)


def normalize(text: str) -> str:
    lowered = (text or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", lowered)).strip()


def sanitize(text: str, max_chars: int = MAX_MEMORY_CHARS) -> str:
    raw = re.sub(r"[ \t]+", " ", (text or "").strip())
    if len(raw) <= max_chars:
        return raw
    cut = raw[:max_chars].rstrip()
    space = cut.rfind(" ")
    if space > max_chars * 0.6:
        cut = cut[:space].rstrip()
    return cut + "..."


def tokens(text: str) -> Set[str]:
    return {w for w in re.findall(r"\w+", normalize(text)) if len(w) > 3 and w not in _STOPWORDS}


def numbers(text: str) -> List[float]:
    expanded = _THOUSANDS_RE.sub(lambda m: str(int(m.group(1)) * 1000), text or "")
    found: List[float] = []
    for raw in _NUM_RE.findall(expanded):
        compact = re.sub(r"[\s\u00a0\u202f]", "", raw).strip(".,")
        if re.fullmatch(r"\d+[.,]\d{3}", compact or ""):
            compact = re.sub(r"[.,]", "", compact)
        try:
            found.append(float(compact.replace(",", ".")))
        except (ValueError, AttributeError):
            pass
    return found


def _numeric_tokens(text: str) -> Set[str]:
    return {w for w in tokens(text) if w.isdigit()}


def _subject_tokens(text: str) -> Set[str]:
    return tokens(text) - _numeric_tokens(text)


def _jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def subject_similarity(a: str, b: str) -> float:
    return _jaccard(_subject_tokens(a), _subject_tokens(b))


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        na, nb = normalize(a), normalize(b)
        return 1.0 if na and na == nb else 0.0
    inter = len(ta & tb)
    if not inter:
        return 0.0
    jaccard = inter / len(ta | tb)
    ratio = min(len(ta), len(tb)) / max(len(ta), len(tb))
    return max(jaccard, inter / min(len(ta), len(tb)) * 0.9) if ratio >= 0.6 else jaccard


def is_near_duplicate(a: str, b: str, threshold: float = NEAR_DUPLICATE_THRESHOLD) -> bool:
    return bool(normalize(a)) and normalize(a) == normalize(b) or similarity(a, b) >= threshold


def _keeper_key(item: Dict[str, Any]) -> Tuple[float, str, int]:
    return (float(item.get("importance") or 0.0), str(item.get("updated_at") or item.get("created_at") or ""), len(str(item.get("content") or "")))


def consolidation_groups(items: Sequence[Dict[str, Any]], threshold: float = NEAR_DUPLICATE_THRESHOLD) -> List[Dict[str, Any]]:
    pool = [dict(i) for i in items if str(i.get("content") or "").strip()]
    used: Set[int] = set()
    groups: List[Dict[str, Any]] = []
    for idx, item in enumerate(pool):
        if idx in used:
            continue
        cluster = [item]
        used.add(idx)
        for jdx in range(idx + 1, len(pool)):
            if jdx not in used and is_near_duplicate(item["content"], pool[jdx]["content"], threshold):
                cluster.append(pool[jdx])
                used.add(jdx)
        if len(cluster) > 1:
            cluster.sort(key=_keeper_key, reverse=True)
            groups.append({"keeper": cluster[0].get("id"), "keeper_content": cluster[0].get("content"), "duplicates": [c.get("id") for c in cluster[1:]]})
    return groups


def _attributes(text: str) -> Set[str]:
    lowered = (text or "").lower().replace("ё", "е")
    return {key for key, markers in _SINGLE_VALUE_ATTRIBUTES.items() if any(m in lowered for m in markers)}


def _attribute_words(attrs: Set[str]) -> Set[str]:
    words: Set[str] = set()
    for key in attrs:
        words.add(key)
        for marker in _SINGLE_VALUE_ATTRIBUTES.get(key, ()):
            words.update(w for w in re.findall(r"\w+", marker) if len(w) > 3)
    return words


def _has(text: str, markers: Tuple[str, ...]) -> bool:
    lowered = (text or "").lower().replace("ё", "е")
    return any(m in lowered for m in markers)


def detect_value_conflict(new_content: str, old_content: str) -> Optional[str]:
    if not (new_content or "").strip() or not (old_content or "").strip() or normalize(new_content) == normalize(old_content):
        return None
    new_words, old_words = tokens(new_content), tokens(old_content)
    overlap = len(new_words & old_words)
    shared_attrs = _attributes(new_content) & _attributes(old_content)
    if _has(new_content, _NEGATION_MARKERS) and not _has(old_content, _NEGATION_MARKERS) and overlap >= 1:
        return REASON_NEGATION
    if _has(new_content, _OVERRIDE_MARKERS) and (overlap >= 2 or shared_attrs and overlap >= 1):
        return REASON_OVERRIDE
    new_nums, old_nums = set(numbers(new_content)), set(numbers(old_content))
    if new_nums and old_nums and new_nums != old_nums and subject_similarity(new_content, old_content) >= NUMERIC_SUBJECT_MATCH:
        return REASON_NUMERIC
    # Price is multi-valued across services. It must never fall through to the
    # generic single-attribute branch after the numeric subject check failed.
    attribute_attrs = shared_attrs - {"прайс"}
    if attribute_attrs and subject_similarity(new_content, old_content) >= ATTRIBUTE_SUBJECT_MATCH:
        if (new_words ^ old_words) - _attribute_words(attribute_attrs):
            return REASON_ATTRIBUTE
    return None


def is_owner_source(source: Optional[str]) -> bool:
    return (source or OWNER).strip().lower() in _OWNER_SOURCES


def source_label(source: Optional[str]) -> str:
    return SOURCE_LABELS.get((source or "").strip().lower(), UNKNOWN_SOURCE_LABEL)


def looks_like_injection(text: str) -> bool:
    lowered = (text or "").lower().replace("ё", "е")
    return any(m in lowered for m in _INJECTION_MARKERS)


def admit_external(text: str, source: Optional[str]) -> Tuple[bool, float, str]:
    if is_owner_source(source):
        return True, TRUST_OWNER, "owner"
    if looks_like_injection(text):
        return False, TRUST_QUARANTINED, REASON_INJECTION
    return True, TRUST_EXTERNAL, "external_material"
