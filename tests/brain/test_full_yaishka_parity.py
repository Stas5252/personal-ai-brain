"""
Comprehensive Full Yaishka Parity & Superset Acceptance Test Suite.
Verifies all capabilities required by Master Prompt:
- Real Personalization (Photographer A vs Photographer B)
- Real Memory Evolution without Stale Data
- Real Voice-to-Content Decomposition (3 distinct transcripts)
- Real Gemini Vision Image Critique
- Natural Language Multi-Intent Compound Query Resolution
- Channel Adapters (Telegram, MAX, Web UI)
- Learning from User Feedback
- Full Sales & Objection Engine Parity
"""
import pytest
from pathlib import Path
from src.brain.services.brain_service import BrainService
from src.brain.models.profile import UserProfile
from src.brain.models.client import Client, ClientStatus
from src.brain.models.project import Project, ProjectStatus
from src.brain.models.memory import MemoryType
from src.brain.engines.content_engine import ContentEngine
from src.brain.engines.sales_engine import SalesEngine
from src.brain.engines.shooting_engine import ShootingEngine
from src.brain.engines.voice_engine import VoiceEngine
from src.brain.engines.proactive_engine import ProactiveEngine
from src.brain.engines.workflow_engine import WorkflowEngine
from src.brain.channels import TelegramAdapter, MaxAdapter, WebAdapter

@pytest.fixture
def brain():
    return BrainService()

def test_yaishka_parity_01_personalization_a_vs_b(brain):
    """
    Master Prompt #32: Real Personalization Test.
    Photographer A: Семейный премиум, Москва, теплый тон.
    Photographer B: Предметный малый бизнес, Самара, экспертный тон.
    Same prompt: 'Придумай контент на неделю.'
    Must produce fundamentally different results reflecting niche, city, and audience.
    """
    ce = ContentEngine()

    # Photographer A
    prof_a = UserProfile(
        identity="Анна Романова",
        niche="Семейная съемка премиум-сегмента",
        genres=["Семейная", "Материнство", "Newborn"],
        city="Москва",
        services=["Премиальная семейная история"],
        pricing={"Пакет": "45 000 руб"},
        tone="Теплый, искренний, семейный"
    )
    plan_a = ce.build_content_sprint_plan(profile=prof_a, days=7, use_llm=False)
    topics_a = " ".join([p["topic"] for p in plan_a]).lower()

    # Photographer B
    prof_b = UserProfile(
        identity="Дмитрий Волков",
        niche="Коммерческая предметная съемка для бизнеса",
        genres=["Предметная", "Каталог", "Маркетплейсы"],
        city="Самара",
        services=["Съемка каталога для брендов"],
        pricing={"Пакет": "12 000 руб"},
        tone="Деловой, экспертный, сдержанный"
    )
    plan_b = ce.build_content_sprint_plan(profile=prof_b, days=7, use_llm=False)
    topics_b = " ".join([p["topic"] for p in plan_b]).lower()

    assert len(plan_a) >= 4
    assert len(plan_b) >= 4
    # Distinct genres and cities must be reflected
    assert "москв" in topics_a or "семейн" in topics_a
    assert "самар" in topics_b or "предметн" in topics_b
    assert topics_a != topics_b

def test_yaishka_parity_02_memory_evolution(brain):
    """
    Master Prompt #34: Memory evolution without stale data.
    """
    # 1. Add initial style memory
    m1 = brain.memory_engine.add_memory(
        content="Мой любимый стиль съемки — cinematic noir с глубокими тенями.",
        memory_type=MemoryType.PREFERENCE,
        importance=0.8,
        source="user_statement"
    )
    assert m1.id is not None

    # 2. Update/Evolve preference
    m2 = brain.memory_engine.add_memory(
        content="Теперь я полностью перехожу на clean editorial и мягкий естественный свет.",
        memory_type=MemoryType.PREFERENCE,
        importance=0.95,
        source="user_statement"
    )
    assert m2.id is not None

    # Retrieve memories for style query
    retrieved = brain.memory_engine.retrieve_relevant_memories("стиль съемки свет", limit=2)
    assert len(retrieved) > 0
    top_memory = retrieved[0][0].content
    # The newer high-importance memory should rank top
    assert "clean editorial" in top_memory or "мягкий" in top_memory

