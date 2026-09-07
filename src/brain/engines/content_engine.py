"""
Specialized Content Engine for Personal AI Brain.
Provides production-grade generation guidance, formats, hooks, CTAs,
and the core "Мне нечего выложить" recovery workflow.
"""
from typing import Dict, Any, List, Optional
from src.brain.models.profile import UserProfile

class ContentEngine:
    def __init__(self):
        pass

    def build_format_prompt(self, format_type: str, goal: str = "вовлечение", audience: str = "клиенты") -> str:
        fmt = format_type.lower()
        if "reel" in fmt or "рилс" in fmt:
            return (
                "ФОРМАТ: REELS (Короткий динамичный ролик)\n"
                "Структура сценария:\n"
                "1. ХУК (0-3 сек): Провокационный вопрос, визуальный слом шаблона или парадоксальное утверждение.\n"
                "2. ВИЗУАЛЬНЫЙ РЯД: Конкретное описание действий фотографа/модели в кадре, движение камеры.\n"
                "3. ТЕКСТ НА ЭКРАНЕ: 3-4 емкие плашки крупным шрифтом (для тех, кто смотрит без звука).\n"
                "4. ГОЛОСОВОЙ ТЕКСТ: Разговорная реплика живым языком без клише.\n"
                "5. АУДИО: Рекомендация по треку / настроению звука.\n"
                "6. ОПИСАНИЕ И CTA: Текст под видео (1-2 абзаца) с четким призывом сохранить или написать в Direct."
            )
        elif "stori" in fmt or "сторис" in fmt:
            return (
                "ФОРМАТ: СЕРИЯ STORIES (Драматургическая цепочка 4-6 кадров)\n"
                "Структура серии:\n"
                "Кадр 1 (Вход в контекст): Интрига, живой вопрос или необычный бекстейдж-кадр.\n"
                "Кадр 2 (Развитие): Закулисная деталь, мысль фотографа или сомнение, знакомое клиенту.\n"
                "Кадр 3 (Кульминация): Результат, готовый кадр 'до/после' или эстетическое открытие.\n"
                "Кадр 4 (Польза/Инсайт): Практический вывод для клиента (про позы, свет, гардероб).\n"
                "Кадр 5 (Интерактив/CTA): Окошко для вопросов, опрос или мягкое приглашение на съемку."
            )
        elif "telegram" in fmt or "тг" in fmt or "канал" in fmt:
            return (
                "ФОРМАТ: TELEGRAM-ПОСТ\n"
                "Структура публикации:\n"
                "1. Заголовок жирным шрифтом без точки.\n"
                "2. Личная интонация, форматирование с абзацами и акцентными списками.\n"
                "3. Глубокая мысль или экспертный кейс без канцелярита.\n"
                "4. Открытый вопрос для обсуждения в комментариях."
            )
        else:
            return (
                "ФОРМАТ: ЭКСПЕРТНЫЙ / СТОРИТЕЛЛИНГ ПОСТ\n"
                "Структура поста:\n"
                "1. ЦЕПЛЯЮЩИЙ ХУК В ПЕРВОЙ СТРОКЕ: Разрушение мифа, неожиданная цитата или яркая деталь.\n"
                "2. ТЕЛО ПОСТА (3-4 коротких абзаца): История из практики, разбор клиентской боли или закулисье.\n"
                "3. ВЫВОД: Трансформация клиента / личная позиция автора.\n"
                "4. ПРИЗЫВ К ДЕЙСТВИЮ (CTA): Естественный, не агрессивный призыв к диалогу или записи."
            )

    def emergency_content_recovery(
        self,
        profile: Optional[UserProfile] = None,
        recent_projects: Optional[List[Dict[str, Any]]] = None,
        current_season: str = "текущий сезон",
        memories: Optional[List[str]] = None,
        use_llm: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Core workflow: 'Мне нечего выложить'.
        Synthesizes 3 distinct, immediately actionable content angles
        dynamically mined from photographer projects, memories, and profile via LLM.
        """
        # 1. Mine recent projects from DB if not provided
        if recent_projects is None:
            try:
                from src.brain.db import get_connection
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT name, description, status FROM projects ORDER BY created_at DESC LIMIT 3")
                rows = c.fetchall()
                conn.close()
                if rows:
                    recent_projects = [{"name": r["name"], "description": r["description"], "status": r["status"]} for r in rows]
                else:
                    recent_projects = []
            except Exception:
                recent_projects = []

        # 2. Mine memories from DB if not provided
        if memories is None:
            try:
                from src.brain.engines.memory_engine import MemoryEngine
                mem_engine = MemoryEngine()
                retrieved = mem_engine.retrieve_relevant_memories("съемка кадр бэкстейдж клиент история", limit=2)
                memories = [m[0].content for m in retrieved]
            except Exception:
                memories = []

        genres = ", ".join(profile.genres) if profile and profile.genres else "индивидуальные и портретные съемки"
        city = profile.city if profile and profile.city else "вашем городе"
        niche = profile.niche if profile and profile.niche else "авторская фотография"
        service = profile.services[0] if profile and profile.services else "индивидуальную съемку"

        # Try dynamic LLM synthesis first if requested
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                
                proj_context = "; ".join([f"'{p.get('name')}' ({p.get('status')})" for p in recent_projects]) if recent_projects else "нет активных проектов"
                mem_context = "; ".join(memories) if memories else "нет заметок"

                prompt = (
                    f"Ты — креативный арт-директор и контент-стратег фотографа.\n"
                    f"Фотограф растерян: 'Мне нечего выложить'.\n"
                    f"Контекст фотографа:\n"
                    f"- Ниша: {niche}\n"
                    f"- Жанры: {genres}\n"
                    f"- Город: {city}\n"
                    f"- Сезон: {current_season}\n"
                    f"- Свежие проекты: {proj_context}\n"
                    f"- Личные факты и мысли: {mem_context}\n\n"
                    f"Создай 3 кардинально разных, цепляющих, живых ракурса для публикации.\n"
                    f"Верни ответ ИСКЛЮЧИТЕЛЬНО в формате JSON массива из 3 объектов, без markdown блоков ```json:\n"
                    f"[\n"
                    f'  {{"angle": "Сторителлинг & Доверие", "format": "Личный пост + карусель кадров", "hook": "цепляющий хук в кавычках", "theme": "суть темы", "cta": "призыв к действию"}},\n'
                    f'  {{"angle": "Экспертиза & Закулисье", "format": "Reels / Клип (Backstage vs Итоговый кадр)", "hook": "цепляющий хук в кавычках", "theme": "суть темы", "cta": "призыв к действию"}},\n'
                    f'  {{"angle": "Мягкие продажи & Сезонный оффер", "format": "Серия Stories + пост с открытыми датами", "hook": "цепляющий хук в кавычках", "theme": "суть темы", "cta": "призыв к действию"}}\n'
                    f"]"
                )

                status_code, text, _, _ = llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )
                if status_code == 200:
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, list) and len(parsed) >= 3:
                        return parsed[:3]
            except Exception:
                pass  # Gracefully fall back to mined template below

        # Angle 1: Storytelling & Trust (mined from projects/memories)
        if recent_projects:
            p_top = recent_projects[0]
            angle1_hook = f"«То, что осталось за кадром проекта '{p_top.get('name')}'»: почему идеальный кадр рождается из хаоса."
            angle1_theme = f"Закулисье съемки '{p_top.get('name')}': преодоление сомнений, поиск света и живые эмоции."
            angle1_cta = f"Напишите в комментариях, хотите увидеть до/после кадров с этой съемки?"
        elif memories:
            m_top = memories[0]
            angle1_hook = f"«{m_top[:70]}...» — почему эта деталь на съемке решает всё."
            angle1_theme = f"Сторителлинг из личной практики фотографа в нише {niche}."
            angle1_cta = "Поделитесь, какой кадр вы мечтаете сделать для себя?"
        else:
            angle1_hook = f"«Я не умею позировать и боюсь камеры» — с этой фразы начинаются 8 из 10 моих съемок в нише {niche}."
            angle1_theme = "Психологический комфорт на съемке: как раскрыть человека без заученных поз."
            angle1_cta = "Напишите, в какой момент вы обычно чувствуете себя скованно перед камерой?"

        # Angle 2: Expertise & Backstage
        if recent_projects and len(recent_projects) > 1:
            p_sec = recent_projects[1]
            angle2_hook = f"Разбор световой схемы на проекте '{p_sec.get('name')}': как повторить киношный объем."
            angle2_theme = f"Световые приемы и оптика для съемки в жанре '{genres}'."
        else:
            angle2_hook = f"Один источник света и 3 совершенно разных настроения в одном кадре."
            angle2_theme = f"Разбор световой схемы для жанра '{genres}' в локациях в {city}."

        # Angle 3: Soft Sales & Seasonal Offer
        angle3_hook = f"Осталось всего 3 свободных слота на {current_season} на {service}."
        angle3_theme = f"Почему готовиться к съемке нужно заранее: подбор гардероба и концепции под ключ."
        angle3_cta = "Отправьте '+' в директ, чтобы забронировать слот и получить персональный мудборд."

        return [
            {
                "angle": "Сторителлинг & Доверие",
                "format": "Личный пост + карусель кадров",
                "hook": angle1_hook,
                "theme": angle1_theme,
                "cta": angle1_cta
            },
            {
                "angle": "Экспертиза & Закулисье",
                "format": "Reels / Клип (Backstage vs Итоговый кадр)",
                "hook": angle2_hook,
                "theme": angle2_theme,
                "cta": "Сохраняйте схему, чтобы повторить на следующей съемке."
            },
            {
                "angle": "Мягкие продажи & Сезонный оффер",
                "format": "Серия Stories + пост с открытыми датами",
                "hook": angle3_hook,
                "theme": angle3_theme,
                "cta": angle3_cta
            }
        ]

    def build_content_sprint_plan(
        self,
        profile: Optional[UserProfile] = None,
        days: int = 7,
        use_llm: bool = False
    ) -> List[Dict[str, Any]]:
        genres = ", ".join(profile.genres) if profile and profile.genres else "авторская фотография"
        city = profile.city if profile and profile.city else "городе"
        service = profile.services[0] if profile and profile.services else "съемки"

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — контент-стратег для фотографа в нише '{genres}', город {city}.\n"
                    f"Составь план публикаций на 4 ключевых дня недели.\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО JSON массив из 4 объектов:\n"
                    f"[\n"
                    f'  {{"day": "Понедельник", "rubric": "Сторителлинг", "topic": "живая тема", "format": "Post"}},\n'
                    f'  {{"day": "Среда", "rubric": "Экспертиза", "topic": "полезная тема", "format": "Reels"}},\n'
                    f'  {{"day": "Пятница", "rubric": "Кейс/Доверие", "topic": "история съемки", "format": "Stories"}},\n'
                    f'  {{"day": "Воскресенье", "rubric": "Продажи", "topic": "оффер на {service}", "format": "Post"}}\n'
                    f"]"
                )
                status_code, text, _, _ = llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.6
                )
                if status_code == 200:
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, list) and len(parsed) >= 4:
                        return parsed
            except Exception:
                pass

        rubrics = [
            ("Понедельник", "Вдохновение / Сторителлинг", f"История одного кадра: что осталось за кадром съемки в стиле {genres}", "Post"),
            ("Среда", "Экспертиза / Польза", f"3 вещи в гардеробе, которые портят съемку {genres}", "Reels + Carousel"),
            ("Пятница", "Кейс / Доверие", f"Как мы подобрали локацию в {city} и создали киношную атмосферу", "Stories Series"),
            ("Воскресенье", "Продажи / Оффер", f"Свободные даты на следующий месяц и анонс пакетов на {service}", "Telegram / Post")
        ]
        return [
            {"day": day, "rubric": rubric, "topic": topic, "format": fmt}
            for day, rubric, topic, fmt in rubrics
        ]

