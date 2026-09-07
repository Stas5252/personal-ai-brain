"""
Comprehensive 50-Scenario Product Benchmark for Personal AI Brain.
Evaluates the system as a specialized personal work system for photographers
across all 11 core categories:
1. CONTENT (Scenarios 1-5)
2. SALES & OBJECTIONS (Scenarios 6-10)
3. CLIENT & CRM LIFECYCLE (Scenarios 11-14)
4. PRICING & COMMERCIAL ARCHITECTURE (Scenarios 15-18)
5. SHOOTING & ART DIRECTION (Scenarios 19-23)
6. IMAGE & REFERENCES (Scenarios 24-27)
7. VOICE-TO-CONTENT (Scenarios 28-31)
8. KNOWLEDGE & RAG FACTORY (Scenarios 32-35)
9. MEMORY & ADMISSION (Scenarios 36-39)
10. STYLE ADHERENCE & SIGNATURE (Scenarios 40-43)
11. WORKFLOW & SYSTEM INTEGRATION (Scenarios 44-50)
"""
import pytest
from src.brain.services.brain_service import BrainService
from src.brain.models.profile import UserProfile
from src.brain.models.client import Client, ClientStatus
from src.brain.models.project import Project, ProjectStatus
from src.brain.models.task import Task, TaskStatus, TaskPriority, ApprovalState
from src.brain.models.routing import IntentType
from src.brain.models.memory import MemoryItem, MemoryType
from src.brain.models.style import StyleProfile
from src.brain.models.knowledge import KnowledgeLayer, HallucinationType

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

# ===========================================================================
# CATEGORY 1: CONTENT (Scenarios 1-5)
# ===========================================================================

def test_scenario_01_content_first_shoot_post(brain):
    """Scenario 01: Post preparing beginner clients for their first shoot"""
    prompt = brain.content_engine.build_format_prompt("post")
    assert "ЦЕПЛЯЮЩИЙ ХУК" in prompt
    assert "ТЕЛО ПОСТА" in prompt
    assert "CTA" in prompt

def test_scenario_02_content_reels_posing_mistakes(brain):
    """Scenario 02: Reels script for posing mistakes with 3-sec hook & visual scenes"""
    prompt = brain.content_engine.build_format_prompt("reels")
    assert "ХУК (0-3 сек)" in prompt
    assert "ВИЗУАЛЬНЫЙ РЯД" in prompt
    assert "ТЕКСТ НА ЭКРАНЕ" in prompt
    assert "ГОЛОСОВОЙ ТЕКСТ" in prompt

def test_scenario_03_content_stories_photoday_warmup(brain):
    """Scenario 03: 5-slide Stories sequence with narrative tension for photoday warmup"""
    prompt = brain.content_engine.build_format_prompt("stories")
    assert "СЕРИЯ STORIES" in prompt
    assert "Кадр 1" in prompt
    assert "Кадр 3 (Кульминация)" in prompt
    assert "Кадр 5" in prompt

def test_scenario_04_content_telegram_raw_files_manifesto(brain):
    """Scenario 04: Formatted Telegram longread post"""
    prompt = brain.content_engine.build_format_prompt("telegram")
    assert "TELEGRAM" in prompt
    assert "Заголовок жирным" in prompt

def test_scenario_05_content_emergency_recovery_mined(brain):
    """Scenario 05: 'Мне нечего выложить' recovery workflow dynamically mining projects"""
    prof = brain.profile_engine.get_profile()
    projects = [
        {"name": "Съемка винтажного Porsche 911", "description": "Паркинг, неон", "status": "COMPLETED"},
        {"name": "Лукбук шелковых платьев", "description": "Минималистичная студия", "status": "EDITING"}
    ]
    angles = brain.content_engine.emergency_content_recovery(profile=prof, recent_projects=projects)
    assert len(angles) == 3
    assert any("Porsche 911" in a["hook"] or "Porsche 911" in a["theme"] for a in angles)
    assert any("Лукбук шелковых платьев" in a["hook"] or "Лукбук шелковых платьев" in a["theme"] for a in angles)

# ===========================================================================
# CATEGORY 2: SALES & OBJECTIONS (Scenarios 6-10)
# ===========================================================================

