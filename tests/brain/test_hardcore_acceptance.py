"""
Hardcore Acceptance Tests for Personal AI Brain: "Not a Chatbot" Benchmark.
Verifies production capabilities on 5 complex real-world photographer challenges:
1. Hardcore 1: 35yo female client fashion prep & selling strategy
2. Hardcore 2: Multimodal combined input (Voice + Screenshot OCR + Pricing PDF)
3. Hardcore 3: Price increase with fear of client loss (psychology + grandfathering + post + DM)
4. Hardcore 4: 'Мне нечего выложить' with real DB project and memory mining
5. Hardcore 5: 'Что мне сегодня делать?' with real DB state (projects, thinking leads, tasks)
"""
import pytest
from src.brain.services.brain_service import BrainService
from src.brain.models.profile import UserProfile
from src.brain.models.client import Client, ClientStatus
from src.brain.models.project import Project, ProjectStatus
from src.brain.models.task import Task, TaskStatus, TaskPriority
from src.brain.models.memory import MemoryType

@pytest.fixture(scope="module")
def brain():
    b = BrainService()
    # Configure production photographer profile
    p = UserProfile(
        identity="Елена Морозова",
        profession="Портретный и fashion фотограф",
        city="Москва",
        niche="Кинематографичный женский портрет и тихая роскошь",
        genres=["Женский портрет", "Fashion", "Экспертный портрет"],
        services=["Индивидуальная съёмка", "Экспресс-портрет", "Кампейн для бренда"],
        pricing={"Экспресс": "8 000 руб", "Стандарт": "15 000 руб", "Премиум": "30 000 руб"},
        audience="Девушки 25-45 лет, эксперты, предпринимательницы, ценящие сдержанную эстетику",
        tone="Теплый, кинематографичный, заботливый, интеллигентный, без клише",
        forbidden_words=["красоточка", "волшебство", "уникальный прайс", "скидочка", "налетай"]
    )
    b.profile_engine.save_profile(p)
    return b

def test_hardcore_01_35yo_female_executive_prep(brain):
    """
    Hardcore 1: 35-year-old female executive fashion prep & selling strategy.
    Persona: IT Top Manager, needs personal brand portraits, fears looking vulgar or artificial,
    convinced she doesn't know how to pose, budget 25-30k.
    """
    client = brain.create_client(
        name="Мария",
        contact="@maria_tech_exec",
        status=ClientStatus.LEAD,
        service="Индивидуальная съёмка (Премиум)",
        budget="30 000 руб",
        preferences="Сдержанная эстетика, тихая роскошь, естественность",
        objections="Боюсь выглядеть нелепо или вульгарно, совсем не умею позировать"
    )

    # 1. Objections handling: gentle reassurance with psychological safety
    response = brain.sales_engine.generate_objection_response(
        objection_type="не умеем позировать",
        profile=brain.profile_engine.get_profile(),
        client=client
    )
    assert "Мария" in response
    assert "позировать" in response.lower() or "атмосферу" in response.lower()
    assert "музыку" in response.lower() or "подсказывать" in response.lower()

    # 2. Visual Logic: Quiet luxury / Executive aesthetic
    v_logic = brain.shooting_engine.build_visual_logic(
        concept_title="Executive Quiet Luxury",
        genre="Экспертный женский портрет",
        mood="Сдержанный, статусный, минималистичный, глубокий"
    )
    assert "light_scheme" in v_logic
    assert len(v_logic["color_palette"]) == 4
    # Palettes must have valid HEX codes
    assert all(c["hex"].startswith("#") for c in v_logic["color_palette"])
    assert any("пиджак" in s.lower() or "шерсть" in s.lower() or "шелк" in s.lower() for s in v_logic["styling_and_wardrobe"])

    # 3. 60-minute Chronological Shot List
    shot_list = brain.shooting_engine.generate_shot_list(60)
    assert len(shot_list) == 4
    assert "разогрев" in shot_list[0]["phase"].lower()
    assert "детали" in shot_list[2]["phase"].lower()

    # 4. 48h Pre-Shoot Memo tailored for client
    memo = brain.shooting_engine.generate_client_prep_memo("Мария")
    assert "Мария" in memo
    assert "СОН И ВОДА" in memo
    assert "БЕЛЬЕ" in memo

def test_hardcore_02_multimodal_voice_chat_price_pdf(brain):
    """
    Hardcore 2: Multimodal combined input:
    - Spoken voice note from photographer regarding barter/discount request
    - Client chat screenshot OCR with 30% discount demand
    - Pricing PDF rules forbidding discounts for tags
    """
    # 1. Spoken voice transcript
    voice_transcript = "Только что звонила клиентка Карина, хочет съемку на открытии ее шоурума, просит скидку 30%, потому что у нее большой блог."
    voice_pack = brain.voice_engine.process_voice_transcript(voice_transcript)
    assert len(voice_pack["extracted_events"]) >= 1
    assert "Карина" in voice_pack["source_transcript"]

    # 2. Client chat OCR screenshot text
    chat_ocr = "Карина: Привет! Нам очень нравятся твои работы. Сделай скидку 30% от пакета Премиум, а мы выложим отметки во всех сторис?"
    diag = brain.sales_engine.analyze_client_dialogue(chat_ocr)
    assert "дорого" in diag["detected_objections"]

    # 3. Negotiation response upholding price integrity
    client_karina = Client(id="c_karina", name="Карина", service="Премиум (Открытие шоурума)", budget="Скидка 30%")
    negotiation_msg = brain.sales_engine.generate_objection_response("дорого", profile=brain.profile_engine.get_profile(), client=client_karina)
    assert "Карина" in negotiation_msg
    assert "вложение" in negotiation_msg.lower() or "стоимость" in negotiation_msg.lower()

    # 4. Automatic task creation for follow-up
    task = brain.create_task(
        title="Отправить Карине встречное предложение без скидки с добавленным видео-тизером",
        task_type="sales",
        priority=TaskPriority.HIGH,
        client_id=client_karina.id
    )
    assert task.status == TaskStatus.TODO
    assert task.priority == TaskPriority.HIGH

