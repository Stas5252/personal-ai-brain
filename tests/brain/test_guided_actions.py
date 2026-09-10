from types import SimpleNamespace

import pytest

from src.brain.channels.bot_config import ACTIONS as MENU_ACTIONS
from src.brain.engines.promotion_engine import PromotionEngine
from src.brain.services.guided_actions import ACTION_BY_ID, ACTION_BY_LABEL, ACTIONS, GuidedActionService, MissingActionInput


class FakeBrain:
    def __init__(self):
        self.profile_engine = SimpleNamespace(get_profile=lambda: SimpleNamespace(niche="\u0441\u0435\u043c\u0435\u0439\u043d\u044b\u0439 \u0444\u043e\u0442\u043e\u0433\u0440\u0430\u0444", city="\u0421\u0430\u043c\u0430\u0440\u0430", audience="\u0441\u0435\u043c\u044c\u0438"))
        self.content_engine = SimpleNamespace(
            build_content_sprint_plan=lambda **kw: {"days": [{"day": i + 1} for i in range(kw["days"])]},
            generate_nine_step_stories_arc=lambda text, **kw: {"topic": text, "steps": list(range(1, 10))},
        )
        self.proactive_engine = SimpleNamespace(generate_daily_plan=lambda **kw: {"priorities": ["CRM", "\u0441\u044a\u0451\u043c\u043a\u0430", "\u043a\u043e\u043d\u0442\u0435\u043d\u0442"]})

    def process_chat(self, **kwargs):
        return {"status_code": 200, "response": "\u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u0442\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442"}


def test_registry_covers_every_menu_button():
    # bot_config.ACTIONS is a flat {label: prompt} dict, so the labels are its
    # keys. Iterating the values would iterate the characters of the prompts.
    assert set(MENU_ACTIONS) == set(ACTION_BY_LABEL)
    assert len(ACTION_BY_ID) == len(ACTION_BY_LABEL) == len(ACTIONS) == 37


def test_reference_buttons_are_reachable_and_declare_their_input():
    # A vault button missing from the menu is dead code: the runner only
    # dispatches text it can find in ACTION_BY_LABEL.
    for action_id in ("shoot.reference", "shoot.character", "shoot.refset"):
        action = ACTION_BY_ID[action_id]
        assert action.label in MENU_ACTIONS
        assert ACTION_BY_LABEL[action.label].action_id == action_id
    assert ACTION_BY_ID["shoot.reference"].image
    assert ACTION_BY_ID["shoot.reference"].requires_input
    assert ACTION_BY_ID["shoot.character"].requires_input
    # The set is shown on tap; asking a question first would be a dead end.
    assert not ACTION_BY_ID["shoot.refset"].requires_input


def test_input_contract_pauses_underspecified_action():
    with pytest.raises(MissingActionInput, match="\u043f\u0435\u0440\u0435\u043f\u0438\u0441\u043a\u0438"):
        GuidedActionService().execute("sales.dialogue", FakeBrain(), use_llm=False)


def test_week_plan_is_dispatched_to_specialized_engine():
    result = GuidedActionService().execute("content.week", FakeBrain(), use_llm=False)
    assert len(result["data"]["days"]) == 7


def test_price_draft_does_not_invent_delivery_or_booking_terms():
    result = GuidedActionService().execute("sales.price", FakeBrain(), text="\u0411\u0430\u0437\u0430 20 000 \u0440\u0443\u0431\u043b\u0435\u0439", use_llm=False)
    serialized = str(result["data"]).lower()
    assert "\u0442\u043e\u043b\u044c\u043a\u043e \u0438\u0437 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430" in serialized
    assert "\u0440\u043e\u0432\u043d\u043e 2 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0445" not in serialized
    assert "\u0431\u0440\u043e\u043d\u044c \u0431\u0435\u0437 \u043f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u044b" not in serialized


def test_promotion_is_structured_and_evidence_scoped():
    engine = PromotionEngine()
    strategy = engine.build_monthly_strategy(use_llm=False)
    assert len(strategy["weekly_sprints"]) == 4
    assert "live-\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438" in strategy["measurement_note"]
    analysis = engine.analyze_competitors("A: \u043f\u043e\u0440\u0442\u0444\u043e\u043b\u0438\u043e\nB: \u0435\u0441\u0442\u044c CTA", use_llm=False)
    assert analysis["evidence_scope"].startswith("\u0422\u043e\u043b\u044c\u043a\u043e \u043c\u0430\u0442\u0435\u0440\u0438\u0430\u043b\u044b \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f")


def test_locked_facts_survive_a_hallucinating_model():
    engine = PromotionEngine()
    template = engine.build_monthly_strategy(use_llm=False)
    merged = engine._merge(
        template,
        {
            "positioning": "\u0422\u043e\u0447\u043d\u0435\u0435 \u0438 \u0436\u0438\u0432\u0435\u0435",
            "measurement_note": "\u0423 \u043d\u0430\u0441 \u0435\u0441\u0442\u044c live-\u0434\u0430\u0448\u0431\u043e\u0440\u0434 \u043e\u0445\u0432\u0430\u0442\u043e\u0432",
            "weekly_sprints": ["\u043d\u0435\u0434\u0435\u043b\u044f 1"],
            "invented_key": "12 000 \u043f\u043e\u0434\u043f\u0438\u0441\u0447\u0438\u043a\u043e\u0432 \u0437\u0430 \u043c\u0435\u0441\u044f\u0446",
        },
    )
    assert merged["positioning"] == "\u0422\u043e\u0447\u043d\u0435\u0435 \u0438 \u0436\u0438\u0432\u0435\u0435"
    assert "live-\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438" in merged["measurement_note"]
    assert len(merged["weekly_sprints"]) == 4
    assert "invented_key" not in merged
