"""Deterministic tests for price parsing and Russian lexical matching.

Both modules are pure stdlib on purpose: they encode two product rules that
have to hold with no database, no LLM and no vector store behind them.
"""
import pytest

from src.brain.knowledge.text_match import (
    TOPIC_BONUS,
    lexical_score,
    query_topic,
    stem,
    tokenize,
    topic_bonus,
)
from src.brain.services.guided_actions import (
    ACTIONS,
    GuidedActionService,
    MissingActionInput,
)
from src.brain.services.pricing import (
    MAX_REASONABLE_PRICE,
    MIN_REASONABLE_PRICE,
    PriceNotFound,
    format_money,
    parse_base_price,
)


class _FakeProfileEngine:
    def get_profile(self):
        return {"name": "Test", "city": "Samara"}


class _FakeBrain:
    def __init__(self):
        self.profile_engine = _FakeProfileEngine()


def _service():
    """Service without __init__: the pricing branch never touches PromotionEngine."""
    return GuidedActionService.__new__(GuidedActionService)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("15000", 15000),
        ("15 000 \u20bd", 15000),
        ("15\u00a0000 \u20bd", 15000),
        ("15к", 15000),
        ("цена 12 тыс", 12000),
        ("от 8000 руб", 8000),
        ("базовая 15000, премиум 30000", 15000),
        ("900 или 30000 \u20bd", 30000),
    ],
)
def test_parse_base_price_reads_what_the_user_typed(text, expected):
    assert parse_base_price(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "не помню точно",
        "пиши на 89991234567",
        "съёмка 10.09.2026",
        str(MIN_REASONABLE_PRICE - 200),
        str(MAX_REASONABLE_PRICE + 1000),
    ],
)
def test_parse_base_price_refuses_to_guess(text):
    with pytest.raises(PriceNotFound):
        parse_base_price(text)


def test_format_money_uses_a_non_breaking_separator():
    assert format_money(15000) == "15\u00a0000 \u20bd"
    assert format_money(1200000) == "1\u00a0200\u00a0000 \u20bd"


def test_price_list_asks_instead_of_inventing_a_base():
    with pytest.raises(MissingActionInput) as excinfo:
        _service().execute("sales.price", _FakeBrain(), text="хочу прайс на свадьбы")
    assert "15000" in str(excinfo.value)


def test_price_list_is_built_from_the_stated_base():
    result = _service().execute("sales.price", _FakeBrain(), text="базовая 15000 \u20bd")
    data = result["data"]
    assert data["base_price"] == format_money(15000)
    assert [tier["price"] for tier in data["tiers"]] == [
        format_money(10500),
        format_money(15000),
        format_money(24000),
    ]
    # The old branch fell back to 20000 whenever it could not parse a number.
    assert "20 000" not in result["markdown"].replace("\u00a0", " ")


def test_thirty_two_guided_actions_stay_unique():
    ids = [action.action_id for action in ACTIONS]
    assert len(ids) == 32
    assert len(set(ids)) == 32


@pytest.mark.parametrize(
    "forms",
    [
        ("возражение", "возражения", "возражений", "возражением", "возражениями"),
        ("цена", "цены", "цену", "ценой"),
        ("ценность", "ценности"),
        ("клиент", "клиенты", "клиентов", "клиентам"),
        ("пост", "посты", "постов"),
        ("закрывать", "закрываем"),
        ("дорого", "дорогой"),
    ],
)
def test_inflected_forms_share_one_stem(forms):
    assert len({stem(form) for form in forms}) == 1


def test_yo_is_folded():
    assert stem("съёмка") == stem("съемка")


def test_stopwords_and_digits_are_dropped():
    assert tokenize("как и что") == set()
    assert tokenize("урок 2026") == {stem("урок")}


def test_inflected_question_matches_the_lesson():
    # This is the regression: every content word here is inflected differently
    # in the lesson, and the old word-set comparison scored it 0.25.
    score = lexical_score(
        "как закрывать возражение дорого",
        "Скрипт: закрываем возражения \u00abдорого\u00bb через ценность",
    )
    assert score >= 0.99


def test_unrelated_text_scores_zero():
    assert lexical_score("подбор музыки", "договор аренды студии") == 0.0
    assert lexical_score("", "что угодно") == 0.0


def test_exact_phrase_scores_highest():
    assert lexical_score("товарная линейка", "Урок: товарная линейка фотографа") == 0.95


@pytest.mark.parametrize(
    "question,topic",
    [
        ("как отвечать на возражение дорого", "sales"),
        ("идеи для сторис", "content"),
        ("как организовать фотодень", "business"),
    ],
)
def test_questions_route_to_corpus_topics(question, topic):
    assert query_topic(question) == topic


def test_topic_bonus_only_rewards_an_exact_topic_match():
    assert topic_bonus("sales", "sales") == TOPIC_BONUS
    assert topic_bonus("sales", "content") == 0.0
    assert topic_bonus("general", "general") == 0.0
    assert topic_bonus("sales", None) == 0.0