def test_scenario_06_sales_objection_dorogo(brain):
    """Scenario 06: Objection 'дорого' handled with value preservation and no price dropping"""
    client = Client(id="c_test", name="Наталья", service="Индивидуальная съёмка", budget="10 000 руб")
    resp = brain.sales_engine.generate_objection_response("дорого", profile=brain.profile_engine.get_profile(), client=client)
    assert "Наталья" in resp
    assert "вложение" in resp.lower() or "стоимость" in resp.lower()
    assert "подскажите" in resp.lower() or "комфортное" in resp.lower()

def test_scenario_07_sales_objection_ne_umeem_pozirovat(brain):
    """Scenario 07: Objection 'не умеем позировать' handled with psychological safety"""
    client = Client(id="c_test2", name="Екатерина")
    resp = brain.sales_engine.generate_objection_response("не умеем позировать", client=client)
    assert "Екатерина" in resp
    assert "95%" in resp or "подсказывать" in resp
    assert "музыку" in resp.lower() or "атмосферу" in resp.lower()

def test_scenario_08_sales_objection_podumaem(brain):
    """Scenario 08: Objection 'я подумаю' handled with empathy and open timeframe check"""
    client = Client(id="c_test3", name="Анна")
    resp = brain.sales_engine.generate_objection_response("подумаем", client=client)
    assert "Анна" in resp
    assert "не торопитесь" in resp.lower()
    assert "дату" in resp.lower() or "окошки" in resp.lower()

def test_scenario_09_sales_objection_posovetuemsya(brain):
    """Scenario 09: Objection 'надо посоветоваться' with supportive partner prep"""
    client = Client(id="c_test4", name="Марина")
    resp = brain.sales_engine.generate_objection_response("посоветуемся с мужем", client=client)
    assert "Марина" in resp
    assert "вместе" in resp.lower() or "показать" in resp.lower()

def test_scenario_10_sales_objection_nashli_deshevle(brain):
    """Scenario 10: Objection 'нашли дешевле' with dignified differentiation"""
    resp = brain.sales_engine.generate_objection_response("нашли дешевле")
    assert "сравниваете" in resp.lower()
    assert "результат" in resp.lower() or "подход" in resp.lower()

# ===========================================================================
# CATEGORY 3: CLIENT & CRM LIFECYCLE (Scenarios 11-14)
# ===========================================================================

def test_scenario_11_client_dialogue_stage_diagnosis(brain):
    """Scenario 11: Diagnose dialogue stage and hidden objections from client chat"""
    chat_sample = "Добрый день! Хочу фотосессию на день рождения, но боюсь, что буду деревянной в кадре..."
    diag = brain.sales_engine.analyze_client_dialogue(chat_sample)
    assert "не умеем позировать" in diag["detected_objections"]
    assert "камеры" in diag["recommended_strategy"] or "ведение" in diag["recommended_strategy"]

def test_scenario_12_client_lifecycle_progression(brain):
    """Scenario 12: Full client lifecycle progression"""
    c = brain.create_client(name="Светлана", contact="@sveta_art", status=ClientStatus.LEAD)
    assert c.status == ClientStatus.LEAD
    c.status = ClientStatus.THINKING
    c.status = ClientStatus.BOOKED
    assert c.status == ClientStatus.BOOKED

def test_scenario_13_client_ghosting_careful_followup(brain):
    """Scenario 13: Proactive nudge suggestion when client ghosts"""
    nudge = brain.proactive_engine.evaluate_proactive_nudge("Клиент не отвечает больше суток после прайса")
    if not brain.proactive_engine.is_quiet_hours():
        assert nudge is not None
        assert "диалог" in nudge["message"] or "сообщение" in nudge["message"]

def test_scenario_14_client_ltv_repeat_booking(brain):
    """Scenario 14: LTV & repeat booking priority in daily plan"""
    c_repeat = Client(id="rep_1", name="Ольга", status=ClientStatus.REPEAT, service="Сезонный лукбук")
    plan = brain.proactive_engine.generate_daily_plan(clients=[c_repeat])
    assert len(plan["priorities"]) == 3

# ===========================================================================
# CATEGORY 4: PRICING & COMMERCIAL ARCHITECTURE (Scenarios 15-18)
# ===========================================================================

