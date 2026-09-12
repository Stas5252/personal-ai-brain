"""Grounding: the owner's own materials reach every model call.

Why this module exists
----------------------
The repository ships 57 course PDFs (``материалы для ии``) and 40 Markdown
lessons, indexed by ``scripts/ingest_course_corpus.py`` and
``scripts/seed_vetted_knowledge.py``. Exactly one code path ever read that
index: ``BrainService.process_chat``. Every deterministic engine — promotion,
sales, shooting, content, proactive — calls ``LLMProvider.chat_completion``
directly with a template plus the profile, so 18 of the 32 guided actions
answered without ever opening the knowledge base. The material was present,
indexed, and unused.

Grounding therefore lives at the single choke point every model call passes
through, instead of being re-implemented in a dozen engines that would drift
apart.

Failure policy
--------------
Grounding is additive and best effort. A missing database, a cold vector index
or an unreadable chunk degrades an answer to "no citations"; it must never turn
a working answer into an exception. Every failure path returns the original
messages unchanged.

Environment switches
--------------------
``BRAIN_GROUNDING_ENABLED``    default ``true``
``BRAIN_GROUNDING_TOP_K``      default 3 chunks per call
``BRAIN_GROUNDING_MAX_CHARS``  default 2400 characters of evidence per call
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Optional, Sequence

log = logging.getLogger(__name__)

# Written by BrainService.process_chat when it attaches knowledge itself. Its
# presence means the caller already grounded the prompt, so a second copy would
# only spend context window.
UPSTREAM_KNOWLEDGE_MARKER = "МАТЕРИАЛЫ ИЗ БАЗЫ ЗНАНИЙ"
EVIDENCE_HEADER = "### МАТЕРИАЛЫ ВЛАДЕЛЬЦА (курс и конспекты)"
SOURCES_PREFIX = "📚 Источники:"

DEFAULT_TOP_K = 3
DEFAULT_MAX_CHARS = 2_400
# Shorter turns ("ок", "привет") carry no retrievable intent, and retrieving on
# them only spends a database round trip per message.
MIN_QUERY_CHARS = 8
MIN_EXCERPT_CHARS = 120


def enabled() -> bool:
    raw = os.environ.get("BRAIN_GROUNDING_ENABLED", "").strip().lower()
    if not raw:
        return True
    return raw in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("%s=%r is not an integer; using %d.", name, raw, default)
        return default
    return value if value > 0 else default


def top_k() -> int:
    return _positive_int("BRAIN_GROUNDING_TOP_K", DEFAULT_TOP_K)


def max_chars() -> int:
    return max(_positive_int("BRAIN_GROUNDING_MAX_CHARS", DEFAULT_MAX_CHARS), MIN_EXCERPT_CHARS)


def message_text(content: Any) -> str:
    """Flattens an OpenAI-style message body into plain text.

    Vision calls send a list of parts, so a photo question would otherwise look
    like an empty question and silently skip retrieval.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, (list, tuple)):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in (None, "text"):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return "" if content is None else str(content)


def last_user_query(messages: Sequence[Any]) -> str:
    """The question to retrieve against: the newest non-empty user turn."""
    for message in reversed(list(messages or [])):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        text = message_text(message.get("content")).strip()
        if text:
            return text
    return ""


def already_grounded(messages: Sequence[Any]) -> bool:
    for message in messages or []:
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        text = message_text(message.get("content"))
        if UPSTREAM_KNOWLEDGE_MARKER in text or EVIDENCE_HEADER in text:
            return True
    return False


def expects_json(messages: Sequence[Any]) -> bool:
    """True when the caller contracted for a strict JSON shape.

    Engines such as PromotionEngine merge the model's JSON back into their own
    template and discard anything that adds keys or changes types. Asking those
    calls to append a human-readable source line would only break the parse, so
    they get the evidence without the citation instruction.
    """
    for message in messages or []:
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        if "json" in message_text(message.get("content")).casefold():
            return True
    return False


def _hit_parts(hit: Any):
    """Unpacks the ``(chunk, score, trace)`` tuples retrieval returns."""
    if isinstance(hit, (tuple, list)):
        return (hit[0] if len(hit) > 0 else None), (hit[2] if len(hit) > 2 else None)
    return hit, None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", 0):
            return value
    return None


