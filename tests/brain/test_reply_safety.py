"""Offline checks for reply delivery and the memory admission policy.

No network and no database: only pure functions are exercised, so these tests
run anywhere in under a second.
"""
from datetime import datetime, timedelta, timezone

from src.brain.channels.telegram_media import sanitize_markdown, split_message
from src.brain.engines.memory_engine import MemoryEngine, recency_score
from src.brain.models.memory import AdmissionAction, MemoryType

TELEGRAM_LIMIT = 4096


def test_long_answer_is_split_below_telegram_limit():
    text = "\n\n".join(f"Абзац {i} про свет, композицию и работу с моделью. " * 6 for i in range(120))
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= TELEGRAM_LIMIT for chunk in chunks)


def test_short_answer_stays_one_message():
    assert split_message("Готово.") == ["Готово."]


def test_split_prefers_paragraph_break():
    text = "A" * 3400 + "\n\n" + "B" * 500
    chunks = split_message(text)
    assert chunks[0].endswith("A")
    assert chunks[1].startswith("B")


def test_unclosed_code_fence_is_closed():
    assert sanitize_markdown("Вот промпт:\n```\nsoft window light").endswith("```")


def test_odd_asterisk_is_removed():
    assert "*" not in sanitize_markdown("*Прайс на съёмку")


def test_balanced_markdown_is_untouched():
    text = "*Прайс* и _детали_"
    assert sanitize_markdown(text) == text


def test_task_request_is_not_stored_as_memory():
    decision = MemoryEngine().evaluate_admission("Напиши пост про осеннюю съёмку")
    assert decision.action == AdmissionAction.IGNORE


def test_preference_is_saved_with_high_importance():
    decision = MemoryEngine().evaluate_admission("Не используй слово трансформация в текстах")
    assert decision.action == AdmissionAction.SAVE
    assert decision.memory_type == MemoryType.PREFERENCE
    assert decision.importance >= 0.9


def test_first_person_fact_is_saved():
    decision = MemoryEngine().evaluate_admission("Я снимаю семейные съёмки в Самаре")
    assert decision.action == AdmissionAction.SAVE


def test_unrelated_sentence_is_ignored():
    decision = MemoryEngine().evaluate_admission("Завтра по прогнозу дождь и сильный ветер")
    assert decision.action == AdmissionAction.IGNORE


def test_recency_halves_after_thirty_days():
    now = datetime.now(timezone.utc)
    assert recency_score(now.isoformat()) > 0.99
    assert 0.45 < recency_score((now - timedelta(days=30)).isoformat()) < 0.55
    assert 0.20 < recency_score((now - timedelta(days=60)).isoformat()) < 0.30


def test_recency_accepts_naive_timestamp():
    naive = (datetime.now() - timedelta(days=1)).isoformat()
    assert 0.0 <= recency_score(naive) <= 1.0