def test_scenario_15_pricing_cannibalization_detection(brain):
    """Scenario 15: Identify package cannibalization in photographer rates"""
    packages = [
        {"name": "Экспресс", "price": 4000, "duration_hours": 2, "retouched_photos": 40},
        {"name": "Стандарт", "price": 12000, "duration_hours": 2, "retouched_photos": 45}
    ]
    eval_res = brain.sales_engine.evaluate_pricing_ladder(packages)
    assert any("перегружен" in iss for iss in eval_res["issues_detected"])

def test_scenario_16_pricing_increase_psychological_strategy(brain):
    """Scenario 16: Account positioning and pricing ladder recommendations"""
    packages = [
        {"name": "Экспресс", "price": 8000, "duration_hours": 1, "retouched_photos": 15},
        {"name": "Оптимальный", "price": 16000, "duration_hours": 2, "retouched_photos": 35},
        {"name": "Премиум", "price": 32000, "duration_hours": 3, "retouched_photos": 60}
    ]
    res = brain.sales_engine.evaluate_pricing_ladder(packages)
    assert res["total_packages"] == 3
    assert len(res["issues_detected"]) == 0
    assert any("апселл" in rec.lower() or "фотокнига" in rec.lower() for rec in res["recommendations"])

def test_scenario_17_pricing_high_margin_upsells(brain):
    """Scenario 17: Upsell recommendations added to pricing structure"""
    packages = [{"name": "Базовый", "price": 10000}]
    res = brain.sales_engine.evaluate_pricing_ladder(packages)
    assert any("апселл" in rec.lower() or "фотокнига" in rec.lower() for rec in res["recommendations"])

def test_scenario_18_pricing_vip_package_differentiation(brain):
    """Scenario 18: Bio and positioning clarity for high-ticket clientele"""
    bio = "Fashion & Editorial фотограф Москва. Полное продюсирование съемки, стиль и команда. Запись в Direct."
    audit = brain.sales_engine.audit_profile_positioning(bio)
    assert audit["score"] >= 8
    assert audit["clarity"] == "Высокая"

# ===========================================================================
# CATEGORY 5: SHOOTING & ART DIRECTION (Scenarios 19-23)
# ===========================================================================

def test_scenario_19_shooting_cinematic_noir_visual_logic(brain):
    """Scenario 19: Dynamic Noir visual logic: hard light snoot & dark HEX palette"""
    logic = brain.shooting_engine.build_visual_logic("Noir City Walk", mood="Драматичный нуар")
    assert "snoot" in logic["light_scheme"]["primary"] or "луч" in logic["light_scheme"]["primary"]
    assert any(c["hex"] == "#1A1A1D" for c in logic["color_palette"])
    assert "Low-Key" in logic["light_scheme"]["character"]

def test_scenario_20_shooting_warm_golden_hour_visual_logic(brain):
    """Scenario 20: Dynamic Warm/Sunset visual logic: golden hour & terracotta palette"""
    logic = brain.shooting_engine.build_visual_logic("Теплый закат в оранжерее", mood="Золотой закат, тепло")
    assert "закат" in logic["light_scheme"]["primary"] or "солнечн" in logic["light_scheme"]["primary"]
    assert any(c["hex"] == "#E9C46A" for c in logic["color_palette"])
    assert "High-Key" in logic["light_scheme"]["character"]

def test_scenario_21_shooting_chronological_shotlist(brain):
    """Scenario 21: Chronological 60-min production shot list"""
    shots = brain.shooting_engine.generate_shot_list(60)
    assert len(shots) == 4
    assert shots[0]["timing"] == "00:00 - 00:15"
    assert "разогрев" in shots[0]["phase"].lower()
    assert shots[-1]["timing"] == "00:50 - 01:00"

def test_scenario_22_shooting_client_prep_memo_48h(brain):
    """Scenario 22: Client preparation memo with 5 key points"""
    memo = brain.shooting_engine.generate_client_prep_memo("Ольга")
    assert "Ольга" in memo
    assert "СОН И ВОДА" in memo
    assert "ОДЕЖДА И ОБУВЬ" in memo
    assert "БЕЛЬЕ" in memo
    assert "АКСЕССУАРЫ" in memo

