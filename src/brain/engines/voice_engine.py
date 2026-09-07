"""
Specialized Voice Workflow Engine for Personal AI Brain.
Processes raw voice notes / STT transcripts from photographers,
extracts narrative events and business insights, and generates
complete derivative content packs (1 Post, 2 Reels, 5 Stories, 1 Task).
"""
from typing import Dict, Any, List, Optional
from src.brain.models.profile import UserProfile
from src.brain.models.task import Task, TaskStatus, TaskPriority

class VoiceEngine:
    def __init__(self):
        pass

    def process_voice_transcript(
        self,
        transcript: str,
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Deconstructs spoken stream-of-consciousness into structured business & content assets,
        dynamically extracting actual events, conflicts, insights, and derivative media via LLM.
        """
        import re
        clean_text = transcript.strip()

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                niche = profile.niche if profile and profile.niche else "авторская фотография"
                tone = profile.tone if profile and profile.tone else "искренний, кинематографичный"
                prompt = (
                    f"Ты — профессиональный контент-продюсер и сторителлер фотографа ({niche}, тон: {tone}).\n"
                    f"Фотограф надиктовал голосовую заметку со съёмки или мысли:\n"
                    f"«««\n{clean_text}\n»»»\n\n"
                    f"Разбери эту аудиозапись и создай готовый комплект публикаций.\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    f"{{\n"
                    f'  "source_transcript": {json.dumps(clean_text, ensure_ascii=False)},\n'
                    f'  "extracted_events": ["событие 1", "событие 2"],\n'
                    f'  "story_beats": ["Экспозиция: ...", "Кульминация: ...", "Развязка: ..."],\n'
                    f'  "business_insights": ["бизнес-инсайт 1", "бизнес-инсайт 2"],\n'
                    f'  "derivative_post": "готовый сильный пост от первого лица с абзацами",\n'
                    f'  "derivative_reels": [\n'
                    f'    {{"id": "reel_1", "title": "заголовок", "hook": "хук", "visual": "видеоряд", "text_on_screen": "текст", "voiceover": "голос", "cta": "призыв"}},\n'
                    f'    {{"id": "reel_2", "title": "заголовок", "hook": "хук", "visual": "видеоряд", "text_on_screen": "текст", "voiceover": "голос", "cta": "призыв"}}\n'
                    f'  ],\n'
                    f'  "derivative_stories": [\n'
                    f'    {{"slide": 1, "type": "Hook", "text": "слайд 1"}},\n'
                    f'    {{"slide": 2, "type": "Context", "text": "слайд 2"}},\n'
                    f'    {{"slide": 3, "type": "Turning Point", "text": "слайд 3"}},\n'
                    f'    {{"slide": 4, "type": "Result", "text": "слайд 4"}},\n'
                    f'    {{"slide": 5, "type": "CTA", "text": "слайд 5"}}\n'
                    f'  ],\n'
                    f'  "suggested_task": {{"title": "действие фотографа по итогам", "priority": "HIGH", "due_in_hours": 24}}\n'
                    f"}}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "derivative_post" in parsed and "derivative_reels" in parsed:
                        return parsed
            except Exception:
                pass

        sentences = [s.strip() for s in re.split(r'[.!?]+', clean_text) if len(s.strip()) > 3]
        if not sentences:
            sentences = [clean_text]

        t_lower = clean_text.lower().replace("ё", "е")

        # 1. Extract Events directly from spoken sentences
        events = [f"Зафиксировано событие: «{s}»" for s in sentences[:3]]

        # 2. Extract Story Beats
        opening = sentences[0] if len(sentences) > 0 else clean_text
        middle = sentences[1] if len(sentences) > 1 else sentences[0]
        resolution = sentences[-1] if len(sentences) > 2 else "Итог съемки: яркие кадры и преодоление скованности"

        story_beats = [
            f"Экспозиция: {opening}",
            f"Кульминация и переломный момент: {middle}",
            f"Развязка и эмоциональный отклик: {resolution}"
        ]

        # 3. Derive Business Insights based on topic
        if any(w in t_lower for w in ["цен", "прайс", "чек", "деньг", "подорож"]):
            business_insights = [
                "Повышение цен требует прозрачной коммуникации добавленной ценности и заблаговременного анонса постоянным клиентам.",
                "Психологический барьер фотографа перед ростом чека снимается четким регламентом подготовки и сервиса."
            ]
            task_title = "Сформировать новую линейку пакетов и подготовить обращение к постоянным клиентам"
        elif any(w in t_lower for w in ["ресторан", "меню", "шеф", "блюд", "предмет"]):
            business_insights = [
                "Коммерческая фуд-съемка требует жесткого тайминга подачи горячих блюд и точной работы с контровым светом.",
                "Упаковка ресторанного кейса в карусель привлекает новых B2B-заказчиков с высоким чеком."
            ]
            task_title = "Отобрать 15 лучших кадров для коммерческого портфолио ресторана"
        else:
            business_insights = [
                "Бережная предварительная подготовка и правильная атмосфера на съемке (музыка, диалог) снимают 90% клиентского стресса.",
                "Искренние живые эмоции и кадры до/после — самый конвертирующий контент для прогрева новой аудитории."
            ]
            task_title = "Отправить клиенту первые 3-5 готовых тизеров съемки"

        # 4. Generate Derivative Post
        post_draft = (
            f"«{opening}»\n\n"
            f"Когда мы только начинали эту съемку, в воздухе чувствовалось напряжение. "
            f"Но в фотографии главное — не заученные позы, а безопасное пространство, где человеку разрешено выдохнуть и быть собой.\n\n"
            f"{middle}. И в этот момент магия случилась: скованность ушла, уступив место настоящему, глубокому взгляду.\n\n"
            f"Ради таких моментов я и держу камеру в руках. {resolution}.\n\n"
            f"А что для вас самое сложное в фотосессиях — подготовка или первые минуты перед объективом?"
        )

        # 5. Generate Derivative Reels
        reels_scripts = [
            {
                "id": "reel_1",
                "title": f"Динамика съемки: {opening[:40]}...",
                "hook": f"«{opening[:60]}...» — как переломить ход съемки за 5 минут.",
                "visual": "Склейка: сначала напряженный взгляд в зеркало, затем динамичные живые кадры в движении под мягким светом.",
                "text_on_screen": "Секрет живых кадров без заученных поз",
                "voiceover": "Камера видит не ваше умение позировать, а ваше состояние. Стоит расслабиться — и кадр оживает.",
                "cta": "Сохраняй идею для своей следующей съемки."
            },
            {
                "id": "reel_2",
                "title": "Бэкстейдж съемки и свет",
                "hook": "Что видит фотограф за секунду до того, как рождается шедевр.",
                "visual": "План со спины фотографа, работа с отражателем и готовый крупный портрет на мониторе камеры.",
                "text_on_screen": "Чистый свет и никакого позирования",
                "voiceover": "Правильный световой акцент подчеркивает взгляд и создает киношный объем без сложной ретуши.",
                "cta": "Напиши '+' в комментарии, если хочешь подробный разбор световой схемы."
            }
        ]

        # 6. Generate Derivative Stories Pack
        stories_pack = [
            {"slide": 1, "type": "Hook / Backstage", "text": f"Вчерашняя съемка началась неожиданно... «{opening[:50]}» Показать изнанку?"},
            {"slide": 2, "type": "Context / Challenge", "text": f"Главный барьер, с которым мы столкнулись: {middle[:70]}."},
            {"slide": 3, "type": "Turning Point", "text": "Мы сменили ракурс, включили плейлист и просто начали разговаривать."},
            {"slide": 4, "type": "Result / Visual Proof", "text": f"Кадр на дисплее камеры без единого фильтра. {resolution[:60]}."},
            {"slide": 5, "type": "CTA / Question", "text": "Окошко: 'Какой ваш главный страх перед камерой?' + Ссылка на бронь дат"}
        ]

        generated_task = {
            "title": task_title,
            "priority": "HIGH",
            "due_in_hours": 24
        }

        return {
            "source_transcript": clean_text,
            "extracted_events": events,
            "story_beats": story_beats,
            "business_insights": business_insights,
            "derivative_post": post_draft,
            "derivative_reels": reels_scripts,
            "derivative_stories": stories_pack,
            "suggested_task": generated_task
        }
