"""Citations must come from retrieval, not from the model's goodwill.

No database, no vector index and no network: the whole citation path is pure
functions, which is what makes it safe to assert on exact strings here.
"""
from __future__ import annotations

import types

import pytest

from src.brain.knowledge.text_match import (
    LAYER_BONUS,
    layer_bonus,
    layer_is_strict,
    search_stem,
    stem,
)
from src.brain.services import knowledge_grounding as grounding


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
        return list(hits)[:limit]

    return call


# --- the deterministic source line ------------------------------------------


def test_sources_are_rendered_from_retrieval():
    block = grounding.render_sources_block(["Урок 3. Возражения, с. 12", "Урок 8. База"])
    assert block == f"{grounding.SOURCES_PREFIX} Урок 3. Возражения, с. 12; Урок 8. База"


def test_repeated_source_is_listed_once():
    block = grounding.render_sources_block(["Урок 3", "Урок 3", " Урок 3 "])
    assert block == f"{grounding.SOURCES_PREFIX} Урок 3"


def test_nothing_retrieved_means_no_citation():
    assert grounding.render_sources_block([]) == ""
    assert grounding.append_sources("Ответ без материалов.", []) == "Ответ без материалов."


def test_answer_gets_exactly_one_source_line():
    answer = grounding.append_sources("Скрипт ответа клиенту.", ["Урок 3. Возражения, с. 12"])
    assert answer.count(grounding.SOURCES_PREFIX) == 1
    assert answer.endswith("Урок 3. Возражения, с. 12")
    assert answer.startswith("Скрипт ответа клиенту.")


def test_model_written_source_line_is_replaced_not_duplicated():
    raw = "Текст ответа.\n\n\U0001F4DA Источники: Урок, который я придумал"
    answer = grounding.append_sources(raw, ["Урок 3. Возражения, с. 12"])
    assert answer.count(grounding.SOURCES_PREFIX) == 1
    assert "придумал" not in answer
    assert "Урок 3. Возражения, с. 12" in answer


def test_invented_citation_is_removed_when_nothing_was_retrieved():
    raw = "Общий совет.\n\n**\U0001F4DA Источники:** Урок 12. Которого нет"
    assert grounding.append_sources(raw, []) == "Общий совет."


def test_empty_answer_is_left_alone():
    assert grounding.append_sources("", ["Урок 3"]) == ""


def test_owner_can_switch_the_source_line_off(monkeypatch):
    monkeypatch.setenv("BRAIN_SOURCES_IN_ANSWER", "false")
    assert grounding.sources_in_answer() is False
    monkeypatch.setenv("BRAIN_SOURCES_IN_ANSWER", "true")
    assert grounding.sources_in_answer() is True


# --- what grounded the last call --------------------------------------------


def test_last_sources_follow_the_last_call():
    grounding.augment_messages(
        [{"role": "user", "content": "Как отвечать на возражение «дорого»?"}],
        retriever=_retriever(_hit("Через ценность, а не скидку.", "Урок 3. Возражения", 12)),
    )
    assert grounding.last_sources() == ["Урок 3. Возражения, с. 12"]

    grounding.augment_messages(
        [{"role": "user", "content": "Как считать себестоимость съёмки?"}],
        retriever=_retriever(),
    )
    assert grounding.last_sources() == [], "an empty retrieval must clear the citation"


def test_prompt_no_longer_asks_the_model_to_cite():
    grounded, sources = grounding.augment_messages(
        [{"role": "user", "content": "Собери прайс на семейную съёмку"}],
        retriever=_retriever(_hit("Три пакета, средний — целевой.", "Урок 5. Прайс")),
    )
    injected = grounded[0]["content"]
    assert grounding.EVIDENCE_HEADER in injected
    assert grounding.SOURCES_PREFIX not in injected
    assert sources == ["Урок 5. Прайс"]


def test_grounding_retrieves_five_chunks_by_default(monkeypatch):
    monkeypatch.delenv("BRAIN_GROUNDING_TOP_K", raising=False)
    assert grounding.top_k() == 5


# --- one stemmer for the whole project --------------------------------------


def test_search_stem_is_built_on_the_shared_morphology():
    assert search_stem("возражения") == stem("возражения").rstrip("ьъ")
    assert search_stem("клиентами") == search_stem("клиенту")
    assert search_stem("свадьба") == search_stem("свадебная")
    assert search_stem("съёмка") == search_stem("съемка")


def test_retrieval_and_indexing_share_one_stemmer():
    hybrid = pytest.importorskip("src.brain.knowledge.indexing.hybrid_search")
    assert hybrid._stem_word is search_stem, "a second stemmer is how the two sides drift apart"


# --- the layer is a preference, not a gate ----------------------------------


def test_layer_rewards_instead_of_filtering():
    assert layer_bonus("business", "business") == LAYER_BONUS
    assert layer_bonus("business", "professional") == 0.0
    assert layer_bonus(None, "business") == 0.0


def test_strict_layer_is_opt_in(monkeypatch):
    monkeypatch.delenv("BRAIN_LAYER_STRICT", raising=False)
    assert layer_is_strict() is False
    monkeypatch.setenv("BRAIN_LAYER_STRICT", "true")
    assert layer_is_strict() is True


# --- brands the lessons spell in English ------------------------------------


def test_english_brand_names_meet_the_russian_words_the_owner_types():
    """Уроки пишут Instagram, а владелец спрашивает «в инстаграме»."""
    assert stem("Instagram") == stem("инстаграме") == stem("инстаграм")
    assert stem("Instagram") == stem("инста")
    assert search_stem("Instagram") == search_stem("инстаграме")
    assert stem("Reels") == stem("рилсы")
    assert stem("Stories") == stem("сторис")
    assert stem("Telegram") == stem("телеграме") == stem("тг")
    assert stem("ChatGPT") == stem("чатгпт")


def test_brand_folding_is_a_named_table_not_transliteration():
    """Склеивать похожие слова нельзя: «инструменты» — не «инстаграм»."""
    from src.brain.knowledge.text_match import tokenize

    assert stem("инструменты") != stem("инстаграм")
    assert "инстагр" in tokenize("как упаковать профиль в Instagram")
    assert "инструмент" in tokenize("инструменты фотографа")
    assert search_stem("свадьба") == search_stem("свадебная")