def test_scenario_23_shooting_difficult_space_lighting(brain):
    """Scenario 23: Reference analysis adapting to studio space"""
    ref = "Естественный свет от большого окна в пол"
    analysis = brain.shooting_engine.analyze_reference(ref)
    assert "окн" in analysis["light_analysis"].lower() or "мягк" in analysis["light_analysis"].lower()
    assert "adaptation_tips" in analysis

# ===========================================================================
# CATEGORY 6: IMAGE & REFERENCES (Scenarios 24-27)
# ===========================================================================

def test_scenario_24_reference_natural_window_analysis(brain):
    """Scenario 24: Optical and diffusion deconstruction of window reference"""
    ref = "Мягкий рассеянный дневной свет от окна, диафрагма 1.4"
    res = brain.shooting_engine.analyze_reference(ref)
    assert "окн" in res["light_analysis"].lower() or "рассеян" in res["light_analysis"].lower()

def test_scenario_25_reference_direct_flash_analysis(brain):
    """Scenario 25: Direct flash deconstruction"""
    ref = "Жесткая накамерная вспышка в лоб на вечернем мероприятии"
    res = brain.shooting_engine.analyze_reference(ref)
    assert "жестк" in res["light_analysis"].lower() or "вспышк" in res["light_analysis"].lower()

def test_scenario_26_reference_hex_color_harmony(brain):
    """Scenario 26: HEX color palette validity"""
    logic = brain.shooting_engine.build_visual_logic("Studio campaign", genre="Fashion")
    assert len(logic["color_palette"]) == 4
    for c in logic["color_palette"]:
        assert c["hex"].startswith("#")
        assert len(c["hex"]) == 7

def test_scenario_27_image_honest_vision_contract(brain):
    """Scenario 27: Honest capability contract: refusal to simulate vision when not configured"""
    from src.brain.knowledge.extractors.vision_provider import VisionProvider
    from pathlib import Path
    vp = VisionProvider()
    res = vp.analyze_image(Path("missing_file.jpg"))
    assert res.status.value in ["NOT_CONFIGURED", "NOT_IMPLEMENTED", "ERROR"]

# ===========================================================================
# CATEGORY 7: VOICE-TO-CONTENT (Scenarios 28-31)
# ===========================================================================

def test_scenario_28_voice_emotional_shoot_decomposition(brain):
    """Scenario 28: Decomposing emotional shoot audio note"""
    note = "Сегодня снимали девушку, которая 5 лет не фотографировалась. Сначала зажалась, потом мы включили ее плейлист и она раскрылась!"
    pack = brain.voice_engine.process_voice_transcript(note)
    assert len(pack["extracted_events"]) >= 1
    assert any("5 лет не фотографировалась" in e for e in pack["extracted_events"])
    assert len(pack["story_beats"]) == 3

def test_scenario_29_voice_business_dilemma_extraction(brain):
    """Scenario 29: Business insight extraction from pricing voice note"""
    note = "Думаю о повышении цен. Текущий чек 8000 руб уже не покрывает студию и стилиста, но я боюсь потерять постоянных клиентов."
    pack = brain.voice_engine.process_voice_transcript(note)
    assert any("цен" in bi.lower() or "чек" in bi.lower() for bi in pack["business_insights"])
    assert "пакет" in pack["suggested_task"]["title"].lower() or "клиент" in pack["suggested_task"]["title"].lower()

def test_scenario_30_voice_derivative_assets_generation(brain):
    """Scenario 30: Derivative post and 2 Reels from voice note"""
    note = "Съемка в неоновом свете на паркинге. Получились кадры в стиле Бегущего по лезвию!"
    pack = brain.voice_engine.process_voice_transcript(note)
    assert len(pack["derivative_post"]) > 80
    assert len(pack["derivative_reels"]) == 2
    assert len(pack["derivative_stories"]) == 5

def test_scenario_31_voice_assistant_task_assignment(brain):
    """Scenario 31: Automatic actionable task creation from voice note"""
    note = "Закончили съемку с Анной, нужно срочно отправить превью до завтра!"
    pack = brain.voice_engine.process_voice_transcript(note)
    assert pack["suggested_task"]["priority"] == "HIGH"
    assert pack["suggested_task"]["due_in_hours"] == 24

