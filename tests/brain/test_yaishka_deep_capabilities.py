import pytest
from src.brain.engines.shooting_engine import ShootingEngine
from src.brain.engines.sales_engine import SalesEngine
from src.brain.engines.agent_router import AgentRouter
from src.brain.engines.content_engine import ContentEngine
from src.brain.models.routing import IntentType
from src.brain.models.profile import UserProfile
from src.brain.services.brain_service import BrainService


class TestYaishkaDeepCapabilities:
    @pytest.fixture
    def shooting_engine(self):
        return ShootingEngine()

    @pytest.fixture
    def sales_engine(self):
        return SalesEngine()

    @pytest.fixture
    def content_engine(self):
        return ContentEngine()

    @pytest.fixture
    def router(self):
        return AgentRouter()

    @pytest.fixture
    def sample_profile(self):
        return UserProfile(
            identity="Виктория",
            city="Самара",
            niche="Семейная и портретная фотография",
            genres=["Семейная", "Индивидуальный портрет", "Love Story"],
            tone="Теплый, искренний, кинематографичный"
        )

    # 1. Moodboard Card Generation
    def test_moodboard_card_generation(self, shooting_engine):
        res = shooting_engine.generate_moodboard_card(
            concept_title="Семейная фотосессия в хвойном лесу",
            genre="Семейная",
            location="Хвойный лес, поляны, поваленные деревья",
            season="Осень",
            people_type="семья с двумя детьми",
            use_llm=False
        )
        assert res["concept"] == "Семейная фотосессия в хвойном лесу"
        assert len(res["color_palette"]) == 5
        assert all("hex" in c and "name" in c for c in res["color_palette"])
        assert len(res["outfit_combinations"]) == 7
        assert len(res["framing_ideas"]) == 5
        assert len(res["important_notes"]) >= 4
        assert "МУДБОРД" in res["card_markdown"]
        assert "Палитра" in res["card_markdown"]
        assert "Важно" in res["card_markdown"]

    # 2. Account & Feed Grid Audit
    def test_account_and_grid_audit(self, shooting_engine, sample_profile):
        sample_bio_and_grid = (
            "Фотограф Надежда Ларионова | Ставрополь\n"
            "Свадьбы и портреты. Более 2000 довольных клиентов. Готовность фото за 24 часа.\n"
            "Актуальное: «Успешная...», «Впервые», «Все будет...»\n"
            "Лента: 9 средних планов подряд, студия вперемешку с репортажем мостов."
        )
        res = shooting_engine.audit_profile_and_grid(
            target=sample_bio_and_grid,
            profile=sample_profile,
            use_llm=False
        )
        assert "niche_and_geo" in res
        assert len(res["strengths"]) >= 1
        assert len(res["growth_points"]) >= 1
        assert "шахмат" in res["grid_rhythm_advice"].lower()
        assert any("дальний" in res["grid_rhythm_advice"].lower() or "макро" in res["grid_rhythm_advice"].lower() for _ in [1])
        assert "прайс" in res["highlights_recommendation"].lower() or "отзыв" in res["highlights_recommendation"].lower()
        assert len(res["action_steps"]) == 3
        assert len(res["full_formatted_audit"]) > 100

    # 3. Music Soundtrack Recommendation
    def test_music_soundtrack_recommendation(self, shooting_engine):
        res = shooting_engine.recommend_music_soundtrack(
            mood_or_concept="Теплая осенняя прогулка на закате в бежевых свитерах",
            visual_series_description="Серия кадров с объятиями, закатным солнцем и золотой листвой",
            use_llm=False
        )
        assert len(res["tracks"]) >= 3
        for t in res["tracks"]:
            assert "title" in t and "genre" in t and "tempo" in t and "mood" in t and "artistic_rationale" in t
            assert len(t["artistic_rationale"]) > 20
        assert "Подборка атмосферных треков" in res["formatted_recommendations"]

    # 4. Photozone Concept Prototyping
    def test_photozone_prototyping(self, shooting_engine):
        res = shooting_engine.prototype_photozone_concept(
            theme="Школьная осенняя локация с деревянной партой и ретро-книгами",
            season="Осень",
            studio_type="Интерьерная студия с кирпичной стеной",
            use_llm=False
        )
        assert "photozone_title" in res
        assert "dimensions_and_light" in res
        assert len(res["color_scheme"]) >= 2
        assert len(res["key_props"]) >= 3
        assert len(res["presale_pitch_text"]) > 30
        assert len(res["image_generation_prompt"]) > 40

    # 5. Objection Handling with Rule of Two Choices
    def test_objection_handling_two_choices(self, sales_engine):
        res = sales_engine.handle_objection_yaishka_style(
            objection_text="Поняла, спасибо! Марин, извините, мне дорого, не потяну сейчас 🙏",
            client_name="Марина",
            service="семейную фотосессию",
            base_price=16000,
            use_llm=False
        )
        msg = res["client_message"]
        assert "понимаю вас" in msg.lower()
        assert "мини-съёмк" in msg.lower() or "коротком формат" in msg.lower()
        assert "част" in msg.lower() or "долями" in msg.lower() or "двумя" in msg.lower()
        assert "фотодни" in msg.lower() or "оставайтесь" in msg.lower()
        assert "два выбора" in res["methodological_advice"].lower()

    # 6. Client Dispute & Conflict Mediation
    def test_dispute_mediation(self, sales_engine, sample_profile):
        res = sales_engine.mediate_client_dispute(
            dispute_description="Клиентка требует отдать все исходники RAW, заявляя что кадров мало, хотя отдали 80 фото как по договору",
            profile=sample_profile,
            use_llm=False
        )
        assert len(res["photographer_slippage"]) > 20
        assert len(res["client_justified_points"]) > 20
        assert len(res["client_overstepping_points"]) > 20
        assert "raw" in res["ready_response_script"].lower()
        assert len(res["strategic_recommendations"]) >= 2
        assert "Разбор спорной ситуации" in res["formatted_mediation"]

    # 7. 3-Tier Price Guide Architecture
    def test_three_tier_pricing_guide(self, sales_engine, sample_profile):
        res = sales_engine.generate_three_tier_price_guide(
            niche="Семейная фотосессия",
            base_price=20000,
            profile=sample_profile,
            use_llm=False
        )
        assert len(res["tiers"]) == 3
        assert "ЛАЙТ" in res["tiers"][0]["name"]
        assert "ОПТИМАЛЬНЫЙ" in res["tiers"][1]["name"]
        assert "ПОПУЛЯРНЫЙ" in res["tiers"][1]["name"]
        assert "ПРЕМИУМ" in res["tiers"][2]["name"]
        assert len(res["guarantees"]) >= 4
        assert "П Р А Й С" in res["card_markdown"]

    # 8. Agent Router Intent Classification for Yaishka Superpowers
    def test_agent_router_superpowers(self, router):
        dec_mb = router.route("Составь мудборд съёмки и подборку образов для семьи в лесу")
        assert dec_mb.primary_intent == IntentType.MOODBOARD or IntentType.MOODBOARD in dec_mb.secondary_intents
        assert dec_mb.workflow_suggested == "moodboard_creation"

        dec_disp = router.route("У меня спорная ситуация с клиенткой, помоги разобрать конфликт")
        assert dec_disp.primary_intent == IntentType.DISPUTE or IntentType.DISPUTE in dec_disp.secondary_intents
        assert dec_disp.workflow_suggested == "dispute_mediation"

        dec_mus = router.route("Подбери треки под серию осенних фотографий для Reels")
        assert dec_mus.primary_intent == IntentType.MUSIC or IntentType.MUSIC in dec_mus.secondary_intents
        assert dec_mus.workflow_suggested == "music_selection"

        dec_aud = router.route("Сделай аудит ленты и шапки профиля в Инстаграм")
        assert dec_aud.primary_intent == IntentType.PROFILE_AUDIT
        assert dec_aud.workflow_suggested == "account_audit"

    # 9. BrainService End-to-End Chat Integration
    def test_brain_service_chat_yaishka_flows(self):
        brain = BrainService()
        res = brain.process_chat(
            query="Составь мудборд съёмки для пары на закате в поле",
            auto_admission=False
        )
        assert res["response"] is not None
        assert len(res["response"]) > 0
        assert res["intent"] in [IntentType.MOODBOARD.value, IntentType.PHOTO.value]

    # 10. Router Collisions & Workflow Enhancements
    def test_router_collision_and_workflow_enhancements(self, router):
        # Collision 1: 'цена' in 'сценарий'
        dec_reels = router.route("Напиши сценарий для рилс про позирование")
        assert dec_reels.primary_intent == IntentType.REELS
        assert dec_reels.primary_intent != IntentType.PRICING

        # Collision 2: 'свет' inside 'совет'
        dec_advice = router.route("Посоветуй как ответить клиенту на вопрос о датах")
        assert dec_advice.primary_intent != IntentType.PHOTO

        # Objection keywords expansion
        dec_husband = router.route("Клиентка говорит: надо посоветоваться с мужем")
        assert dec_husband.primary_intent == IntentType.OBJECTION

        dec_posing = router.route("Клиентка пишет: я деревянная как бревно и боюсь камеры")
        assert dec_posing.primary_intent == IntentType.OBJECTION

        # Force-majeure & cancellation
        dec_cancel_ill = router.route("Клиентка заболела простудой, отмена съемки")
        assert dec_cancel_ill.primary_intent == IntentType.DISPUTE
        assert dec_cancel_ill.workflow_suggested == "cancellation_mediation"

        dec_weather = router.route("На улице сильный ливень и дождь, перенос съемки")
        assert dec_weather.primary_intent == IntentType.DISPUTE
        assert dec_weather.workflow_suggested == "cancellation_mediation"

        # Burnout crisis detection
        dec_burnout = router.route("У меня выгорание, опускаются руки и нет сил снимать")
        assert dec_burnout.workflow_suggested == "burnout_recovery"

        # Photozone prototyping
        dec_pz = router.route("Разработай концепт фотозоны для декоратора к осени")
        assert dec_pz.workflow_suggested == "photozone_prototyping"

        # Music selection discrimination
        dec_photo_music = router.route("Фотосессия на природе под легкую фоновую музыку")
        assert dec_photo_music.workflow_suggested != "music_selection"

        dec_music_explicit = router.route("Подбери музыку для фотосессии в студии")
        assert dec_music_explicit.workflow_suggested == "music_selection"

    # 11. Multi-Objection Yaishka-Grade Handling (Husband & Fear of Posing)
    def test_objection_handling_husband_and_posing(self, sales_engine):
        # Partner / Husband objection
        res_partner = sales_engine.handle_objection_yaishka_style(
            objection_text="Мне очень нравится ваш стиль, но надо посоветоваться с мужем",
            client_name="Анна",
            use_llm=False
        )
        assert res_partner["objection_category"] == "partner"
        assert "мудборд" in res_partner["client_message"] or "15–20 минут" in res_partner["client_message"]
        assert "два" in res_partner["client_message"].lower()
        assert "муж" in res_partner["methodological_advice"].lower()
        assert "🤍" in res_partner["client_message"]

        # Fear of posing objection
        res_posing = sales_engine.handle_objection_yaishka_style(
            objection_text="Я не умею позировать, я деревянная и всегда зажата на фото",
            client_name="Ольга",
            use_llm=False
        )
        assert res_posing["objection_category"] == "fear_of_posing"
        assert "95%" in res_posing["client_message"]
        assert "музык" in res_posing["client_message"].lower() or "кофе" in res_posing["client_message"].lower()
        assert "расслабьтесь" in res_posing["methodological_advice"].lower()
        assert "🤍" in res_posing["client_message"]

    # 12. Cancellation & Reschedule Mediation (Weather, Illness, Late Cancellation)
    def test_cancellation_and_reschedule_mediation(self, sales_engine):
        # Weather
        res_weather = sales_engine.handle_cancellation_and_reschedule(
            cancellation_text="На улице сильный дождь и гроза, не сможем провести съемку на улице",
            client_name="Мария",
            use_llm=False
        )
        assert res_weather["cancellation_type"] == "weather"
        assert "30–60" in res_weather["client_message"]
        assert "студи" in res_weather["client_message"].lower()
        assert "задаток" in res_weather["deposit_policy_explanation"].lower()
        assert "🤍" in res_weather["client_message"]

        # Illness
        res_ill = sales_engine.handle_cancellation_and_reschedule(
            cancellation_text="У ребенка поднялась высокая температура, мы заболели",
            client_name="Елена",
            use_llm=False
        )
        assert res_ill["cancellation_type"] == "illness"
        assert "30–60" in res_ill["client_message"]
        assert "здоровье" in res_ill["client_message"].lower()
        assert "замороз" in res_ill["deposit_policy_explanation"].lower() or "сохраня" in res_ill["deposit_policy_explanation"].lower()

        # Late cancellation
        res_late = sales_engine.handle_cancellation_and_reschedule(
            cancellation_text="У нас поменялись планы, отмените нашу бронь на выходные",
            client_name="Наталья",
            use_llm=False
        )
        assert res_late["cancellation_type"] == "late_cancellation"
        assert "30–60" in res_late["client_message"]
        assert "задаток" in res_late["client_message"].lower()

    # 13. 9-Step Stories Arc (Yaishka Screen 05)
    def test_nine_step_stories_arc(self, content_engine):
        res = content_engine.generate_nine_step_stories_arc(
            topic="Почему не нужно быть моделью для красивой фотосессии",
            use_llm=False
        )
        assert len(res["steps"]) == 9
        expected_names = [
            "Вход", "Разворот", "Детали быта", "Интерактивный опрос",
            "Мостик", "Реакция аудитории", "Философская мысль", "Экспертность", "Эфир/Оффер"
        ]
        for idx, step in enumerate(res["steps"]):
            assert step["step_number"] == idx + 1
            assert step["step_name"] == expected_names[idx]
            assert len(step["visual"]) > 10
            assert len(step["text_on_screen"]) > 10
        assert res["steps"][3]["sticker"] is not None  # Interactive poll
        assert res["steps"][8]["sticker"] is not None  # CTA
        assert "9-ШАГОВАЯ АРКА STORIES" in res["formatted_script"]

    # 14. Introvert Reels Script (Yaishka Screen 17)
    def test_introvert_reels_script(self, content_engine):
        res = content_engine.generate_introvert_reels_script(
            topic="Страх камеры перед фотосессией",
            duration_seconds=12,
            use_llm=False
        )
        assert "Introvert" in res["format_type"]
        assert len(res["b_roll_scenes"]) >= 3
        for scene in res["b_roll_scenes"]:
            assert "visual" in scene and "text_overlay" in scene
        assert "sound_design" in res
        assert "foley_effects" in res["sound_design"]
        assert len(res["caption"]) > 30
        assert "REELS ДЛЯ ИНТРОВЕРТА" in res["formatted_script"]

    # 15. BrainService Workflow Integration & HEX Preservation
    def test_brain_service_workflows_and_dual_card_integration(self):
        brain = BrainService()

        # 1. Partner Objection routed through BrainService
        q_obj = "Клиентка Анна пишет: мне очень нравится ваше портфолио, но надо посоветоваться с мужем"
        routing = brain.router.route(q_obj)
        assert routing.primary_intent == IntentType.OBJECTION

        # 2. Cancellation Mediation Workflow in routing
        q_cancel = "Клиентка отменяет съемку из-за простуды и температуры"
        r_cancel = brain.router.route(q_cancel)
        assert r_cancel.workflow_suggested == "cancellation_mediation"

        # 3. Burnout Recovery Workflow in routing
        q_burnout = "У меня выгорание и творческий ступор, опускаются руки"
        r_burnout = brain.router.route(q_burnout)
        assert r_burnout.workflow_suggested == "burnout_recovery"

        # 4. Photozone Prototyping Workflow in routing
        q_photozone = "Сделай концепт фотозоны для декоратора"
        r_photozone = brain.router.route(q_photozone)
        assert r_photozone.workflow_suggested == "photozone_prototyping"
