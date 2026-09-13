"""Grounding must reach every model call — and must never break one.

These tests deliberately use fake retrieval results: the point is that the
evidence path works without a database, a vector index or a network, because
those are exactly the pieces that fail first in production.
"""
from __future__ import annotations

import types

from src.brain.services import knowledge_grounding as grounding
from src.brain.services.llm_provider import LLMProvider


def _hit(content: str, title: str, page=None, score: float = 0.7):
    chunk = types.SimpleNamespace(
        content=content,
        page_number=page,
        slide_number=None,
        metadata=types.SimpleNamespace(title=title, page_number=page, slide_number=None),
    )
    trace = types.SimpleNamespace(
        title=title, page_number=page, slide_number=None, timestamp_range=None
    )
    return (chunk, score, trace)


def _retriever(*hits):
    def call(query, limit):
        assert query.strip(), "grounding must not retrieve on an empty question"
        return list(hits)[:limit]

    return call


def test_engine_prompt_receives_course_material():
    messages = [
        {"role": "system", "content": "Ты — маркетолог фотографа."},
        {"role": "user", "content": "Как отвечать клиенту на возражение «дорого»?"},
    ]
    grounded, sources = grounding.augment_messages(
        messages,
        retriever=_retriever(
            _hit(
                "Возражение «дорого» закрывается через ценность и состав пакета, а не скидку.",
                "Урок 3. Возражения",
                12,
            )
        ),
    )
    assert len(messages) == 2, "the caller's list must not be mutated"
    assert len(grounded) == 3
    injected = grounded[1]["content"]
    assert grounding.EVIDENCE_HEADER in injected
    assert "через ценность" in injected
    assert "Урок 3. Возражения, с. 12" in injected
    assert sources == ["Урок 3. Возражения, с. 12"]
    assert grounded[-1] == messages[-1], "the question stays the last message"


def test_strict_json_callers_keep_their_contract():
    messages = [
        {"role": "system", "content": "Верни строго JSON с теми же ключами и типами."},
        {"role": "user", "content": "Собери план продвижения на месяц"},
    ]
    grounded, sources = grounding.augment_messages(
        messages,
        retriever=_retriever(
            _hit("Повторные клиенты дают сарафан дешевле любой рекламы.", "Урок 8. Клиентская база")
        ),
    )
    injected = grounded[1]["content"]
    assert grounding.EVIDENCE_HEADER in injected
    assert grounding.SOURCES_PREFIX not in injected, "a JSON contract must not be asked for prose"
    assert sources == ["Урок 8. Клиентская база"]


def test_process_chat_prompts_are_not_grounded_twice():
    messages = [
        {
            "role": "system",
            "content": f"### {grounding.UPSTREAM_KNOWLEDGE_MARKER}:\n--- Источник: Урок 1 ---",
        },
        {"role": "user", "content": "Что выложить в сторис на этой неделе?"},
    ]
    grounded, sources = grounding.augment_messages(
        messages, retriever=_retriever(_hit("текст урока", "Урок 1"))
    )
    assert grounded == messages
    assert sources == []


def test_multimodal_question_is_still_retrievable():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Разбери свет на этом кадре"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        }
    ]
    grounded, sources = grounding.augment_messages(
        messages, retriever=_retriever(_hit("Мягкий свет строится от большого источника.", "Урок 4. Свет"))
    )
    assert sources == ["Урок 4. Свет"]
    assert grounding.EVIDENCE_HEADER in grounded[0]["content"]


def test_retrieval_failure_degrades_instead_of_raising():
    def broken(query, limit):
        raise RuntimeError("vector index is cold")

    messages = [{"role": "user", "content": "Как упаковать профиль фотографа?"}]
    grounded, sources = grounding.augment_messages(messages, retriever=broken)
    assert grounded == messages
    assert sources == []


def test_empty_index_leaves_the_prompt_alone():
    messages = [{"role": "user", "content": "Как считать себестоимость съёмки?"}]
    grounded, sources = grounding.augment_messages(messages, retriever=_retriever())
    assert grounded == messages
    assert sources == []


def test_small_talk_does_not_trigger_retrieval():
    calls = []

    def counting(query, limit):
        calls.append(query)
        return []

    grounded, sources = grounding.augment_messages(
        [{"role": "user", "content": "ок"}], retriever=counting
    )
    assert calls == [], "a two-letter turn must not cost a retrieval"
    assert sources == []
    assert len(grounded) == 1


def test_evidence_stays_inside_its_budget(monkeypatch):
    monkeypatch.setenv("BRAIN_GROUNDING_MAX_CHARS", "300")
    long_text = "смысл урока " * 200
    grounded, sources = grounding.augment_messages(
        [{"role": "user", "content": "Как продавать фотодень?"}],
        retriever=_retriever(
            _hit(long_text, "Урок 6. Фотодень"), _hit(long_text, "Урок 7. Продажи")
        ),
    )
    injected = grounded[0]["content"]
    assert "…" in injected, "long chunks are trimmed, not dropped"
    assert len(injected) < 1600
    assert sources


def test_owner_can_switch_grounding_off(monkeypatch):
    monkeypatch.setenv("BRAIN_GROUNDING_ENABLED", "false")
    messages = [{"role": "user", "content": "Как отвечать на «дорого»?"}]
    grounded, sources = grounding.augment_messages(
        messages, retriever=_retriever(_hit("текст урока про возражения", "Урок 3"))
    )
    assert grounded == messages
    assert sources == []


def test_provider_starts_with_no_claimed_sources():
    assert LLMProvider().last_grounding_sources == []
