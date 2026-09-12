"""Content planning with fail-closed commercial facts.

Ideas may be generated, but prices, availability, statistics, reviews, client
results, and personal experience are emitted only when present in input data.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.brain.models.profile import UserProfile


class ContentEngine:
    def build_format_prompt(self, format_type: str, goal: str = "вовлечение", audience: str = "клиенты") -> str:
        value = format_type.lower()
        if any(word in value for word in ("интроверт", "b-roll", "эстетик")):
            return (
                "ФОРМАТ: REELS БЕЗ ГОВОРЯЩЕЙ ГОЛОВЫ\n"
                "1. B-ROLL: руки, камера, свет и детали\n"
                "2. ТЕКСТ НА ЭКРАНЕ\n3. ЗВУКОВОЙ ДИЗАЙН\n"
                "4. ХРОНОМЕТРАЖ 7–15 СЕК\n5. ТЕКСТ И CTA"
            )
        if any(word in value for word in ("арка", "9", "яишка")):
            return (
                "ФОРМАТ: 9-ШАГОВАЯ АРКА STORIES\n"
                "Вход → разворот → подтверждённая деталь → опрос → мостик → "
                "реальная реакция или вопрос → мысль → экспертиза → проверенный оффер"
            )
        if "reel" in value or "рилс" in value:
            return "ФОРМАТ: REELS\nХук → визуал → текст → голос → звук → CTA"
        if "stori" in value or "сторис" in value:
            return "ФОРМАТ: STORIES\nКонтекст → развитие → результат → польза → CTA"
        if any(word in value for word in ("telegram", "тг", "канал")):
            return "ФОРМАТ: TELEGRAM-ПОСТ\nЗаголовок, проверенная история или мысль, вопрос."
        return "ФОРМАТ: ПОСТ\nХук, подтверждённая история или польза, вывод, CTA."

    @staticmethod
    def _json_response(prompt: str, temperature: float = 0.7):
        try:
            from src.brain.services.llm_provider import LLMProvider

            status, text, _, _ = LLMProvider().chat_completion(
                [{"role": "user", "content": prompt}], temperature=temperature
            )
            if status != 200 or text.strip().startswith("Тестовый ответ"):
                return None
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return json.loads(cleaned)
        except Exception:
            return None

    def emergency_content_recovery(
        self,
        profile: Optional[UserProfile] = None,
        recent_projects: Optional[List[Dict[str, Any]]] = None,
        current_season: str = "текущий сезон",
        memories: Optional[List[str]] = None,
        use_llm: bool = True,
    ) -> List[Dict[str, Any]]:
        projects = list(recent_projects or [])
        notes = list(memories or [])
        genres = ", ".join(profile.genres) if profile and profile.genres else "фотография"
        service = profile.services[0] if profile and profile.services else "съёмка"
        if use_llm:
            parsed = self._json_response(
                "Создай JSON-массив из трёх контент-идей для фотографа. "
                "Поля: angle, format, hook, theme, cta. Не выдумывай цены, даты, "
                "слоты, статистику, отзывы, проекты и личный опыт. "
                f"Жанры: {genres}. Сезон: {current_season}. "
                f"Подтверждённые проекты: {projects or 'нет'}. "
                f"Подтверждённые заметки: {notes or 'нет'}."
            )
            if isinstance(parsed, list) and len(parsed) >= 3:
                return parsed[:3]

        first = projects[0] if projects else None
        first_hook = (
            f"Что осталось за кадром проекта «{first.get('name', 'без названия')}»"
            if first
            else "Что реально помогает человеку расслабиться перед камерой"
        )
        first_theme = (
            first.get("description") or "Подтверждённые решения из проекта"
            if first
            else "Практический разбор без выдуманного кейса"
        )
        return [
            {
                "angle": "Сторителлинг",
                "format": "Пост + реальные кадры",
                "hook": first_hook,
                "theme": first_theme,
                "cta": "Спросите аудиторию, что ей сложнее всего перед съёмкой.",
            },
            {
                "angle": "Экспертиза",
                "format": "Reels / backstage",
                "hook": "Один приём, который стоит проверить на следующей съёмке",
                "theme": f"Покажите реальный приём для жанра {genres}; не приписывайте результат без примера.",
                "cta": "Предложите сохранить инструкцию.",
            },
            {
                "angle": "Мягкий оффер",
                "format": "Stories + пост",
                "hook": f"Как подготовиться к услуге «{service}»",
                "theme": "Перед публикацией подставьте только действующие цены и подтверждённые свободные даты.",
                "cta": "Предложите запросить актуальные условия.",
            },
        ]

    def build_content_sprint_plan(
        self, profile: Optional[UserProfile] = None, days: int = 4, use_llm: bool = True
    ) -> List[Dict[str, Any]]:
        if days <= 0 or days > 31:
            raise ValueError("days must be between 1 and 31")
        genres = ", ".join(profile.genres) if profile and profile.genres else "фотография"
        city = profile.city if profile and profile.city else "город не указан"
        service = profile.services[0] if profile and profile.services else "съёмка"
        if use_llm:
            parsed = self._json_response(
                f"Верни JSON-массив ровно из {days} дней контент-плана фотографа. "
                "Поля: day, rubric, topic, format, hook, cta. "
                "Не выдумывай кейсы, клиентов, цифры, цены, отзывы и свободные даты. "
                f"Жанры: {genres}; город: {city}; услуга: {service}."
            )
            if isinstance(parsed, list) and len(parsed) >= days:
                return parsed[:days]
        rotation = [
            ("Сторителлинг", f"История реального кадра в жанре {genres}", "Post"),
            ("Экспертиза", f"Что проверить в гардеробе для {genres}", "Reels + Carousel"),
            ("Доверие", "Разбор подтверждённого проекта или процесса", "Stories"),
            ("Продажи", f"Условия на {service} после проверки прайса и календаря", "Post"),
            ("Закулисье", f"Реальная световая схема для {genres}", "Reels"),
            ("Анти-страх", "Как проходит подготовка без обещания гарантированного результата", "Carousel"),
            ("Интерактив", "Вопрос аудитории о подготовке к съёмке", "Stories"),
        ]
        result = []
        for index in range(days):
            rubric, topic, format_name = rotation[index % len(rotation)]
            result.append(
                {
                    "day": f"День {index + 1}",
                    "rubric": rubric,
                    "topic": topic,
                    "format": format_name,
                    "hook": topic,
                    "cta": "Используйте только проверяемое действие без ложного дефицита.",
                }
            )
        return result

    def generate_nine_step_stories_arc(
        self,
        topic: str,
        profile: Optional[UserProfile] = None,
        target_offer: Optional[str] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        service = target_offer or (
            profile.services[0] if profile and profile.services else "съёмка"
        )
        if use_llm:
            parsed = self._json_response(
                "Верни JSON-объект topic, steps (ровно 9 объектов step_number, step_name, visual, "
                "text_on_screen, sticker), formatted_script. Не выдумывай отзывы, личный опыт, "
                "затраченное время, статистику, цены или число свободных мест. "
                f"Тема: {topic}; услуга: {service}."
            )
            if isinstance(parsed, dict) and len(parsed.get("steps", [])) == 9:
                return parsed
        rows = [
            ("Вход", "Нейтральный кадр по теме", f"Сегодня разбираю тему: {topic}."),
            ("Разворот", "Деталь процесса", "Что в этой теме часто понимают неправильно?"),
            ("Детали", "Реальный backstage", "Подставьте подтверждённую деталь подготовки; время и результат не придумывайте."),
            ("Опрос", "Кадр с двумя вариантами", "Какой вариант ближе вам?"),
            ("Мостик", "Переход к процессу", "Покажите, как наблюдение связано с вашей работой."),
            ("Реакция", "Реальный скрин или вопрос", "Добавьте настоящий ответ клиента; если его нет — задайте вопрос аудитории."),
            ("Мысль", "Авторский кадр", "Сформулируйте собственный вывод без неподтверждённых обобщений."),
            ("Экспертность", "Реальный рабочий процесс", "Покажите конкретное действие, которое действительно выполняете на съёмке."),
            ("Оффер", "Проверенный кадр услуги", f"Перед публикацией проверьте прайс и календарь для услуги «{service}»; не создавайте ложный дефицит."),
        ]
        steps = [
            {
                "step_number": index,
                "step_name": name,
                "visual": visual,
                "text_on_screen": text,
                "sticker": "Опрос" if index == 4 else None,
            }
            for index, (name, visual, text) in enumerate(rows, 1)
        ]
        formatted = "\n\n".join(
            f"### Кадр {step['step_number']}: {step['step_name']}\n"
            f"🎬 {step['visual']}\n💬 {step['text_on_screen']}"
            for step in steps
        )
        return {"topic": topic, "steps": steps, "formatted_script": formatted}

    def generate_introvert_reels_script(
        self,
        topic: str,
        profile: Optional[UserProfile] = None,
        duration_seconds: int = 12,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        if use_llm:
            parsed = self._json_response(
                "Верни JSON-объект title, format_type, duration_seconds, b_roll_scenes, "
                "sound_design, caption, formatted_script для Reels без говорящей головы. "
                "Не выдумывай статистику, клиентов, отзывы и результаты. "
                f"Тема: {topic}; длительность: {duration_seconds}."
            )
            if isinstance(parsed, dict) and parsed.get("b_roll_scenes"):
                return parsed
        scenes = [
            {"timing": "0–4 сек", "visual": "Настройка камеры крупным планом", "text_overlay": topic},
            {"timing": "4–8 сек", "visual": "Реальный фрагмент процесса", "text_overlay": "Покажите наблюдаемое действие без обещания результата"},
            {"timing": "8–12 сек", "visual": "Подтверждённый готовый кадр", "text_overlay": "Сохраните идею для подготовки"},
        ]
        sound = {"track_mood": "ambient / lo-fi", "foley_effects": "звук затвора и окружения"}
        caption = (
            "Перед камерой не нужно изображать чужую роль. В публикации покажите, "
            "как именно вы помогаете во время съёмки, используя только свой реальный процесс.\n\n"
            "Что в подготовке вызывает больше всего вопросов?"
        )
        formatted = "\n\n".join(
            f"### {scene['timing']}\n{scene['visual']}\nТекст: {scene['text_overlay']}"
            for scene in scenes
        ) + f"\n\nТекст поста:\n{caption}"
        return {
            "title": topic,
            "format_type": "Aesthetic B-Roll (No Talking Head)",
            "duration_seconds": duration_seconds,
            "b_roll_scenes": scenes,
            "sound_design": sound,
            "caption": caption,
            "formatted_script": formatted,
        }
