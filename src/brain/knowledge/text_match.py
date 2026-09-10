"""Russian-aware lexical matching for knowledge retrieval.

Retrieval used to compare raw word forms, so \u00abвозражение\u00bb in a question and
\u00abвозражения\u00bb in a lesson counted as two unrelated words. On a corpus that is
entirely Russian that is not a rounding error: the correct chunk scored zero
and the answer came back ungrounded.

Everything here is pure stdlib and deterministic, so it can be tested without
the database, the embedding model or the vector store.
"""
from __future__ import annotations

import re

__all__ = [
    "MIN_STEM_LENGTH",
    "TOPIC_BONUS",
    "lexical_score",
    "query_topic",
    "stem",
    "tokenize",
    "topic_bonus",
]

# Keep at least this many characters, otherwise short words collapse into each
# other. Three is the shortest that still lets \u00abцена\u00bb and \u00abцены\u00bb meet at \u00abцен\u00bb.
MIN_STEM_LENGTH = 3

# Two passes, because Russian stacks endings: \u00abвозражением\u00bb needs \u00abем\u00bb removed
# and then the leftover \u00abи\u00bb, to land on the same stem as \u00abвозражения\u00bb.
_MAX_STRIPS = 2

# Deliberately small. A topic match hints that two texts cover the same area;
# it is never proof that a chunk answers the question.
TOPIC_BONUS = 0.12

# Letters only. Years and prices are not retrieval signal and they used to add
# noise to the token set.
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# Function words carry no signal but inflate the denominator, which pushed
# genuinely relevant chunks below the score threshold.
_STOPWORDS = frozenset(
    {
        "а", "без", "бы", "быть", "в", "вас", "весь", "во", "вот", "все",
        "всего", "вы", "да", "даже", "для", "до", "его", "ее", "если", "есть",
        "еще", "же", "за", "и", "из", "или", "им", "их", "к", "как", "когда",
        "кто", "ли", "меня", "мне", "можно", "мой", "мы", "на", "над", "наш",
        "не", "нет", "ни", "но", "ну", "о", "об", "он", "она", "они", "от",
        "по", "под", "при", "с", "себя", "так", "также", "там", "твой", "то",
        "того", "тоже", "только", "тот", "ты", "у", "уже", "чего", "чем", "что",
        "чтобы", "эта", "эти", "это", "этот", "я",
        "and", "for", "in", "is", "of", "or", "the", "to", "with",
    }
)

# Sorted longest-first at import time so the table below can be edited in any
# order without silently changing which suffix wins.
#
# Derivational endings such as \u00ab-ение\u00bb are intentionally absent: stripping them
# turns \u00abвозражение\u00bb into \u00abвозраж\u00bb while \u00abвозражения\u00bb only loses \u00abия\u00bb, and the
# two forms stop matching. Inflection only.
_SUFFIXES = tuple(
    sorted(
        {
            "иями", "ами", "ями", "иям", "иях", "ией", "иев",
            "ать", "ять", "еть", "ить", "уть", "ишь", "ешь",
            "ите", "ете", "ает", "яет", "ают", "яют", "али", "яли",
            "ам", "ям", "ах", "ях", "ов", "ев", "ий", "ый", "ой", "ей",
            "ая", "яя", "ые", "ие", "ое", "ых", "их", "ым", "им", "ем", "ом",
            "ию", "ью", "ия", "ую", "юю", "ла", "ло", "ли", "ут", "ют",
            "а", "е", "и", "й", "о", "у", "ы", "ь", "я", "ю",
        },
        key=len,
        reverse=True,
    )
)


def stem(word: str) -> str:
    """Reduce a Russian word to a comparable stem."""
    normalised = word.lower().replace("\u0451", "е")
    for _ in range(_MAX_STRIPS):
        for suffix in _SUFFIXES:
            if normalised.endswith(suffix) and len(normalised) - len(suffix) >= MIN_STEM_LENGTH:
                normalised = normalised[: -len(suffix)]
                break
        else:
            break
    return normalised


def tokenize(text: str) -> set[str]:
    """Split text into comparable stems, dropping stopwords."""
    tokens: set[str] = set()
    for raw in _WORD.findall(text or ""):
        lowered = raw.lower().replace("\u0451", "е")
        if len(lowered) < 2 or lowered in _STOPWORDS:
            continue
        tokens.add(stem(lowered))
    return tokens


def lexical_score(query: str, content: str) -> float:
    """Score ``content`` against ``query`` on a 0.0 \u2013 1.0 scale."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    needle = (query or "").strip().lower()
    if needle and needle in (content or "").lower():
        return 0.95

    common = query_tokens & tokenize(content)
    if not common:
        return 0.0
    return len(common) / len(query_tokens)


def query_topic(query: str) -> str:
    """Route a question into the same nine topics the corpus is indexed under."""
    from src.brain.knowledge.corpus import TOPIC_GENERAL, classify_topic

    try:
        return classify_topic(query or "")
    except Exception:
        return TOPIC_GENERAL


def topic_bonus(topic: str | None, subcategory: str | None) -> float:
    """Small nudge when a chunk sits in the topic the question is about."""
    from src.brain.knowledge.corpus import TOPIC_GENERAL

    if not topic or not subcategory or topic == TOPIC_GENERAL:
        return 0.0
    return TOPIC_BONUS if str(subcategory).strip().lower() == topic else 0.0