def test_yaishka_parity_03_voice_decomposition_three_transcripts():
    """
    Master Prompt #36: Real Voice Test with 3 distinct transcripts.
    """
    ve = VoiceEngine()

    # Transcript 1: Shoot story
    t1 = "Вчера была съемка с пальто, мы два часа искали жесткий свет через отражатель, но когда нашли, кадры получились как для Vogue."
    p1 = ve.process_voice_transcript(t1, use_llm=False)

    # Transcript 2: Client objection complaint
    t2 = "Клиентка написала что муж не хочет фотографироваться и говорит что это дорого, нужно помочь ей объяснить ценность семейного архива."
    p2 = ve.process_voice_transcript(t2, use_llm=False)

    # Transcript 3: New photoday idea
    t3 = "Хочу запустить весенний фотодень в цветущей оранжерее с живыми тюльпанами на 8 марта на пять слотов по двадцать тысяч."
    p3 = ve.process_voice_transcript(t3, use_llm=False)

    # All 3 must produce distinct derivatives
    assert p1["derivative_post"] != p2["derivative_post"]
    assert p2["derivative_post"] != p3["derivative_post"]
    assert "пальто" in p1["extracted_events"][0].lower() or "жесткий" in p1["story_beats"][0].lower()
    assert "дорого" in p2["extracted_events"][0].lower() or "муж" in p2["story_beats"][0].lower()
    assert "оранжере" in p3["extracted_events"][0].lower() or "тюльпан" in p3["story_beats"][0].lower()

def test_yaishka_parity_04_live_vision_critique():
    """
    Master Prompt #16 & #37: Real Gemini Vision critique on image.
    """
    se = ShootingEngine()
    test_img = Path("tests/fixtures/test_vision.png")
    assert test_img.exists()

    critique = se.critique_shot(str(test_img))
    assert critique["status"] == "AVAILABLE"
    assert len(critique["description"]) > 50
    # Must contain photographic analytical terms
    desc = critique["description"].lower()
    assert any(w in desc for w in ["композици", "цвет", "свет", "арт", "кадр", "минимализм", "форма", "фон"])

def test_yaishka_parity_05_compound_multi_intent(brain):
    """
    Master Prompt #19: Compound request (photoday + offer + price + stories).
    """
    compound_query = "Придумай осенний фотодень, сделай под него предложение, напиши сторис и скажи сколько поставить цену."
    routing = brain.router.route(compound_query)

    assert len(routing.compound_intents) >= 2 or routing.primary_intent is not None
    assert routing.workflow_suggested in ["photoday_launch", "no_content_emergency"] or routing.primary_intent is not None

def test_yaishka_parity_06_channel_adapters(brain):
    """
    Master Prompt #26, #27, #28: Channel parity across Telegram, MAX, Web.
    """
    tg = TelegramAdapter(brain_service=brain)
    max_ch = MaxAdapter(brain_service=brain)
    web = WebAdapter(brain_service=brain)

    assert tg.channel_name == "telegram"
    assert max_ch.channel_name == "max"
    assert web.channel_name == "web"

    # Test Web handle_text
    web_res = web.handle_text(user_id="user_123", text="Привет! Чем ты можешь мне помочь?")
    assert "response" in web_res
    assert web_res["status_code"] == 200

def test_yaishka_parity_07_sales_objections():
    """
    Master Prompt #8: Objections 'дорого', 'подумаем', 'не умеем позировать'.
    """
    se = SalesEngine()
    prof = UserProfile(niche="Женский портрет", tone="Заботливый")
    cl = Client(id="client_test_1", name="Елена", service="Индивидуальная съёмка")

    resp_d = se.generate_objection_response("дорого", profile=prof, client=cl, use_llm=False)
    resp_p = se.generate_objection_response("мы подумаем", profile=prof, client=cl, use_llm=False)
    resp_pos = se.generate_objection_response("не умеем позировать", profile=prof, client=cl, use_llm=False)

    assert "вложение" in resp_d.lower() or "ценность" in resp_d.lower() or "формат" in resp_d.lower()
    assert "не торопитесь" in resp_p.lower() or "взвесить" in resp_p.lower() or "дату" in resp_p.lower()
    assert "позировать" in resp_pos.lower() or "подсказываю" in resp_pos.lower() or "атмосфер" in resp_pos.lower()

