"""Offline tests for the voice learning loop.

Everything here is a pure function: no database, no network, no model. The
point of these tests is that a rejected answer must change something real, and
that the change is derived from her words instead of guessed.
"""
from types import SimpleNamespace

from src.brain.engines.style_engine import (
    MAX_CARD_CHARS,
    build_voice_card,
    classify_closing,
    classify_opening,
    contrast_terms,
    extract_explicit_bans,
    measure_voice,
)


# -- explicit bans ----------------------------------------------------------


def test_quoted_words_become_bans():
    bans = extract_explicit_bans('так не пиши, убери "дорогие мои"')
    assert "дорогие мои" in bans


def test_russian_quotes_are_understood():
    bans = extract_explicit_bans("так не пиши, без слова «уникальный»")
    assert "уникальный" in bans


def test_a_verdict_without_words_bans_nothing():
    """«так не пиши» is a verdict, not a stop word: nothing may be invented."""
    assert extract_explicit_bans("так не пиши") == []
    assert extract_explicit_bans("") == []
    assert extract_explicit_bans(None) == []


def test_words_after_the_marker_are_taken_without_quotes():
    bans = extract_explicit_bans("убери волшебство момента, звучит не как я")
    assert bans and bans[0].startswith("волшебство")


def test_bans_are_lowercased_deduplicated_and_capped():
    bans = extract_explicit_bans('убери "Клише", "клише", "штамп", "вода", "пафос", "ещё"')
    assert bans.count("клише") == 1
    assert len(bans) <= 5


# -- derived bans -----------------------------------------------------------


def test_contrast_finds_the_cliche_that_is_not_hers():
    bad = ["Дорогие мои подписчики, спешу поделиться волшебством момента."]
    good = [
        "Съёмка получилась тихой и тёплой. Люблю такие кадры.",
        "Приходите в студию, там мягкий свет и много воздуха.",
    ]
    terms = contrast_terms(bad, good, limit=3)
    assert any("дорогие" in term for term in terms)


def test_contrast_never_bans_a_word_she_uses_herself():
    bad = ["Съёмка получилась волшебной и невероятной."]
    good = ["Съёмка получилась тихой. Съёмка это про доверие."]
    terms = contrast_terms(bad, good, limit=3)
    assert all("съёмка" not in term for term in terms)


def test_contrast_on_empty_input_is_empty():
    assert contrast_terms([], [], limit=3) == []
    assert contrast_terms(None, None, limit=3) == []


# -- third voice layer ------------------------------------------------------


def test_opening_and_closing_are_classified():
    assert classify_opening("А вы замечали, как свет меняет лицо?") == "вопросом"
    assert classify_opening("3 вещи, которые я поняла за год работы со светом.") == "цифрой"
    assert classify_opening("Люблю утро.") == "короткой фразой"
    assert classify_closing("Напиши мне в директ, и подберём дату съёмки.") == "призывом"
    assert classify_closing("А что для вас важнее в кадре?") == "вопросом"


def test_measure_voice_reports_how_she_explains():
    texts = [
        "Свет решает всё. Например, окно слева даёт мягкую тень. Напиши в директ.",
        "Поза важнее одежды. Например, разверни плечи. Запись открыта.",
        "Фон не должен спорить с лицом. Например, убери яркое пятно. Пиши в директ.",
    ]
    voice = measure_voice(texts)
    assert voice["learned"] is True
    assert "на примере" in voice["explanation_habit"]
    assert voice["opening_habit"]
    assert voice["closing_habit"]


def test_measure_voice_on_nothing_invents_nothing():
    voice = measure_voice([])
    assert voice["learned"] is False
    assert voice["opening_habit"] == ""
    assert voice["closing_habit"] == ""
    assert voice["explanation_habit"] == ""


def test_measure_voice_keeps_the_old_keys():
    """The new layer is added, not swapped in: existing callers keep working."""
    voice = measure_voice(["Короткий текст про свет и тепло в кадре."])
    for key in (
        "exemplar_count",
        "sentence_length_avg",
        "emoji_frequency",
        "paragraph_structure",
        "punctuation_habits",
        "signature_words",
        "signature_phrases",
        "cta_rate",
    ):
        assert key in voice


# -- identity card ----------------------------------------------------------


def fake_profile(**kwargs):
    data = {
        "identity": "Вика",
        "niche": "семейная съёмка",
        "city": "Саратов",
        "tone": "тёплый, без штампов",
        "forbidden_words": ["дорогие мои"],
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_card_names_the_author_and_the_stop_words():
    card = build_voice_card(fake_profile(), {"learned": False})
    assert "Вика" in card
    assert "семейная съёмка" in card
    assert "дорогие мои" in card


def test_card_stays_short_enough_to_reinject_every_turn():
    card = build_voice_card(
        fake_profile(forbidden_words=[f"клише-{n}" for n in range(40)]),
        {
            "learned": True,
            "sentence_length_avg": 11.0,
            "emoji_frequency": "Редко, ~1.0 на текст",
            "opening_habit": "вопросом",
            "closing_habit": "призывом",
            "explanation_habit": "на примере",
        },
    )
    assert len(card) <= MAX_CARD_CHARS


def test_card_includes_the_measured_habits_once_learned():
    card = build_voice_card(
        fake_profile(),
        {
            "learned": True,
            "sentence_length_avg": 11.0,
            "emoji_frequency": "Редко, ~1.0 на текст",
            "opening_habit": "вопросом",
            "closing_habit": "призывом",
            "explanation_habit": "на примере",
        },
    )
    assert "открываю вопросом" in card
    assert "закрываю призывом" in card


def test_card_is_empty_without_a_profile():
    """No profile means no card at all, instead of a card about nobody."""
    assert build_voice_card(None, {}) == ""
    assert build_voice_card(SimpleNamespace(), {"learned": False}) == ""


def test_card_survives_a_profile_without_voice_data():
    card = build_voice_card(fake_profile(forbidden_words=[]), None)
    assert "Вика" in card
