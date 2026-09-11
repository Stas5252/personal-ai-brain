"""
User Profile Engine and Onboarding Workflow for Personal AI Brain.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any
from src.brain.db import get_connection
from src.brain.models.profile import UserProfile, OnboardingQuestion, OnboardingSession

ONBOARDING_QUESTIONS: List[OnboardingQuestion] = [
    OnboardingQuestion(
        index=1,
        id="identity",
        question="Кто ты и как тебя зовут / как называется твой бренд или проект?",
        field_target="identity",
        example="Алина Морозова / Студия Alina Visuals"
    ),
    OnboardingQuestion(
        index=2,
        id="niche",
        question="Чем конкретно ты занимаешься в фотографии и какая твоя ключевая специализация?",
        field_target="niche",
        example="Женский индивидуальный портрет, студийный контент для брендов и лаконичный минимализм"
    ),
    OnboardingQuestion(
        index=3,
        id="city",
        question="В каком городе и локациях ты преимущественно работаешь?",
        field_target="city",
        example="Москва, выезды в Санкт-Петербург"
    ),
    OnboardingQuestion(
        index=4,
        id="services",
        question="Какие основные услуги и съёмочные пакеты ты предлагаешь?",
        field_target="services",
        example="Индивидуальная фотосессия 'Экспресс', Пакет 'Премиум под ключ', Контент для экспертов"
    ),
    OnboardingQuestion(
        index=5,
        id="prices",
        question="Каковы твои цены и условия оплаты?",
        field_target="prices",
        example="Экспресс: 15 000 руб, Премиум: 35 000 руб, Брендовый контент-день: 50 000 руб"
    ),
    OnboardingQuestion(
        index=6,
        id="audience",
        question="Кто твой идеальный клиент (целевая аудитория и типажи)?",
        field_target="audience",
        example="Девушки 25-40 лет, предпринимательницы, ценящие эстетику, естественность и комфорт на съемке"
    ),
    OnboardingQuestion(
        index=7,
        id="visual_preferences",
        question="Как бы ты описала свой визуальный стиль, работу со светом и цветом?",
        field_target="visual_preferences",
        example="Естественный мягкий свет, глубокие тени, чистые пленочные цвета, минимализм, без вульгарной ретуши"
    ),
    OnboardingQuestion(
        index=8,
        id="tone_and_sales",
        question="Как ты хочешь общаться с аудиторией и клиентами (тон, продажи, подача)?",
        field_target="tone",
        example="Теплый, поддерживающий, профессиональный, без навязчивого 'впаривания' и без снобизма"
    ),
    OnboardingQuestion(
        index=9,
        id="forbidden",
        question="Что тебе категорически не нравится? (запретные темы, раздражающие слова, штампы)",
        field_target="forbidden_words",
        example="Не использовать: 'красотка', 'волшебные кадры', 'уникальное предложение', агрессивные скидки"
    ),
    OnboardingQuestion(
        index=10,
        id="goals",
        question="Какие главные цели сейчас стоят перед твоим проектом на ближайшие полгода?",
        field_target="goals",
        example="Поднять средний чек, запустить регулярные фотодни раз в месяц, собрать портфолио для журналов"
    )
]

class ProfileEngine:
    def __init__(self):
        pass

    def get_profile(self) -> UserProfile:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT data_json FROM user_profile WHERE id = 'default'")
        row = c.fetchone()
        conn.close()
        if row:
            data = json.loads(row["data_json"])
            return UserProfile(**data)
        return UserProfile()

    def save_profile(self, profile: UserProfile) -> UserProfile:
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO user_profile (id, data_json, updated_at)
        VALUES ('default', ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """, (profile.model_dump_json(), profile.updated_at))
        conn.commit()
        conn.close()
        return profile

    def start_onboarding(self) -> Tuple[OnboardingSession, OnboardingQuestion]:
        session_id = str(uuid.uuid4())
        session = OnboardingSession(session_id=session_id, current_step=0, answers={})
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO onboarding_sessions (session_id, step, answers_json, completed, created_at)
        VALUES (?, 0, '{}', 0, ?)
        """, (session_id, session.created_at))
        conn.commit()
        conn.close()
        return session, ONBOARDING_QUESTIONS[0]

    def answer_onboarding(self, session_id: str, answer_text: str) -> Dict[str, Any]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT step, answers_json, completed FROM onboarding_sessions WHERE session_id = ?", (session_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Onboarding session {session_id} not found")
        step = row["step"]
        answers = json.loads(row["answers_json"])
        current_q = ONBOARDING_QUESTIONS[step]
        answers[current_q.id] = answer_text.strip()
        next_step = step + 1
        if next_step < len(ONBOARDING_QUESTIONS):
            c.execute("""
            UPDATE onboarding_sessions
            SET step = ?, answers_json = ?
            WHERE session_id = ?
            """, (next_step, json.dumps(answers, ensure_ascii=False), session_id))
            conn.commit()
            conn.close()
            return {
                "completed": False,
                "next_question": ONBOARDING_QUESTIONS[next_step].model_dump(),
                "progress": f"{next_step}/{len(ONBOARDING_QUESTIONS)}"
            }
        else:
            c.execute("""
            UPDATE onboarding_sessions
            SET step = ?, answers_json = ?, completed = 1
            WHERE session_id = ?
            """, (next_step, json.dumps(answers, ensure_ascii=False), session_id))
            conn.commit()
            conn.close()
            profile = self._build_profile_from_answers(answers)
            self.save_profile(profile)
            return {
                "completed": True,
                "profile": profile.model_dump(),
                "progress": f"{len(ONBOARDING_QUESTIONS)}/{len(ONBOARDING_QUESTIONS)}"
            }

    def _build_profile_from_answers(self, answers: Dict[str, str]) -> UserProfile:
        raw_prices = answers.get("prices", "")
        prices_dict = {}
        for part in raw_prices.replace(";", "\n").split("\n"):
            if ":" in part:
                k, v = part.split(":", 1)
                prices_dict[k.strip()] = v.strip()
            elif part.strip():
                prices_dict[f"Пакет {len(prices_dict)+1}"] = part.strip()
        services_list = [s.strip() for s in answers.get("services", "").replace(";", ",").split(",") if s.strip()]
        forbidden_raw = answers.get("forbidden", "")
        forbidden_words = []
        forbidden_topics = []
        for item in forbidden_raw.replace(";", ",").split(","):
            cleaned = item.replace("Не использовать:", "").replace("не использовать", "").strip().strip("'\"")
            if cleaned:
                if len(cleaned.split()) > 3:
                    forbidden_topics.append(cleaned)
                else:
                    forbidden_words.append(cleaned)
        goals_list = [g.strip() for g in answers.get("goals", "").replace(";", ",").split(",") if g.strip()]
        return UserProfile(
            identity=answers.get("identity", ""),
            profession="Фотограф",
            city=answers.get("city", ""),
            niche=answers.get("niche", ""),
            services=services_list,
            prices=prices_dict,
            audience=answers.get("audience", ""),
            clients=answers.get("audience", ""),
            goals=goals_list,
            business_stage="Действующий коммерческий фотограф",
            tone=answers.get("tone_and_sales", "Теплый, поддерживающий, профессиональный"),
            language="ru",
            preferred_models=["models/gemini-2.5-flash", "models/gemini-3.5-flash"],
            content_preferences="Естественный бэкстейдж, экспертные посты без клише, разборы съемок",
            sales_preferences=answers.get("tone_and_sales", "Мягкие продажи через ценность и портфолио"),
            visual_preferences=answers.get("visual_preferences", ""),
            brand_preferences="Эстетика, надежность, открытость",
            forbidden_topics=forbidden_topics,
            forbidden_words=forbidden_words,
            updated_at=datetime.now(timezone.utc).isoformat()
        )

    def parse_profile_from_freetext(self, text: str) -> UserProfile:
        """Parses a free-form introduction through the configured LLM."""
        res = self.extract_profile_from_freeform(text)
        return res["profile"]

    def extract_profile_from_freeform(self, text: str) -> Dict[str, Any]:
        """
        Parses a free-form introduction or voice note into structured UserProfile via LLM,
        identifies missing critical fields, indexes facts into memory, and generates
        a warm, personal conversational response in the style of a dedicated photo-marketer.
        """
        from src.brain.services.llm_provider import LLMProvider
        llm = LLMProvider()
        prompt = (
            "Ты — личный ИИ-напарник и маркетолог для фотографов (как в лучших школах фотобизнеса).\n"
            "Фотограф рассказывает о себе, своём опыте, ценах, клиентах и целях:\n"
            f"«««\n{text}\n»»»\n\n"
            "Заполни карточку профиля фотографа на основе этого рассказа.\n"
            "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект (без markdown блоков ```json):\n"
            "{\n"
            '  "identity": "Имя фотографа или бренд (например: Алина Морозова)",\n'
            '  "city": "Город (например: Москва, Санкт-Петербург, Ростов-на-Дону)",\n'
            '  "niche": "Ключевая специализация (например: Женский портрет, Свадьбы, Семейная съемка, Контент)",\n'
            '  "genres": ["список жанров"],\n'
            '  "services": ["список пакетов/услуг"],\n'
            '  "pricing": {"Экспресс": "10000", "Стандарт": "20000"},\n'
            '  "audience": "Кто целевая аудитория (например: девушки 25-35, эксперты, пары)",\n'
            '  "tone": "Желаемый тон (например: теплый, заботливый, экспертный)",\n'
            '  "forbidden_words": ["стоп-слова и раздражающие штампы"],\n'
            '  "goals": ["цели: поднять чек, набрать заказов, упаковать рилс"]\n'
            "}"
        )
        extracted_data = {}
        try:
            status_code, resp_text, _, _ = llm.chat_completion(
                [{"role": "user", "content": prompt}], temperature=0.2)
            if status_code == 200:
                clean = resp_text.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                extracted_data = json.loads(clean)
        except Exception as e:
            print(f"[!] Error extracting profile via LLM: {e}")

        # Rule-based fallback extraction if LLM didn't return values (e.g. offline or test mode)
        import re
        if not extracted_data.get("identity"):
            m_name = re.search(r"меня зовут\s+([А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+)?)", text, re.IGNORECASE)
            if not m_name:
                m_name = re.search(r"(?:\bя\s*[—–-]\s*|\bя\s+)([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)", text)
            if m_name and m_name.group(1).lower() not in ["фотограф", "снимаю", "из", "в", "начинающий", "коммерческий"]:
                extracted_data["identity"] = m_name.group(1).strip()
        if not extracted_data.get("city"):
            m_city = re.search(r"(?:в|из|город(?:е)?)\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", text)
            if m_city:
                c_val = m_city.group(1).strip()
                c_low = c_val.lower()
                if "москв" in c_low:
                    extracted_data["city"] = "Москва"
                elif "питер" in c_low or "петербург" in c_low:
                    extracted_data["city"] = "Санкт-Петербург"
                elif "самар" in c_low:
                    extracted_data["city"] = "Самара"
                elif "казан" in c_low:
                    extracted_data["city"] = "Казань"
                elif "новосибирск" in c_low:
                    extracted_data["city"] = "Новосибирск"
                elif "екатеринбург" in c_low:
                    extracted_data["city"] = "Екатеринбург"
                elif c_val.endswith("е") or c_val.endswith("ы"):
                    extracted_data["city"] = c_val[:-1] + "а"
                else:
                    extracted_data["city"] = c_val
        if not extracted_data.get("niche"):
            m_niche = re.search(r"(?:снимаю|ниша|специализаци[яи]|фотографирую)\s+([^.,;\n]+)", text, re.IGNORECASE)
            if m_niche:
                extracted_data["niche"] = m_niche.group(1).strip()

        current = self.get_profile()
        # The extraction prompt never returns visual, content, sales or brand
        # preferences, so those are carried over from the stored profile.
        # Rebuilding the model without them used to silently erase the visual
        # style that image generation reads and the forbidden topics list.
        updated = UserProfile(
            identity=extracted_data.get("identity") or current.identity,
            profession="Фотограф",
            city=extracted_data.get("city") or current.city,
            niche=extracted_data.get("niche") or current.niche,
            genres=extracted_data.get("genres") or current.genres,
            services=extracted_data.get("services") or current.services,
            prices=extracted_data.get("pricing") or current.prices,
            pricing=extracted_data.get("pricing") or current.pricing,
            audience=extracted_data.get("audience") or current.audience,
            clients=extracted_data.get("audience") or current.clients,
            goals=extracted_data.get("goals") or current.goals,
            business_stage=current.business_stage or "Действующий коммерческий фотограф",
            tone=extracted_data.get("tone") or current.tone or "Теплый, поддерживающий, профессиональный",
            language=current.language,
            preferred_models=current.preferred_models,
            content_preferences=current.content_preferences,
            sales_preferences=current.sales_preferences,
            visual_preferences=current.visual_preferences,
            brand_preferences=current.brand_preferences,
            forbidden_topics=current.forbidden_topics,
            forbidden_words=extracted_data.get("forbidden_words") or current.forbidden_words,
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        saved = self.save_profile(updated)

        # Index recognized facts into persistent memory
        try:
            from src.brain.engines.memory_engine import MemoryEngine
            from src.brain.models.memory import MemoryType
            me = MemoryEngine()
            if saved.identity:
                me.add_memory(content=f"Фотографа зовут: {saved.identity}", memory_type=MemoryType.CORE_FACT, importance=1.0)
            if saved.niche:
                me.add_memory(content=f"Специализация и ниша: {saved.niche} в городе {saved.city or 'не указан'}", memory_type=MemoryType.CORE_FACT, importance=0.95)
            if saved.goals:
                me.add_memory(content=f"Цели фотографа: {', '.join(saved.goals)}", memory_type=MemoryType.GOAL, importance=0.9)
        except Exception:
            pass

        # Check what critical info is still missing
        missing = []
        if not saved.identity:
            missing.append("имя")
        if not saved.niche:
            missing.append("ниша/специализация")
        if not saved.city:
            missing.append("город")
        if not saved.prices and not saved.pricing:
            missing.append("цены / средний чек")

        # Build friendly conversational summary
        name_str = saved.identity or "коллега"
        niche_str = saved.niche or "фотография"
        city_str = f" в {saved.city}" if saved.city else ""
        
        if not missing or (saved.identity and saved.niche):
            clarification = None
            summary = (
                f"Очень приятно познакомиться, {name_str}! 🤝\n\n"
                f"Я всё запомнил:\n"
                f"• Ниша: {niche_str}{city_str}\n"
                f"• Стиль и тон: {saved.tone}\n"
            )
            if saved.prices:
                price_lines = ", ".join([f"{k}: {v}" for k, v in list(saved.prices.items())[:3]])
                summary += f"• Текущий прайс: {price_lines}\n"
            if saved.goals:
                summary += f"• Главные цели: {', '.join(saved.goals)}\n"
            summary += (
                "\nТеперь я твой карманный маркетолог. С чем помогу прямо сейчас?\n"
                "🎬 Придумать цепляющие Reels или сценарий сторис\n"
                "💬 Разобрать переписку с клиентом (например, если написали 'дорого' или 'мы подумаем')\n"
                "🎨 Собрать мудборд или схему света для съёмки\n"
                "🏷️ Оформить понятный прайс\n\n"
                "Или просто наговори голосовым любую рабочую задачу обычным языком!"
            )
        else:
            clarification = f"Подскажи ещё, в каком городе ты в основном работаешь и какая твоя ключевая специализация?"
            summary = (
                f"Привет, {name_str}! Начало положено. {clarification}"
            )

        return {
            "profile": saved,
            "extracted_data": extracted_data,
            "missing_critical_fields": missing,
            "friendly_summary": summary,
            "next_clarifying_question": clarification,
            "is_complete": len(missing) <= 1
        }
