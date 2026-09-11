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
        ("15\u043a", 15000),
        ("\u0446\u0435\u043d\u0430 12 \u0442\u044b\u0441", 12000),
        ("\u043e\u0442 8000 \u0440\u0443\u0431", 8000),
        ("\u0431\u0430\u0437\u043e\u0432\u0430\u044f 15000, \u043f\u0440\u0435\u043c\u0438\u0443\u043c 30000", 15000),
        ("900 \u0438\u043b\u0438 30000 \u20bd", 30000),
    ],
)
def test_parse_base_price_reads_what_the_user_typed(text, expected):
    assert parse_base_price(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\u043d\u0435 \u043f\u043e\u043c\u043d\u044e \u0442\u043e\u0447\u043d\u043e",
        "\u043f\u0438\u0448\u0438 \u043d\u0430 89991234567",
        "\u0441\u044a\u0451\u043c\u043a\u0430 10.09.2026",
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
        _service().execute("sales.price", _FakeBrain(), text="\u0445\u043e\u0447\u0443 \u043f\u0440\u0430\u0439\u0441 \u043d\u0430 \u0441\u0432\u0430\u0434\u044c\u0431\u044b")
    assert "15000" in str(excinfo.value)


def test_price_list_is_built_from_the_stated_base():
    result = _service().execute("sales.price", _FakeBrain(), text="\u0431\u0430\u0437\u043e\u0432\u0430\u044f 15000 \u20bd")
    data = result["data"]
    assert data["base_price"] == format_money(15000)
    assert [tier["price"] for tier in data["tiers"]] == [
        format_money(10500),
        format_money(15000),
        format_money(24000),
    ]
    # The old branch fell back to 20000 whenever it could not parse a number.
    assert "20 000" not in result["markdown"].replace("\u00a0", " ")


def test_guided_action_ids_stay_unique():
    # The old name hard-coded 32 and the registry has outgrown that number
    # twice since, so the test failed for a bookkeeping reason instead of a
    # product one. Uniqueness is the rule worth guarding: a duplicate id is
    # silently swallowed by ACTION_BY_ID and one button stops answering.
    ids = [action.action_id for action in ACTIONS]
    assert len(set(ids)) == len(ids)
    assert len(ids) >= 32


@pytest.mark.parametrize(
    "forms",
    [
        ("\u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u0435", "\u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f", "\u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u0439", "\u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u0435\u043c", "\u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f\u043c\u0438"),
        ("\u0446\u0435\u043d\u0430", "\u0446\u0435\u043d\u044b", "\u0446\u0435\u043d\u0443", "\u0446\u0435\u043d\u043e\u0439"),
        ("\u0446\u0435\u043d\u043d\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u043d\u043e\u0441\u0442\u0438"),
        ("\u043a\u043b\u0438\u0435\u043d\u0442", "\u043a\u043b\u0438\u0435\u043d\u0442\u044b", "\u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432", "\u043a\u043b\u0438\u0435\u043d\u0442\u0430\u043c"),
        ("\u043f\u043e\u0441\u0442", "\u043f\u043e\u0441\u0442\u044b", "\u043f\u043e\u0441\u0442\u043e\u0432"),
        ("\u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0442\u044c", "\u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0435\u043c"),
        ("\u0434\u043e\u0440\u043e\u0433\u043e", "\u0434\u043e\u0440\u043e\u0433\u043e\u0439"),
    ],
)
def test_inflected_forms_share_one_stem(forms):
    assert len({stem(form) for form in forms}) == 1


def test_yo_is_folded():
    assert stem("\u0441\u044a\u0451\u043c\u043a\u0430") == stem("\u0441\u044a\u0435\u043c\u043a\u0430")


def test_stopwords_and_digits_are_dropped():
    assert tokenize("\u043a\u0430\u043a \u0438 \u0447\u0442\u043e") == set()
    assert tokenize("\u0443\u0440\u043e\u043a 2026") == {stem("\u0443\u0440\u043e\u043a")}


def test_inflected_question_matches_the_lesson():
    # This is the regression: every content word here is inflected differently
    # in the lesson, and the old word-set comparison scored it 0.25.
    score = lexical_score(
        "\u043a\u0430\u043a \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0442\u044c \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u0435 \u0434\u043e\u0440\u043e\u0433\u043e",
        "\u0421\u043a\u0440\u0438\u043f\u0442: \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0435\u043c \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f \u00ab\u0434\u043e\u0440\u043e\u0433\u043e\u00bb \u0447\u0435\u0440\u0435\u0437 \u0446\u0435\u043d\u043d\u043e\u0441\u0442\u044c",
    )
    assert score >= 0.99


def test_unrelated_text_scores_zero():
    assert lexical_score("\u043f\u043e\u0434\u0431\u043e\u0440 \u043c\u0443\u0437\u044b\u043a\u0438", "\u0434\u043e\u0433\u043e\u0432\u043e\u0440 \u0430\u0440\u0435\u043d\u0434\u044b \u0441\u0442\u0443\u0434\u0438\u0438") == 0.0
    assert lexical_score("", "\u0447\u0442\u043e \u0443\u0433\u043e\u0434\u043d\u043e") == 0.0


def test_exact_phrase_scores_highest():
    assert lexical_score("\u0442\u043e\u0432\u0430\u0440\u043d\u0430\u044f \u043b\u0438\u043d\u0435\u0439\u043a\u0430", "\u0423\u0440\u043e\u043a: \u0442\u043e\u0432\u0430\u0440\u043d\u0430\u044f \u043b\u0438\u043d\u0435\u0439\u043a\u0430 \u0444\u043e\u0442\u043e\u0433\u0440\u0430\u0444\u0430") == 0.95


@pytest.mark.parametrize(
    "question,topic",
    [
        ("\u043a\u0430\u043a \u043e\u0442\u0432\u0435\u0447\u0430\u0442\u044c \u043d\u0430 \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u0435 \u0434\u043e\u0440\u043e\u0433\u043e", "sales"),
        ("\u0438\u0434\u0435\u0438 \u0434\u043b\u044f \u0441\u0442\u043e\u0440\u0438\u0441", "content"),
        ("\u043a\u0430\u043a \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u043e\u0432\u0430\u0442\u044c \u0444\u043e\u0442\u043e\u0434\u0435\u043d\u044c", "business"),
    ],
)
def test_questions_route_to_corpus_topics(question, topic):
    assert query_topic(question) == topic


def test_topic_bonus_only_rewards_an_exact_topic_match():
    assert topic_bonus("sales", "sales") == TOPIC_BONUS
    assert topic_bonus("sales", "content") == 0.0
    assert topic_bonus("general", "general") == 0.0
    assert topic_bonus("sales", None) == 0.0