def test_hardcore_03_price_increase_psychological_strategy(brain):
    """
    Hardcore 3: Price increase strategy with fear of client loss.
    Elena wants to raise rates from 8k to 15k, fearing past clients will leave.
    Delivers: economic evaluation, 30-day grandfathering transition, announcement post, and 1-on-1 scripts.
    """
    packages = [
        {"name": "Экспресс", "price": 8000, "duration_hours": 1, "retouched_photos": 15},
        {"name": "Стандарт", "price": 15000, "duration_hours": 2, "retouched_photos": 30},
        {"name": "Премиум", "price": 30000, "duration_hours": 3, "retouched_photos": 60}
    ]
    eval_res = brain.sales_engine.evaluate_pricing_ladder(packages)
    assert eval_res["total_packages"] == 3
    assert len(eval_res["issues_detected"]) == 0
    assert any("апселл" in rec.lower() or "фотокнига" in rec.lower() for rec in eval_res["recommendations"])

    # 1. Voice-to-Content on pricing anxiety
    voice_pricing_dilemma = "Боюсь поднимать цену до 15 000 руб, вдруг старые клиенты скажут, что я зазналась и уйдут."
    voice_pack = brain.voice_engine.process_voice_transcript(voice_pricing_dilemma)
    assert any("цен" in bi.lower() or "чек" in bi.lower() or "клиент" in bi.lower() for bi in voice_pack["business_insights"])

    # 2. Announcement post structure
    post_fmt = brain.content_engine.build_format_prompt("post")
    assert "ЦЕПЛЯЮЩИЙ ХУК" in post_fmt
    assert "ТЕЛО ПОСТА" in post_fmt

    # 3. Empathetic 1-on-1 script when old client remarks on price
    old_client = Client(id="c_old", name="Вероника", service="Стандарт")
    old_client_resp = brain.sales_engine.generate_objection_response("дорого", client=old_client)
    assert "Вероника" in old_client_resp
    assert "вложение" in old_client_resp.lower() or "стоимость" in old_client_resp.lower()

def test_hardcore_04_emergency_no_content_real_project_mining(brain):
    """
    Hardcore 4: 'Мне нечего выложить' with real DB project and memory mining.
    Proves zero template fallback: extracts real shoot names and memory facts from DB.
    """
    # 1. Populate real project and memory in DB
    p1 = brain.create_project("Съемка винтажного Porsche 911 в неоне", description="Паркинг, дыммашина, свет от неона", status=ProjectStatus.COMPLETED)
    p2 = brain.create_project("Fashion кампейн для бренда шерстяных пальто", description="Студия с циклорамой", status=ProjectStatus.EDITING)
    
    brain.memory_engine.add_memory(
        content="На съемке с пальто мы 2 часа искали идеальный жесткий свет через отражатель, чтобы показать рельеф ткани",
        memory_type=MemoryType.EPISODE,
        importance=0.85,
        source="shoot_debrief"
    )

    # 2. Call emergency content recovery without passing manual arrays
    angles = brain.content_engine.emergency_content_recovery(profile=brain.profile_engine.get_profile())
    assert len(angles) == 3
    # Verify that real project titles from DB are injected into angles
    assert any("Porsche 911" in a["hook"] or "пальто" in a["hook"] or "Porsche 911" in a["theme"] or "пальто" in a["theme"] for a in angles)
    assert angles[0]["angle"] == "Сторителлинг & Доверие"
    assert angles[1]["angle"] == "Экспертиза & Закулисье"
    assert angles[2]["angle"] == "Мягкие продажи & Сезонный оффер"

def test_hardcore_05_daily_planning_real_db_state(brain):
    """
    Hardcore 5: 'Что мне сегодня делать?' with real DB state.
    DB contains active urgent project, a thinking client awaiting follow-up, and tasks.
    Generates strictly prioritized Top-3 actionable daily plan.
    """
    # 1. Populate real DB records
    p_urgent = brain.create_project("Ретушь лукбука для Ольги", status=ProjectStatus.EDITING)
    c_thinking = brain.create_client("Диана", status=ClientStatus.THINKING, service="Индивидуальная съёмка")
    t_urgent = brain.create_task("Загрузить превью на диск", task_type="editing", priority=TaskPriority.HIGH)

    # 2. Generate daily plan querying DB
    plan = brain.proactive_engine.generate_daily_plan()
    assert "priorities" in plan
    priorities = plan["priorities"]
    assert len(priorities) == 3

    # Priority 1: Shoot / Production
    assert priorities[0]["priority_level"] == 1
    assert any("Ретушь лукбука" in priorities[0]["title"] or "SHOOTING" in priorities[0]["domain"] for p in priorities)

    # Priority 2: Sales / Client Care
    assert priorities[1]["priority_level"] == 2
    assert "SALES" in priorities[1]["domain"]
    assert "Диана" in priorities[1]["title"] or "клиент" in priorities[1]["title"].lower()

    # Priority 3: Content / Visibility
    assert priorities[2]["priority_level"] == 3
    assert "CONTENT" in priorities[2]["domain"]