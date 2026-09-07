"""
Style Benchmark for Personal AI Brain.
Evaluates adherence to photographer style guidelines, tone,
and strict rejection of forbidden stop-words.
"""
import pytest
from src.brain.services.brain_service import BrainService
from src.brain.models.style import StyleProfile, ExemplarCategory

def test_style_adherence_and_forbidden_words():
    brain = BrainService()
    
    style_profile = StyleProfile(
        tone="Искренний, кинематографичный, сдержанный",
        forbidden_expressions=["красоточка", "волшебство", "скидочка", "налетай", "уникальный прайс"]
    )
    
    # 1. Test evaluation on a generic bad AI text
    generic_bad_text = "Привет, красоточка! Лови волшебство на моих съемках, успей налетай на скидочку!"
    bad_benchmark = brain.style_engine.evaluate_benchmark(
        generic_bad_text,
        style_profile,
        forbidden_words=style_profile.forbidden_expressions
    )
    
    # The benchmark must catch the violations
    assert bad_benchmark.forbidden_violations > 0
    assert bad_benchmark.overall_score < 0.7
    
    # 2. Test evaluation on clean, stylish photographer text
    good_text = (
        "Свет падает сквозь жалюзи под острым углом. В кадре нет заученных поз — только живой взгляд, "
        "глубокая полутень и естественное дыхание. Мы сохраняем момент, который не устареет. "
        "Напишите мне в директ, чтобы подобрать удобную дату для съемки."
    )
    good_benchmark = brain.style_engine.evaluate_benchmark(
        good_text,
        style_profile,
        forbidden_words=style_profile.forbidden_expressions
    )
    
    assert good_benchmark.forbidden_violations == 0
    assert good_benchmark.overall_score > bad_benchmark.overall_score
    assert good_benchmark.overall_score >= 0.7
