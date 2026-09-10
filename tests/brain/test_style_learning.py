"""Офлайн-тесты обучения авторскому голосу: без БД, без сети, без ключей."""

from src.brain.engines.style_engine import (
    MIN_EXEMPLARS_FOR_VOICE,
    StyleEngine,
    measure_voice,
)
from src.brain.models.style import ExemplarCategory, StyleProfile

SAMPLE_1 = """Съёмка на рассвете — это всегда риск.
Туман может не встать, а модель может проспать.

Но когда всё сходится, кадр звучит. Напиши в директ, если хочешь так же."""

SAMPLE_2 = """Я не люблю постановку. Люблю живое.
Когда девушка смеётся, потому что ей правда смешно.

Свет, ветер, движение — и всё. Места на октябрь ещё есть."""

SAMPLE_3 = """Пять лет назад я снимала на кит-объектив.
И кадры были живые.

Техника не делает кадр. Делает внимание. Напиши, если согласна."""

SAMPLES = [SAMPLE_1, SAMPLE_2, SAMPLE_3]


def test_empty_vault_is_not_learned():
    voice = measure_voice([])
    assert voice["exemplar_count"] == 0
    assert voice["learned"] is False
    assert voice["signature_words"] == []
    assert voice["sentence_length_avg"] == 0.0


def test_three_texts_make_voice_learned():
    voice = measure_voice(SAMPLES)
    assert voice["exemplar_count"] == len(SAMPLES)
    assert len(SAMPLES) >= MIN_EXEMPLARS_FOR_VOICE
    assert voice["learned"] is True


def test_two_texts_are_not_enough():
    voice = measure_voice(SAMPLES[:2])
    assert voice["learned"] is False


def test_sentence_length_is_measured():
    voice = measure_voice(SAMPLES)
    assert 3.0 < voice["sentence_length_avg"] < 20.0


def test_signature_words_skip_stopwords_and_short_words():
    voice = measure_voice(SAMPLES)
    for word in voice["signature_words"]:
        assert len(word) >= 4
        assert word not in {"это", "если", "когда", "может"}


def test_cta_rate_detected():
    voice = measure_voice(SAMPLES)
    assert voice["cta_rate"] == 1.0


def test_texts_without_cta_report_zero_rate():
    voice = measure_voice(["Просто мысли вслух о свете и тумане на рассвете."] * 3)
    assert voice["cta_rate"] == 0.0


def test_emoji_free_texts_reported_honestly():
    voice = measure_voice(SAMPLES)
    assert voice["emoji_per_text"] == 0.0
    assert "без эмодзи" in voice["emoji_frequency"].lower()


def test_detect_category_reels():
    assert StyleEngine.detect_category("Сценарий для рилс: хук в первые секунды") == (
        ExemplarCategory.REELS_SCRIPT
    )


def test_detect_category_offer():
    assert StyleEngine.detect_category("Прайс на осень: пакет ЛАЙТ 12000") == (
        ExemplarCategory.OFFER
    )


def test_detect_category_defaults_to_post():
    assert StyleEngine.detect_category(SAMPLE_1) == ExemplarCategory.POST


def test_derive_profile_uses_measurements():
    voice = measure_voice(SAMPLES)
    base = StyleProfile()
    derived = StyleEngine().derive_profile(base, voice)
    assert derived.sentence_length_avg == voice["sentence_length_avg"]
    assert derived.emoji_frequency == voice["emoji_frequency"]
    assert derived.vocabulary
    # базовый профиль не мутируется
    assert base.sentence_length_avg == 12.0


def test_derive_profile_keeps_base_when_not_learned():
    voice = measure_voice(SAMPLES[:1])
    base = StyleProfile()
    derived = StyleEngine().derive_profile(base, voice)
    assert derived.sentence_length_avg == base.sentence_length_avg
    assert derived.emoji_frequency == base.emoji_frequency


def test_learn_from_text_rejects_short_reply():
    assert StyleEngine().learn_from_text("ок, давай") is None


def test_title_is_trimmed_to_first_line():
    title = StyleEngine._title_from(SAMPLE_1)
    assert title.startswith("Съёмка на рассвете")
    assert "\n" not in title


def test_benchmark_penalises_forbidden_words():
    engine = StyleEngine()
    voice = measure_voice([])
    profile = StyleProfile(forbidden_expressions=["трансформация"])
    clean = engine.evaluate_benchmark(
        "Свет мягкий, кадр живой. Напиши в директ.", profile, voice=voice
    )
    dirty = engine.evaluate_benchmark(
        "Настоящая трансформация ждёт тебя. Напиши в директ.", profile, voice=voice
    )
    assert clean.forbidden_violations == 0
    assert dirty.forbidden_violations == 1
    assert dirty.overall_score < clean.overall_score
