"""Specialized content planning with an anti-fabrication policy.

Generated drafts may propose ideas, but commercial facts (prices, availability,
conversion statistics, client results and personal experience) must come from
explicit context. Missing evidence is stated instead of invented.
"""
from typing import Dict, Any, List, Optional
from src.brain.models.profile import UserProfile


class ContentEngine:
    def __init__(self):
        pass

    def build_format_prompt(self, format_type: str, goal: str = "вовлечение", audience: str = "клиенты") -> str:
        fmt = format_type.lower()
        if "reel" in fmt or "рилс" in fmt:
            return ("ФОРМАТ: REELS\n1. ХУК (0-3 сек)\n2. ВИЗУАЛЬНЫЙ РЯД\n3. ТЕКСТ НА ЭКРАНЕ\n4. ГОЛОСОВОЙ ТЕКСТ\n5. АУДИО\n6. ОПИСАНИЕ И CTA")
        if "stori" in fmt or "сторис" in fmt:
            return ("ФОРМАТ: СЕРИЯ STORIES\nКадр 1: контекст\nКадр 2: развитие\nКадр 3 (Кульминация): результат\nКадр 4: польза\nКадр 5: интерактив и CTA")
        if "telegram" in fmt or "тг" in fmt or "канал" in fmt:
            return "ФОРМАТ: TELEGRAM-ПОСТ\nЗаголовок жирным, личная интонация, мысль или кейс, вопрос для обсуждения."
        return "ФОРМАТ: ЭКСПЕРТНЫЙ / СТОРИТЕЛЛИНГ ПОСТ\nЦЕПЛЯЮЩИЙ ХУК, ТЕЛО ПОСТА (история или боль клиента), вывод, CTA."

    @staticmethod
    def _evidence_note(value: str, label: str) -> str:
        return f"{label}: {value}" if value else f"{label}: требует подтверждения"

    def emergency_content_recovery(self, profile: Optional[UserProfile] = None,
                                   recent_projects: Optional[List[Dict[str, Any]]] = None,
                                   current_season: str = "текущий сезон",
                                   memories: Optional[List[str]] = None,
                                   use_llm: bool = False) -> List[Dict[str, Any]]:
        """Build three content angles without inventing availability or statistics."""
        if recent_projects is None:
            try:
                from src.brain.db import get_connection
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("SELECT name, description, status FROM projects ORDER BY created_at DESC LIMIT 3")
                recent_projects = [{"name": r["name"], "description": r["description"], "status": r["status"]} for r in cursor.fetchall()]
                conn.close()
            except Exception:
                recent_projects = []
        if memories is None:
            try:
                from src.brain.engines.memory_engine import MemoryEngine
                memories = [item.content for item, _ in MemoryEngine().retrieve_relevant_memories("съемка кадр бэкстейдж клиент история", limit=2)]
            except Exception:
                memories = []
        genres = ", ".join(profile.genres) if profile and profile.genres else "индивидуальные и портретные съемки"
        city = profile.city if profile and profile.city else "вашем городе"
        niche = profile.niche if profile and profile.niche else "авторская фотография"
        service = profile.services[0] if profile and profile.services else "индивидуальную съемку"
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                project_context = "; ".join(f"{p.get('name')} ({p.get('status')})" for p in recent_projects) or "нет подтверждённых проектов"
                memory_context = "; ".join(memories) or "нет подтверждённых заметок"
                prompt = (f"Ты контент-стратег фотографа. Используй только данные контекста, не выдумывай цены, даты, слоты, статистику, отзывы или личный опыт. Если факта нет, напиши 'требует подтверждения'. Ниша: {niche}. Жанры: {genres}. Город: {city}. Сезон: {current_season}. Проекты: {project_context}. Заметки: {memory_context}. Верни JSON-массив из 3 объектов с полями angle, format, hook, theme, cta.")
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200:
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, list) and len(parsed) >= 3 and all(isinstance(x, dict) for x in parsed[:3]):
                        return parsed[:3]
            except Exception:
                pass
        if recent_projects:
            project = recent_projects[0]
            first_hook = f"Что осталось за кадром проекта «{project.get('name', 'без названия')}»"
            first_theme = f"Закулисье проекта: {project.get('description') or 'разбор процесса и решений'}"
        elif memories:
            first_hook = f"Деталь со съёмки, которую обычно не замечают: «{memories[0][:70]}...»"
            first_theme = "История из подтверждённой заметки фотографа"
        else:
            first_hook = "Что помогает человеку расслабиться перед камерой"
            first_theme = "Практический рассказ без выдуманных цифр и чужих результатов"

        if recent_projects and len(recent_projects) > 1:
            project_2 = recent_projects[1]
            second_hook = f"Один источник света, несколько настроений: проект «{project_2.get('name', 'без названия')}»"
            second_theme = f"Разбор приёма и решений: {project_2.get('description') or 'по материалам съёмки'} для жанра {genres}."
        else:
            second_hook = "Один источник света, несколько настроений"
            second_theme = f"Разбор приёма для жанра {genres}; оборудование и результат нужно подтвердить по материалам съёмки."

        return [
            {"angle": "Сторителлинг & Доверие", "format": "Личный пост + кадры", "hook": first_hook,
             "theme": first_theme, "cta": "Напишите, какая часть подготовки к съёмке для вас самая сложная."},
            {"angle": "Экспертиза & Закулисье", "format": "Reels / backstage", "hook": second_hook,
             "theme": second_theme,
             "cta": "Сохраните идею и адаптируйте её под своё оборудование."},
            {"angle": "Мягкие продажи & Сезонный оффер", "format": "Stories + пост",
             "hook": f"Как подготовиться к {service} в {current_season}",
             "theme": "Покажите реальное предложение, цены и доступность только после проверки действующего прайса и календаря.",
             "cta": "Напишите, чтобы получить актуальные условия и проверить свободные даты."},
        ]

    def build_content_sprint_plan(self, profile: Optional[UserProfile] = None,
                                  days: int = 7, use_llm: bool = False) -> List[Dict[str, Any]]:
        if days <= 0 or days > 31:
            raise ValueError("days must be between 1 and 31")
        genres = ", ".join(profile.genres) if profile and profile.genres else "авторская фотография"
        city = profile.city if profile and profile.city else "вашем городе"
        service = profile.services[0] if profile and profile.services else "съёмки"
        # Keep the existing 4 anchor formats, but never claim confirmed dates.
        return [
            {"day": "Понедельник", "rubric": "Сторителлинг", "topic": f"История одного кадра в жанре {genres}", "format": "Post"},
            {"day": "Среда", "rubric": "Экспертиза", "topic": f"Что проверить в гардеробе для {genres}", "format": "Reels + Carousel"},
            {"day": "Пятница", "rubric": "Кейс / Доверие", "topic": f"Подбор локации в {city}, на подтверждённом примере", "format": "Stories Series"},
            {"day": "Воскресенье", "rubric": "Продажи", "topic": f"Актуальные условия на {service}, только после проверки прайса и календаря", "format": "Telegram / Post"},
        ]