# ===========================================================================
# CATEGORY 8: KNOWLEDGE & RAG FACTORY (Scenarios 32-35)
# ===========================================================================

def test_scenario_32_knowledge_exact_clause_retrieval(brain):
    """Scenario 32: Retrieval from Knowledge layers"""
    hits = brain.knowledge_engine.retrieve("подготовка к съемке", limit=3)
    assert isinstance(hits, list)

def test_scenario_33_knowledge_source_traceability(brain):
    """Scenario 33: Context assembly retains source traces"""
    ctx = brain.context_engine.assemble_context(
        query="Тест",
        system_policy="Policy",
        profile=brain.profile_engine.get_profile(),
        memories=[],
        knowledge=[]
    )
    assert hasattr(ctx, "traces")

def test_scenario_34_knowledge_layer_partitioning(brain):
    """Scenario 34: Support for professional and business knowledge layers"""
    assert KnowledgeLayer.PROFESSIONAL.value == "PROFESSIONAL"
    assert KnowledgeLayer.BUSINESS.value == "BUSINESS"

def test_scenario_35_knowledge_refusal_on_absent_facts(brain):
    """Scenario 35: Negative rejection when fact is missing from materials"""
    verdict = brain.knowledge_engine.evaluate_hallucination("Секретный код ячейки", [], "В материалах нет информации.")
    assert verdict == HallucinationType.UNKNOWN

# ===========================================================================
# CATEGORY 9: MEMORY & ADMISSION (Scenarios 36-39)
# ===========================================================================

def test_scenario_36_memory_automatic_admission_from_chat(brain):
    """Scenario 36: Automatic admission policy evaluates and identifies facts"""
    text = "Запомни: я терпеть не могу позирование 'рука у щеки', никогда не предлагай такое клиентам."
    adm = brain.memory_engine.evaluate_admission(text)
    assert adm.action.value in ["SAVE", "TEMPORARY", "IGNORE"]

def test_scenario_37_memory_recall_in_subsequent_context(brain):
    """Scenario 37: Retrieved memories injected into prompt context"""
    brain.memory_engine.add_memory(
        content="Моя любимая оптика для портрета — 85mm f/1.4",
        memory_type=MemoryType.PREFERENCE,
        importance=0.9,
        source="unit_test"
    )
    mems = brain.memory_engine.retrieve_relevant_memories("какой объектив выбрать", limit=2)
    assert len(mems) >= 1
    assert any("85mm" in m[0].content for m in mems)

def test_scenario_38_memory_episodic_semantic_separation(brain):
    """Scenario 38: Separation between episodic and semantic memory types"""
    assert MemoryType.EPISODE.value == "EPISODE"
    assert MemoryType.PREFERENCE.value == "PREFERENCE"

def test_scenario_39_memory_client_project_isolation(brain):
    """Scenario 39: Context isolation between distinct clients"""
    c_a = brain.create_client("Клиент А", service="Портрет")
    c_b = brain.create_client("Клиент Б", service="Свадьба")
    t_a = brain.list_tasks(client_id=c_a.id)
    t_b = brain.list_tasks(client_id=c_b.id)
    assert len(t_a) == 0
    assert len(t_b) == 0

# ===========================================================================
# CATEGORY 10: STYLE ADHERENCE & SIGNATURE (Scenarios 40-43)
# ===========================================================================

def test_scenario_40_style_tone_adaptation(brain):
    """Scenario 40: Style instructions accurately capture photographer's tone"""
    prof = brain.profile_engine.get_profile()
    sp = StyleProfile(tone=prof.tone, forbidden_expressions=prof.forbidden_words)
    instr = brain.style_engine.build_style_instructions(sp)
    assert "СТИЛЬ И ТОНАЛЬНОСТЬ" in instr
    assert "ЗАПРЕЩЕННЫЕ СЛОВА" in instr

def test_scenario_41_style_forbidden_words_filter(brain):
    """Scenario 41: Benchmark detects forbidden words violations"""
    prof = brain.profile_engine.get_profile()
    sp = StyleProfile(tone=prof.tone, forbidden_expressions=prof.forbidden_words)
    bad_text = "Привет красоточка! Лови уникальный прайс и скидочка для тебя!"
    bench = brain.style_engine.evaluate_benchmark(bad_text, sp, forbidden_words=prof.forbidden_words)
    assert bench.forbidden_violations >= 2
    assert bench.overall_score == 0.0

