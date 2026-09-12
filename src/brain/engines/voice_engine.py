"""Convert a transcript into derivative drafts without inventing source facts."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src.brain.models.profile import UserProfile


class VoiceEngine:
    def process_voice_transcript(
        self,
        transcript: str,
        profile: Optional[UserProfile] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        source = str(transcript or "").strip()
        if not source:
            raise ValueError("Voice transcript is empty")
        if use_llm:
            try:
                from src.brain.services.llm_provider import LLMProvider

                niche = profile.niche if profile and profile.niche else "фотография"
                prompt = (
                    "Верни только JSON: source_transcript, extracted_events, story_beats, "
                    "business_insights, derivative_post, derivative_reels (2), derivative_stories (5), "
                    "suggested_task. Все факты, числа, отзывы, эмоции, результаты и события должны "
                    "дословно следовать из транскрипта. Не заполняй пробелы выдумками. "
                    f"Ниша: {niche}. Транскрипт: {json.dumps(source, ensure_ascii=False)}"
                )
                status, text, _, _ = LLMProvider().chat_completion(
                    [{"role": "user", "content": prompt}], temperature=0.5
                )
                if status == 200 and not text.strip().startswith("Тестовый ответ"):
                    cleaned = text.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict) and parsed.get("derivative_post"):
                        return parsed
            except Exception:
                pass

        sentences = [part.strip() for part in re.split(r"[.!?]+", source) if part.strip()]
        events = [f"Из транскрипта: «{sentence}»" for sentence in sentences[:3]]
        opening = sentences[0]
        middle = sentences[1] if len(sentences) > 1 else "Дополнительные детали не указаны"
        ending = sentences[-1] if len(sentences) > 2 else "Итог в транскрипте не указан"
        beats = [
            f"Экспозиция: {opening}",
            f"Развитие: {middle}",
            f"Итог: {ending}",
        ]

        lowered = source.casefold().replace("ё", "е")
        if any(word in lowered for word in ("цен", "прайс", "чек", "деньг")):
            insights = [
                "Проверьте, какие цена и состав услуги действительно названы в заметке.",
                "Перед публикацией отделите личное мнение от подтверждённых коммерческих условий.",
            ]
            task = (
                "Проверить прайс и состав пакетов; подготовить коммуникацию "
                "для клиентов на основе названных условий"
            )
        elif any(word in lowered for word in ("ресторан", "меню", "блюд", "предмет")):
            insights = [
                "Соберите кейс только из процессов и результата, которые прямо названы в заметке.",
                "Добавьте технические параметры после проверки исходных файлов и брифа.",
            ]
            task = "Отобрать подтверждённые материалы для коммерческого кейса"
        else:
            insights = [
                "Используйте в публикации только наблюдения из голосовой заметки.",
                "Если результат, отзыв или цифра не названы, запросите их до финальной публикации.",
            ]
            task = "Дополнить заметку недостающими фактами перед публикацией"

        post = (
            f"{opening}.\n\n"
            f"{middle}.\n\n"
            f"{ending}.\n\n"
            "Черновик сохраняет только факты исходной заметки. Перед публикацией проверьте имена, "
            "цифры, согласие клиента и итоговый CTA."
        )
        reels = [
            {
                "id": "reel_1",
                "title": opening[:80],
                "hook": opening[:120],
                "visual": "Используйте реальный видеоряд, относящийся к заметке.",
                "text_on_screen": middle[:120],
                "voiceover": source[:500],
                "cta": "Задайте вопрос по теме без обещания результата.",
            },
            {
                "id": "reel_2",
                "title": "Разбор подтверждённого процесса",
                "hook": middle[:120],
                "visual": "Покажите фактический процесс или пометьте нужный кадр как TODO.",
                "text_on_screen": ending[:120],
                "voiceover": "Не добавляйте события и цифры, которых нет в исходной записи.",
                "cta": "Предложите сохранить практический вывод.",
            },
        ]
        story_texts = [
            opening,
            middle,
            "Покажите относящийся к заметке реальный backstage.",
            ending,
            "Перед публикацией подставьте только проверенный CTA.",
        ]
        stories = [
            {"slide": index, "type": "Source-based draft", "text": text}
            for index, text in enumerate(story_texts, 1)
        ]
        return {
            "source_transcript": source,
            "extracted_events": events,
            "story_beats": beats,
            "business_insights": insights,
            "derivative_post": post,
            "derivative_reels": reels,
            "derivative_stories": stories,
            "suggested_task": {"title": task, "priority": "HIGH", "due_in_hours": 24},
        }
