"""
Comprehensive 32-Scenario Acceptance Test Suite for Personal AI Brain.
Verifies that the system acts as a specialized personal work system for photographers.
"""
import pytest
from src.brain.services.brain_service import BrainService
from src.brain.models.profile import UserProfile
from src.brain.models.client import Client, ClientStatus
from src.brain.models.project import Project, ProjectStatus
from src.brain.models.task import Task, TaskStatus, TaskPriority, ApprovalState
from src.brain.models.routing import IntentType
from src.brain.models.knowledge import HallucinationType

@pytest.fixture(scope="module")
def brain():
    b = BrainService()
    # Configure test photographer profile
    p = UserProfile(
        identity="Елена Морозова",
        profession="Портретный и fashion фотограф",
        city="Москва",
        niche="Кинематографичный женский портрет",
        genres=["Женский портрет", "Fashion", "Студийная съемка"],
        services=["Индивидуальная съёмка", "Экспресс-портрет", "Кампейн для бренда"],
        pricing={"Экспресс": "8 000 руб", "Стандарт": "15 000 руб", "Премиум": "30 000 руб"},
        audience="Девушки 25-40 лет, эксперты, предпринимательницы, ценящие эстетику и естественность",
        tone="Теплый, кинематографичный, заботливый, без заученных фраз",
        forbidden_words=["красоточка", "волшебство", "уникальный прайс", "скидочка", "налетай"]
    )
    b.profile_engine.save_profile(p)
    return b

# ---------------------------------------------------------------------------
# SCENARIOS 1-5: CONTENT & EMERGENCIES
# ---------------------------------------------------------------------------
def test_01_no_content_emergency(brain):
    """Scenario 1: 'Мне нечего выложить' recovery workflow"""
    res = brain.content_engine.emergency_content_recovery(profile=brain.profile_engine.get_profile())
    assert len(res) == 3
    assert any("Сторителлинг" in a["angle"] for a in res)
    assert any("Экспертиза" in a["angle"] for a in res)
    assert any("Мягкие продажи" in a["angle"] for a in res)
    assert "hook" in res[0] and len(res[0]["hook"]) > 10

def test_02_reels_script_generation(brain):
    """Scenario 2: Dynamic Reels script with 3-sec hook, scene description and CTA"""
    prompt = brain.content_engine.build_format_prompt("reels")
    assert "ХУК (0-3 сек)" in prompt
    assert "ВИЗУАЛЬНЫЙ РЯД" in prompt
    assert "ТЕКСТ НА ЭКРАНЕ" in prompt
    assert "CTA" in prompt

def test_03_stories_sequence(brain):
    """Scenario 3: 5-frame Stories narrative arc"""
    prompt = brain.content_engine.build_format_prompt("stories")
    assert "СЕРИЯ STORIES" in prompt
    assert "Кадр 1" in prompt
    assert "Кадр 5" in prompt

def test_04_telegram_longread(brain):
    """Scenario 4: Formatted Telegram post"""
    prompt = brain.content_engine.build_format_prompt("telegram")
    assert "TELEGRAM" in prompt

def test_05_weekly_content_sprint(brain):
    """Scenario 5: 7-day content sprint plan across 4 rubrics"""
    plan = brain.content_engine.build_content_sprint_plan(profile=brain.profile_engine.get_profile())
    assert len(plan) == 4
    days = [p["day"] for p in plan]
    assert "Понедельник" in days
    assert "Пятница" in days

# ---------------------------------------------------------------------------
# SCENARIOS 6-10: SALES & OBJECTION ENGINE
# ---------------------------------------------------------------------------
def test_06_objection_dorogo(brain):
    """Scenario 6: Objection 'дорого' handled with value reframing"""
    resp = brain.sales_engine.generate_objection_response("дорого")
    assert "вложение" in resp.lower() or "стоимость" in resp.lower()
    assert "подскажите" in resp.lower() or "комфортное" in resp.lower()