def source_label(hit: Any) -> str:
    """A citation the owner can actually open: lesson title plus its location."""
    chunk, trace = _hit_parts(hit)
    meta = getattr(chunk, "metadata", None)
    title = _first(getattr(trace, "title", None), getattr(meta, "title", None)) or "материал без названия"
    label = re.sub(r"\s+", " ", str(title)).strip()
    page = _first(
        getattr(trace, "page_number", None),
        getattr(chunk, "page_number", None),
        getattr(meta, "page_number", None),
    )
    slide = _first(
        getattr(trace, "slide_number", None),
        getattr(chunk, "slide_number", None),
        getattr(meta, "slide_number", None),
    )
    span = _first(getattr(trace, "timestamp_range", None))
    if page:
        label += f", с. {page}"
    elif slide:
        label += f", слайд {slide}"
    if span:
        label += f", {span}"
    return label


def _excerpt(chunk: Any, budget: int) -> str:
    text = re.sub(r"\s+", " ", str(getattr(chunk, "content", "") or "")).strip()
    if len(text) <= budget:
        return text
    head = text[:budget].rsplit(" ", 1)[0].strip()
    return (head or text[:budget].strip()) + "…"


def build_evidence(hits: Any, budget: Optional[int] = None):
    """Renders retrieved chunks as a numbered evidence block plus source labels.

    A long slide deck chunk is trimmed rather than dropped: half a lesson is
    still an answer, a silently empty context is not.
    """
    usable = [hit for hit in (hits or []) if _hit_parts(hit)[0] is not None]
    if not usable:
        return "", []
    budget = budget or max_chars()
    per_hit = max(budget // len(usable), MIN_EXCERPT_CHARS)
    blocks = []
    labels = []
    used = 0
    for hit in usable:
        chunk, _ = _hit_parts(hit)
        excerpt = _excerpt(chunk, per_hit)
        if not excerpt:
            continue
        if blocks and used + len(excerpt) > budget:
            break
        used += len(excerpt)
        label = source_label(hit)
        blocks.append(f"[{len(blocks) + 1}] {label}\n{excerpt}")
        if label not in labels:
            labels.append(label)
    if not blocks:
        return "", []
    return "\n\n".join(blocks), labels


def _default_retriever(query: str, limit: int):
    from src.brain.engines.knowledge_engine import KnowledgeEngine

    return KnowledgeEngine().retrieve(query=query, limit=limit)


def retrieve(
    query: str,
    limit: Optional[int] = None,
    retriever: Optional[Callable[[str, int], Any]] = None,
):
    """Best-effort retrieval: returns ``[]`` instead of raising on any failure."""
    text = (query or "").strip()
    if len(text) < MIN_QUERY_CHARS:
        return []
    call = retriever or _default_retriever
    try:
        return list(call(text, limit or top_k()) or [])
    except Exception:
        log.warning(
            "Grounding retrieval unavailable for %r; answering without it.",
            text[:80], exc_info=True,
        )
        return []


def augment_messages(
    messages: Sequence[Any],
    retriever: Optional[Callable[[str, int], Any]] = None,
):
    """Attaches the owner's own material to a model call.

    Returns ``(messages, sources)``. ``messages`` is the caller's original list
    when nothing was attached, so the result can always go straight to the
    model, and the caller's list is never mutated in place.
    """
    original = list(messages or [])
    if not original or not enabled() or already_grounded(original):
        return original, []
    query = last_user_query(original)
    if not query:
        return original, []
    evidence, labels = build_evidence(retrieve(query, retriever=retriever))
    if not evidence:
        return original, []
    if expects_json(original):
        instruction = (
            "Ниже выдержки из собственных материалов владельца. Опирайся на них как на факты, "
            "но структуру, ключи и типы ответа не меняй."
        )
    else:
        instruction = (
            "Ниже выдержки из собственных материалов владельца — курса и конспектов. "
            "Опирайся на них и приводи конкретику оттуда, а не общие советы. "
            f"Если использовал их, закончи ответ строкой «{SOURCES_PREFIX} …» и перечисли только те "
            "названия из списка ниже, на которые действительно опирался. "
            "Если выдержки не относятся к вопросу — игнорируй их и не ссылайся на них."
        )
    block = f"{EVIDENCE_HEADER}\n{instruction}\n\n{evidence}"
    grounded = list(original)
    insert_at = 0
    for index, message in enumerate(grounded):
        if isinstance(message, dict) and message.get("role") == "system":
            insert_at = index + 1
    grounded.insert(insert_at, {"role": "system", "content": block})
    return grounded, labels