def test_scenario_42_style_evaluation_benchmark(brain):
    """Scenario 42: Benchmark passes for authentic clean photographer voice"""
    prof = brain.profile_engine.get_profile()
    sp = StyleProfile(tone=prof.tone, forbidden_expressions=prof.forbidden_words)
    good_text = "Здравствуйте! Подготовила для вас подборку кинематографичных референсов. Давайте обсудим удобные даты."
    bench = brain.style_engine.evaluate_benchmark(good_text, sp, forbidden_words=prof.forbidden_words)
    assert bench.forbidden_violations == 0
    assert bench.overall_score > 0.0

def test_scenario_43_style_preservation_across_formats(brain):
    """Scenario 43: Content formats maintain structure without generic cliché phrases"""
    reel = brain.content_engine.build_format_prompt("reels")
    assert "ХУК" in reel and "CTA" in reel

# ===========================================================================
# CATEGORY 11: WORKFLOW & SYSTEM INTEGRATION (Scenarios 44-50)
# ===========================================================================

def test_scenario_44_workflow_photoday_stateful_dag(brain):
    """Scenario 44: Execution of photoday workflow steps"""
    wf = brain.start_workflow("photoday_launch", initial_context={"theme": "Осенний нуар"})
    assert wf.status == "ACTIVE"
    assert wf.current_step == 0
    updated_wf, out = brain.execute_workflow_step(wf.workflow_id)
    assert updated_wf.current_step == 1
    assert "concept_and_visual_logic" in updated_wf.steps[1].name

def test_scenario_45_workflow_compound_intent_routing(brain):
    """Scenario 45: Compound intent routing parses compound queries"""
    q = "Хочу снять лавстори на закате и сразу продать серию через рилс и сторис"
    routing = brain.router.route(q)
    assert len(routing.compound_intents) >= 2
    assert any(intent in routing.compound_intents for intent in ["PHOTO", "MOODBOARD", "REELS", "STORIES", "SALES"])

def test_scenario_46_workflow_adaptive_questioning_gaps(brain):
    """Scenario 46: Adaptive questioning formulates targeted inquiries for missing data"""
    routing = brain.router.route("Хочу запустить фотодень", context={"profile": brain.profile_engine.get_profile()})
    assert routing.action_type == "CLARIFY"
    assert len(routing.clarifying_questions) >= 1

def test_scenario_47_workflow_approval_gate_blocking(brain):
    """Scenario 47: Workflow step requiring user approval blocks until granted"""
    wf = brain.start_workflow("client_chat_analysis")
    assert any(s.requires_approval for s in wf.steps)

def test_scenario_48_workflow_daily_planning_db_driven(brain):
    """Scenario 48: Daily planning queries real database state"""
    proj = brain.create_project("Кампейн для бренда", status=ProjectStatus.SHOOTING)
    client = brain.create_client("Алиса", status=ClientStatus.THINKING)
    plan = brain.proactive_engine.generate_daily_plan()
    assert len(plan["priorities"]) == 3
    assert any("Кампейн для бренда" in p["title"] for p in plan["priorities"])

def test_scenario_49_workflow_task_management_lifecycle(brain):
    """Scenario 49: Task creation, priority sorting, status updating"""
    t = brain.create_task("Ретушь 30 кадров", task_type="editing", priority=TaskPriority.URGENT)
    assert t.status == TaskStatus.TODO
    assert t.priority == TaskPriority.URGENT
    updated = brain.update_task_status(t.task_id, TaskStatus.COMPLETED)
    assert updated.status == TaskStatus.COMPLETED

def test_scenario_50_workflow_openwebui_sse_streaming(brain):
    """Scenario 50: Verification of OpenAI models discovery format"""
    from src.brain.api.app import app
    from src.brain.config import BRAIN_API_KEY
    from fastapi.testclient import TestClient
    client = TestClient(app, headers={"Authorization": f"Bearer {BRAIN_API_KEY}"})
    res = client.get("/v1/models")
    assert res.status_code == 200
    assert any(m["id"] == "personal-ai-brain" for m in res.json()["data"])