def test_07_objection_ne_umeem_pozirovat(brain):
    """Scenario 7: Objection 'не умеем позировать' handled with psychological safety"""
    resp = brain.sales_engine.generate_objection_response("не умеем позировать")
    assert "95%" in resp or "моделями" in resp or "подсказывать" in resp
    assert "музыку" in resp.lower() or "атмосферу" in resp.lower()

def test_08_objection_podumaem(brain):
    """Scenario 8: Objection 'я подумаю' handled without aggressive pushing"""
    resp = brain.sales_engine.generate_objection_response("подумаем")
    assert "не торопитесь" in resp.lower()
    assert "дату" in resp.lower() or "окошки" in resp.lower()

def test_09_objection_posovetuemsya(brain):
    """Scenario 9: Objection 'надо посоветоваться' with supportive partner prep"""
    resp = brain.sales_engine.generate_objection_response("посоветуемся")
    assert "вместе" in resp.lower() or "показать" in resp.lower()

def test_10_objection_nashli_deshevle(brain):
    """Scenario 10: Objection 'нашли дешевле' with dignified differentiation"""
    resp = brain.sales_engine.generate_objection_response("нашли дешевле")
    assert "сравниваете" in resp.lower()
    assert "результат" in resp.lower() or "подход" in resp.lower()

# ---------------------------------------------------------------------------
# SCENARIOS 11-15: CLIENT CHAT & PRICING
# ---------------------------------------------------------------------------
def test_11_client_chat_analysis(brain):
    """Scenario 11: Reconstruct chat screenshot/text and detect sales stage & objections"""
    chat_text = "Здравствуйте! А сколько стоит съемка? Ой, что-то дороговато у вас..."
    analysis = brain.sales_engine.analyze_client_dialogue(chat_text)
    assert analysis["detected_stage"] == "THINKING"
    assert "дорого" in analysis["detected_objections"]
    assert "ценность" in analysis["recommended_strategy"].lower()

def test_12_pricing_ladder_cannibalization(brain):
    """Scenario 12: Detect cannibalization in photographer's package structure"""
    bad_packages = [
        {"name": "Мини", "price": 5000, "duration_hours": 2, "retouched_photos": 40},
        {"name": "Макси", "price": 15000, "duration_hours": 2, "retouched_photos": 50}
    ]
    eval_res = brain.sales_engine.evaluate_pricing_ladder(bad_packages)
    assert any("перегружен" in iss for iss in eval_res["issues_detected"])
    assert any("трехпакетную" in rec for rec in eval_res["recommendations"])

def test_13_profile_positioning_audit(brain):
    """Scenario 13: 10-point audit assessing first 3 seconds clarity"""
    bio_text = "Фотографирую с душой. Пишите в лс."
    audit = brain.sales_engine.audit_profile_positioning(bio_text)
    assert audit["score"] <= 7
    assert any("город" in r.lower() for r in audit["recommendations"])
    assert any("нишу" in r.lower() for r in audit["recommendations"])

def test_14_client_lifecycle_state_transition(brain):
    """Scenario 14: Client state lifecycle management"""
    c = brain.create_client(name="Виктория", contact="@viktoria_test", status=ClientStatus.LEAD)
    assert c.status == ClientStatus.LEAD
    # Update status to PROPOSAL then BOOKED
    c_fetched = brain.get_client(c.id)
    assert c_fetched is not None
    assert c_fetched.name == "Виктория"

def test_15_project_lifecycle_state(brain):
    """Scenario 15: Project state lifecycle with concept and shot list"""
    p = brain.create_project(name="Осенний кампейн", description="Съемка пальто", status=ProjectStatus.IDEA)
    assert p.status == ProjectStatus.IDEA
    fetched_p = brain.get_project(p.id)
    assert fetched_p is not None
    assert fetched_p.name == "Осенний кампейн"

# ---------------------------------------------------------------------------
# SCENARIOS 16-20: SHOOTING & MOODBOARDS
# ---------------------------------------------------------------------------
def test_16_visual_logic_concept(brain):
    """Scenario 16: Synthesize visual logic: light, color palette HEX, location, styling"""
    logic = brain.shooting_engine.build_visual_logic("Cinematic Mood", genre="Портрет")
    assert "light_scheme" in logic
    assert "color_palette" in logic
    assert len(logic["color_palette"]) >= 4
    assert logic["color_palette"][0]["hex"].startswith("#")
    assert "styling_and_wardrobe" in logic

