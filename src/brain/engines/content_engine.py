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
                                   use_llm: bool = True) -> List[Dict[str, Any]]:
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
                prompt = (
                    f"Ты контент-стратег и маркетолог для фотографов в стиле лучших методик продвижения.\n"
                    f"Ситуация: фотографу кажется, что 'нечего выложить'.\n"
                    f"Контекст: Ниша: {niche}. Жанры: {genres}. Город: {city}. Сезон: {current_season}.\n"
                    f"Проекты: {project_context}. Заметки: {memory_context}.\n\n"
                    f"Предложи 3 принципиально разных, живых и цепляющих угла подачи:\n"
                    f"1. Сторителлинг / Личный опыт со съёмки\n"
                    f"2. Закулисье / Экспертиза / Лайфхак для клиента\n"
                    f"3. Мягкий оффер / Закрытие страха клиента перед съёмкой\n\n"
                    f"Не выдумывай нереальные цифры и чужие отзывы.\n"
                    f"Верни JSON-массив из 3 объектов с полями angle, format, hook, theme, cta."
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
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
                                  days: int = 4, use_llm: bool = True) -> List[Dict[str, Any]]:
        """
        Generates a tailored multi-day content sprint for the photographer.
        Dynamically adapts to the requested number of days (1-31) and photographer's niche.
        """
        if days <= 0 or days > 31:
            raise ValueError("days must be between 1 and 31")
        genres = ", ".join(profile.genres) if profile and profile.genres else "авторская фотография"
        city = profile.city if profile and profile.city else "вашем городе"
        service = profile.services[0] if profile and profile.services else "съёмки"
        niche = profile.niche if profile and profile.niche else "фотография"
        tone = profile.tone if profile and profile.tone else "живой, экспертный, искренний"

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — контент-продюсер фотографа ({niche}, {genres}, город {city}, тон: {tone}).\n"
                    f"Составь мощный контент-план ровно на {days} дней для социальных сетей (Reels, Stories, Telegram, Посты).\n"
                    f"Рубрики должны гармонично чередоваться:\n"
                    f"- Сторителлинг и личный опыт\n"
                    f"- Экспертиза и помощь клиенту в подготовке\n"
                    f"- Бэкстейдж и процесс съемки\n"
                    f"- Кейсы и преодоление страхов ('не умею позировать', 'боюсь камеры')\n"
                    f"- Мягкие продажи и анонс свободных дат\n\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON массив ровно из {days} объектов:\n"
                    f"[\n"
                    f'  {{"day": "День 1", "rubric": "рубрика", "topic": "конкретная цепляющая тема", "format": "Reels / Post / Stories", "hook": "хук в первые 3 секунды", "cta": "призыв к действию"}}\n'
                    f"]"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, list) and len(parsed) >= min(days, 3):
                        return parsed[:days]
            except Exception:
                pass

        # Fallback multi-day generator
        rubric_rotation = [
            {"rubric": "Сторителлинг", "topic_tpl": "История одного кадра в жанре {genres}", "format": "Post"},
            {"rubric": "Экспертиза", "topic_tpl": "Что проверить в гардеробе для {genres}", "format": "Reels + Carousel"},
            {"rubric": "Кейс / Доверие", "topic_tpl": "Подбор локации в {city}, на подтверждённом примере", "format": "Stories Series"},
            {"rubric": "Продажи", "topic_tpl": "Актуальные условия на {service}, только после проверки прайса и календаря", "format": "Telegram / Post"},
            {"rubric": "Закулисье", "topic_tpl": "Один секрет световой схемы для {genres}", "format": "Reels"},
            {"rubric": "Анти-страх", "topic_tpl": "Что делать, если вы думаете, что не умеете позировать", "format": "Carousel Post"},
            {"rubric": "Интерактив", "topic_tpl": "Голосование за лучший образ недели в Stories", "format": "Stories"},
        ]

        result = []
        if days == 4:
            day_names = ["Понедельник", "Среда", "Пятница", "Воскресенье"]
        else:
            day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

        for idx in range(days):
            day_label = day_names[idx % len(day_names)] if days <= 7 else f"День {idx + 1}"
            template = rubric_rotation[idx % len(rubric_rotation)]
            topic = template["topic_tpl"].format(genres=genres, city=city, service=service)
            result.append({
                "day": day_label,
                "rubric": template["rubric"],
                "topic": topic,
                "format": template["format"]
            })
        return result