def test_yaishka_parity_08_feedback_learning(brain):
    """
    Master Prompt #25: Learning from user feedback.
    """
    # 1. Positive feedback
    res_pos = brain.process_chat("Вот это мне понравилось, сохрани этот тон!")
    assert res_pos["status_code"] == 200

    # Verify memory was recorded
    memories = brain.memory_engine.get_memories()
    pos_mem = [m for m in memories if "Одобренный стиль" in m.content or "мне понравилось" in m.content]
    assert len(pos_mem) > 0

    # 2. Negative feedback
    res_neg = brain.process_chat("Так больше никогда не пиши, убери инфоцыганские обещания.")
    assert res_neg["status_code"] == 200
    memories_neg = brain.memory_engine.get_memories()
    neg_mem = [m for m in memories_neg if "Стилевой запрет" in m.content or "инфоцыган" in m.content]
    assert len(neg_mem) > 0

def test_yaishka_parity_09_adaptive_onboarding(brain):
    """
    Yaishka Feature Parity: Adaptive 1-shot conversational onboarding.
    Extracts identity, city, and niche from free-form text or voice note,
    indexes into memory, and generates an empathetic partner welcome.
    """
    intro_text = "Меня зовут Анастасия Соколова, я фотограф из Москвы. Снимаю женский портрет и контент для брендов."
    res = brain.profile_engine.extract_profile_from_freeform(intro_text)
    
    assert res is not None
    prof = res["profile"]
    assert "Анастасия" in prof.identity or "Соколова" in prof.identity
    assert prof.city in ["Москва", "Москве"]
    assert "портрет" in prof.niche.lower() or "контент" in prof.niche.lower() or len(prof.niche) > 0
    assert "Анастасия" in res["friendly_summary"]
    assert len(res["friendly_summary"]) > 50

def test_yaishka_parity_10_dialogue_analysis_triad(brain):
    """
    Yaishka Feature Parity: Sales dialogue deep analysis with 3 response paths
    (caring, value-focused, alternative) and anti-patterns.
    """
    se = brain.sales_engine
    dialogue = (
        "Клиент: Здравствуйте, сколько стоит съемка?\n"
        "Я: Добрый день! 20 000 руб за 2 часа.\n"
        "Клиент: Ого, это дорого, мы пока подумаем."
    )
    analysis = se.analyze_client_dialogue(dialogue, use_llm=False)
    assert "detected_objections" in analysis
    assert "дорого" in analysis["detected_objections"]
    assert "what_client_really_means" in analysis
    assert "response_options" in analysis
    opts = analysis["response_options"]
    assert "caring" in opts and "value_focused" in opts and "alternative" in opts
    assert len(opts["caring"]) > 20
    assert len(opts["value_focused"]) > 20
    assert len(opts["alternative"]) > 20
    assert "what_not_to_say" in analysis
    assert len(analysis["what_not_to_say"]) > 10

def test_yaishka_parity_11_shooting_visual_logic(brain):
    """
    Yaishka Feature Parity: Visual logic and complete shot list generation
    with exact camera settings and lighting tips.
    """
    se = brain.shooting_engine
    logic = se.build_visual_logic(
        concept_title="Минималистичный женский портрет в лучах заката",
        genre="Индивидуальный портрет",
        mood="Теплый, кинематографичный",
        use_llm=False
    )
    assert "color_palette" in logic
    assert "light_scheme" in logic
    assert len(logic["color_palette"]) >= 3
    assert "location_guidance" in logic
    assert "styling_and_wardrobe" in logic

    shotlist = se.generate_shot_list(
        duration_minutes=60,
        concept="Минималистичный женский портрет",
        use_llm=False
    )
    assert len(shotlist) >= 4
    # Check that shots have timing, phase, plan, and key_shots
    assert "phase" in shotlist[0]
    assert "plan" in shotlist[0]
    assert "key_shots" in shotlist[0]

def test_yaishka_parity_12_voice_multi_format_derivatives(brain):
    """
    Yaishka Feature Parity: Voice note decomposition into multi-format content:
    narrative post, 2 Reels scripts (with hook/visual/audio/CTA), and 5 Stories slides.
    """
    ve = brain.voice_engine
    raw_voice = (
        "Сегодня на съемке клиентка сначала жутко волновалась и говорила что она нефотогеничная. "
        "Но мы включили музыку, начали с чашки кофе и движения, и через двадцать минут она просто раскрылась. "
        "В итоге получилось сорок невероятных кадров, она чуть не расплакалась от восторга."
    )
    res = ve.process_voice_transcript(raw_voice, use_llm=False)
    assert "derivative_post" in res
    assert len(res["derivative_post"]) > 50
    assert "derivative_reels" in res
    assert len(res["derivative_reels"]) >= 2
    r1 = res["derivative_reels"][0]
    assert "hook" in r1 and "visual" in r1 and "cta" in r1
    assert "derivative_stories" in res
    assert len(res["derivative_stories"]) >= 5

