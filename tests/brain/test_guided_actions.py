from types import SimpleNamespace

import pytest

from src.brain.channels.bot_config import ACTIONS as MENU_ACTIONS
from src.brain.engines.promotion_engine import PromotionEngine
from src.brain.services.guided_actions import ACTION_BY_ID, ACTION_BY_LABEL, ACTIONS, GuidedActionService, MissingActionInput


class FakeBrain:
    def __init__(self):
        self.profile_engine = SimpleNamespace(get_profile=lambda: SimpleNamespace(niche="семейный фотограф", city="Самара", audience="семьи"))
        self.content_engine = SimpleNamespace(
            build_content_sprint_plan=lambda **kw: {"days": [{"day": i + 1} for i in range(kw["days"])]},
            generate_nine_step_stories_arc=lambda text, **kw: {"topic": text, "steps": list(range(1, 10))},
        )
        self.proactive_engine = SimpleNamespace(generate_daily_plan=lambda **kw: {"priorities": ["CRM", "съёмка", "контент"]})

    def process_chat(self, **kwargs):
        return {"status_code": 200, "response": "структурированный тестовый результат"}


def test_registry_covers_every_menu_button():
    # bot_config.ACTIONS is a flat {label: prompt} dict, so the labels are its
    # keys. Iterating the values would iterate the characters of the prompts.
    assert set(MENU_ACTIONS) == set(ACTION_BY_LABEL)
    assert len(ACTION_BY_ID) == len(ACTION_BY_LABEL) == len(ACTIONS) == 34


def test_input_contract_pauses_underspecified_action():
    with pytest.raises(MissingActionInput, match="переписки"):
        GuidedActionService().execute("sales.dialogue", FakeBrain(), use_llm=False)


def test_week_plan_is_dispatched_to_specialized_engine():
    result = GuidedActionService().execute("content.week", FakeBrain(), use_llm=False)
    assert len(result["data"]["days"]) == 7


def test_price_draft_does_not_invent_delivery_or_booking_terms():
    result = GuidedActionService().execute("sales.price", FakeBrain(), text="База 20 000 рублей", use_llm=False)
    serialized = str(result["data"]).lower()
    assert "только из договора" in serialized
    assert "ровно 2 свободных" not in serialized
    assert "бронь без предоплаты" not in serialized


def test_promotion_is_structured_and_evidence_scoped():
    engine = PromotionEngine()
    strategy = engine.build_monthly_strategy(use_llm=False)
    assert len(strategy["weekly_sprints"]) == 4
    assert "live-аналитики" in strategy["measurement_note"]
    analysis = engine.analyze_competitors("A: портфолио\nB: есть CTA", use_llm=False)
    assert analysis["evidence_scope"].startswith("Только материалы пользователя")


def test_locked_facts_survive_a_hallucinating_model():
    engine = PromotionEngine()
    template = engine.build_monthly_strategy(use_llm=False)
    merged = engine._merge(
        template,
        {
            "positioning": "Точнее и живее",
            "measurement_note": "У нас есть live-дашборд охватов",
            "weekly_sprints": ["неделя 1"],
            "invented_key": "12 000 подписчиков за месяц",
        },
    )
    assert merged["positioning"] == "Точнее и живее"
    assert "live-аналитики" in merged["measurement_note"]
    assert len(merged["weekly_sprints"]) == 4
    assert "invented_key" not in merged
