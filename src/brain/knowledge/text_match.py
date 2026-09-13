"""Russian-aware lexical matching for knowledge retrieval.

Retrieval used to compare raw word forms, so «возражение» in a question and
«возражения» in a lesson counted as two unrelated words. On a corpus that is
entirely Russian that is not a rounding error: the correct chunk scored zero
and the answer came back ungrounded.

This module is the single owner of morphology. ``HybridSearchEngine`` used to
carry a second, independent stemmer, so the words a question was scored with
and the FTS5 prefixes it was searched with could disagree — the query matched
lexically and then lost the keyword guard, or the other way round. Index-side
code now imports :func:`search_stem` from here instead.

Everything here is pure stdlib and deterministic, so it can be tested without
the database, the embedding model or the vector store.
"""
from __future__ import annotations

import os
import re

__all__ = [
    "LAYER_BONUS",
    "MIN_STEM_LENGTH",
    "TOPIC_BONUS",
    "layer_bonus",
    "layer_is_strict",
    "lexical_score",
    "query_topic",
    "search_stem",
    "stem",
    "tokenize",
    "topic_bonus",
]

# Keep at least this many characters, otherwise short words collapse into each
# other. Three is the shortest that still lets «цена» and «цены» meet at «цен».
MIN_STEM_LENGTH = 3

# Two passes, because Russian stacks endings: «возражением» needs «ем» removed
# and then the leftover «и», to land on the same stem as «возражения».
_MAX_STRIPS = 2

# Deliberately small. A topic match hints that two texts cover the same area;
# it is never proof that a chunk answers the question.
TOPIC_BONUS = 0.12

# A knowledge layer is a preference, not a gate. The course corpus is tagged
# PROFESSIONAL while business questions arrive asking for BUSINESS, so the old
# hard filter answered those questions with nothing at all. The bonus keeps the
# requested layer on top without hiding the rest of the material.
LAYER_BONUS = 0.06

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
# Derivational endings such as «-ение» are intentionally absent: stripping them
# turns «возражение» into «возраж» while «возражения» only loses «ия», and the
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

# Word families the inflection table cannot join, because the root itself
# changes: «свадьба» keeps the soft sign, «свадебная» drops it. Wedding work is
# the single most common paid job in this corpus, so the pair is worth naming.
_SEARCH_PREFIXES = ("свад",)


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


def search_stem(word: str) -> str:
    """Stem for index-side matching: FTS5 prefixes and the keyword guard.

    Same morphology as :func:`stem`, so a question tokenised for scoring and
    the prefix query built from it can no longer disagree. The trailing soft or
    hard sign is dropped because ``"статья"*`` and ``"статьи"*`` have to share
    one prefix in FTS5.
    """
    normalised = (word or "").strip().lower().replace("\u0451", "е")
    if len(normalised) <= MIN_STEM_LENGTH:
        return normalised
    for prefix in _SEARCH_PREFIXES:
        if normalised.startswith(prefix):
            return prefix
    return stem(normalised).rstrip("ьъ")


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
    """Score ``content`` against ``query`` on a 0.0 – 1.0 scale."""
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


def layer_is_strict() -> bool:
    """True when the owner asked for the old behaviour: layer as a hard filter.

    Default is off. ``BRAIN_LAYER_STRICT=true`` restores filtering for anyone
    who keeps genuinely separate corpora per layer.
    """
    raw = os.environ.get("BRAIN_LAYER_STRICT", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def layer_bonus(requested: str | None, chunk_layer: str | None) -> float:
    """Reward a chunk that sits in the requested layer, never require it."""
    if not requested or not chunk_layer:
        return 0.0
    return LAYER_BONUS if str(requested) == str(chunk_layer) else 0.0
