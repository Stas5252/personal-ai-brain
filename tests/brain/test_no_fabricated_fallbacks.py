"""Fallback mode must not publish invented business facts as the owner."""
from src.brain.engines.content_engine import ContentEngine
from src.brain.engines.voice_engine import VoiceEngine


FORBIDDEN_CLAIMS = (
    "ровно 2 свободных слота",
    "2 часа искала",
    "я никогда не видела себя такой",
    "90% моих героев",
    "90% клиентского стресса",
    "самый конвертирующий контент",
)


def test_content_fallback_contains_no_fabricated_claims():
    engine = ContentEngine()
    stories = engine.generate_nine_step_stories_arc("подготовка", use_llm=False)
    reels = engine.generate_introvert_reels_script("страх камеры", use_llm=False)
    rendered = (stories["formatted_script"] + "\n" + reels["formatted_script"]).casefold()
    assert all(claim not in rendered for claim in FORBIDDEN_CLAIMS)
    assert "проверь" in rendered or "подтверж" in rendered


def test_voice_fallback_distinguishes_missing_facts_from_results():
    result = VoiceEngine().process_voice_transcript(
        "Сегодня думала о подготовке к съёмке", use_llm=False
    )
    rendered = str(result).casefold()
    assert all(claim not in rendered for claim in FORBIDDEN_CLAIMS)
    assert "итог в транскрипте не указан" in rendered