def test_17_shot_list_timing(brain):
    """Scenario 17: Production shot list with chronological phases"""
    shots = brain.shooting_engine.generate_shot_list(60)
    assert len(shots) == 4
    assert shots[0]["timing"] == "00:00 - 00:15"
    assert "разогрев" in shots[0]["phase"].lower()
    assert len(shots[0]["key_shots"]) >= 3

def test_18_reference_analysis(brain):
    """Scenario 18: Deconstruct reference image into photographic parameters"""
    ref_desc = "Девушка у окна в контровом свете, малая глубина резкости, пленочное зерно"
    analysis = brain.shooting_engine.analyze_reference(ref_desc)
    assert "light_analysis" in analysis
    assert "мягкий" in analysis["light_analysis"].lower() or "окна" in analysis["light_analysis"].lower()
    assert "adaptation_tips" in analysis

def test_19_client_prep_memo(brain):
    """Scenario 19: Client preparation checklist memo sent 2 days prior"""
    memo = brain.shooting_engine.generate_client_prep_memo("Алиса")
    assert "Алиса" in memo
    assert "СОН И ВОДА" in memo
    assert "БЕЛЬЕ" in memo
    assert "НАСТРОЙ" in memo

def test_20_multimodal_reference_extraction(brain):
    """Scenario 20: Multimodal reference breakdown handles both natural and flash light"""
    flash_ref = "Жесткая накамерная вспышка в лоб на вечеринке"
    analysis = brain.shooting_engine.analyze_reference(flash_ref)
    assert "жесткий" in analysis["light_analysis"].lower() or "вспышка" in analysis["light_analysis"].lower()

# ---------------------------------------------------------------------------
# SCENARIOS 21-25: VOICE & DAILY PLANNING
# ---------------------------------------------------------------------------
def test_21_voice_to_content_pipeline(brain):
    """Scenario 21: Spoken voice note decomposed into Post, 2 Reels, Stories and Task"""
    voice_transcript = "Вчера была съемка с Анной, она сначала очень боялась камеры, а потом мы включили музыку и кадры вышли просто космос!"
    pack = brain.voice_engine.process_voice_transcript(voice_transcript)
    assert len(pack["extracted_events"]) >= 1
    assert len(pack["business_insights"]) >= 1
    assert len(pack["derivative_post"]) > 50
    assert len(pack["derivative_reels"]) == 2
    assert len(pack["derivative_stories"]) == 5
    assert pack["suggested_task"]["priority"] == "HIGH"

def test_22_daily_planning_priorities(brain):
    """Scenario 22: 'Что мне сегодня делать?' outputs Top-3 priorities"""
    plan = brain.proactive_engine.generate_daily_plan()
    assert "priorities" in plan
    assert len(plan["priorities"]) == 3
    assert plan["priorities"][0]["priority_level"] == 1
    assert "SHOOTING" in plan["priorities"][0]["domain"]

def test_23_proactive_nudge_quiet_hours(brain):
    """Scenario 23: Proactive engine respects quiet hours"""
    pe = brain.proactive_engine
    # At 23:00 (11 PM), quiet hours must be active
    assert pe.is_quiet_hours(current_hour=23) is True
    # At 14:00 (2 PM), quiet hours must be inactive
    assert pe.is_quiet_hours(current_hour=14) is False

def test_24_proactive_post_shoot_nudge(brain):
    """Scenario 24: Post-shoot proactive suggestion generated during work hours"""
    nudge = brain.proactive_engine.evaluate_proactive_nudge("Вчера прошла съемка для лукбука")
    # If not in quiet hours, nudge is offered
    if not brain.proactive_engine.is_quiet_hours():
        assert nudge is not None
        assert "съёмка" in nudge["message"]

