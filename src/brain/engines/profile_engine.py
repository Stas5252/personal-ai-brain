"""
User Profile Engine and Onboarding Workflow for Personal AI Brain.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
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
        # Default empty profile
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
            # Advance to next question
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
            # Interview is complete! Synthesize profile
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
        # Parse prices into dict if formatted as text
        raw_prices = answers.get("prices", "")
        prices_dict = {}
        for part in raw_prices.replace(";", "\n").split("\n"):
            if ":" in part:
                k, v = part.split(":", 1)
                prices_dict[k.strip()] = v.strip()
            elif part.strip():
                prices_dict[f"Пакет {len(prices_dict)+1}"] = part.strip()
                
        # Parse services
        services_list = [s.strip() for s in answers.get("services", "").replace(";", ",").split(",") if s.strip()]
        
        # Parse forbidden words/topics
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
                    
        # Parse goals
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