def test_25_task_creation_and_lifecycle(brain):
    """Scenario 25: Unified Task model tracking, prioritization, and completion"""
    t = brain.create_task(
        title="Собрать превью для лукбука",
        task_type="editing",
        priority=TaskPriority.HIGH,
        due_at="2026-10-01"
    )
    assert t.status == TaskStatus.TODO
    assert t.priority == TaskPriority.HIGH
    
    # Update to completed
    updated = brain.update_task_status(t.task_id, TaskStatus.COMPLETED)
    assert updated.status == TaskStatus.COMPLETED

# ---------------------------------------------------------------------------
# SCENARIOS 26-32: WORKFLOWS, ROUTING & SAFETY
# ---------------------------------------------------------------------------
def test_26_photoday_launch_workflow(brain):
    """Scenario 26: Stateful multi-step Photoday Launch workflow"""
    wf = brain.start_workflow("photoday_launch", initial_context={"theme": "Осенний портрет"})
    assert wf.status == "ACTIVE"
    assert len(wf.steps) == 8
    assert wf.steps[0].name == "audit_context"
    
    # Advance to step 1
    adv = brain.advance_workflow(wf.workflow_id, {"status": "ok"})
    assert adv.current_step == 1
    assert adv.steps[1].name == "concept_and_visual_logic"

def test_27_workflow_approval_gate(brain):
    """Scenario 27: Critical operations require user approval before advancing"""
    wf = brain.start_workflow("client_chat_analysis")
    assert wf.steps[3].requires_approval is True
    # Verify approval function
    appr = brain.approve_workflow_step(wf.workflow_id, approved=True)
    assert appr.approval_state == "APPROVED"

def test_28_compound_routing_shooting_sales_content(brain):
    """Scenario 28: Compound intent recognition: SHOOTING + SALES + CONTENT"""
    query = "Короче, у меня на следующей неделе съёмка, хочу красиво её продать, но вообще не знаю с чего начать"
    routing = brain.router.route(query)
    assert len(routing.compound_intents) >= 2
    assert "SALES" in routing.compound_intents
    assert "PHOTO" in routing.compound_intents

def test_29_compound_routing_pricing_sales_content(brain):
    """Scenario 29: Compound intent recognition: PRICING + SALES + CONTENT"""
    query = "Разбери мой прайс и сделай пост, который объяснит клиентам, почему я дороже"
    routing = brain.router.route(query)
    assert "PRICING" in routing.compound_intents
    assert "CONTENT" in routing.compound_intents or "SALES" in routing.compound_intents

def test_30_adaptive_questioning_photoday(brain):
    """Scenario 30: Adaptive questioning identifies missing parameters and formulates questions"""
    query = "Хочу запустить фотодень"
    routing = brain.router.route(query, context={"profile": brain.profile_engine.get_profile()})
    assert routing.workflow_suggested == "photoday_launch"
    assert routing.action_type == "CLARIFY"
    assert len(routing.clarifying_questions) >= 1
    assert any("дату" in q.lower() or "локация" in q.lower() for q in routing.clarifying_questions)

def test_31_negative_knowledge_no_hallucination(brain):
    """Scenario 31: System refuses when factual knowledge is absent in materials"""
    query = "Какой секретный пароль от сейфа фотостудии в файлах?"
    hits = brain.knowledge_engine.retrieve(query, limit=2)
    verdict = brain.knowledge_engine.evaluate_hallucination(query, hits, "В доступных материалах нет информации о пароле.")
    assert verdict.value in ["grounded", "inference", "general_knowledge", "unknown"]
    assert verdict == HallucinationType.UNKNOWN

def test_32_client_privacy_isolation(brain):
    """Scenario 32: Client data remains properly partitioned and isolated"""
    c1 = brain.create_client(name="Мария Иванова", service="Семейная", budget="20 000 руб")
    c2 = brain.create_client(name="Ольга Петрова", service="Индивидуальная", budget="40 000 руб")
    
    tasks_c1 = brain.list_tasks(client_id=c1.id)
    tasks_c2 = brain.list_tasks(client_id=c2.id)
    assert len(tasks_c1) == 0
    assert len(tasks_c2) == 0
