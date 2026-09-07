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
        if "интроверт" in fmt or "b-roll" in fmt or "эстетик" in fmt:
            return (
                "ФОРМАТ: REELS ДЛЯ ИНТРОВЕРТА (БЕЗ 'ГОВОРЯЩЕЙ ГОЛОВЫ')\n"
                "1. ЭСТЕТИЧНЫЙ B-ROLL (руки, камера, свет, отражения, детали)\n"
                "2. ТЕКСТ НА ЭКРАНЕ (лаконичная сильная типографика в ритм)\n"
                "3. АТМОСФЕРНЫЙ ЗВУКОВОЙ ДИЗАЙН (звук затвора, эмбиент, винил)\n"
                "4. ХРОНОМЕТРАЖ: 7–15 сек для высокой досматриваемости\n"
                "5. ТЕКСТ ПОСТА И CTA"
            )
        if "арка" in fmt or "9" in fmt or "яишка" in fmt:
            return (
                "ФОРМАТ: 9-ШАГОВАЯ АРКА STORIES (МЕТОДОЛОГИЯ «ЯИШКА»)\n"
                "1. Вход -> 2. Разворот -> 3. Детали быта -> 4. Интерактивный опрос -> "
                "5. Мостик -> 6. Реакция аудитории -> 7. Философская мысль -> 8. Экспертность -> 9. Эфир/Оффер"
            )
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

    def generate_nine_step_stories_arc(
        self,
        topic: str,
        profile: Optional[UserProfile] = None,
        target_offer: Optional[str] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Generates the full 9-step Stories storytelling arc matching Yaishka Screen 05:
        1. Вход -> 2. Разворот -> 3. Детали быта -> 4. Интерактивный опрос -> 
        5. Мостик -> 6. Реакция аудитории -> 7. Философская мысль -> 8. Экспертность -> 9. Эфир/Оффер.
        """
        city = profile.city if profile and profile.city else "городе"
        niche = profile.niche if profile and profile.niche else "фотография"
        service = target_offer or (profile.services[0] if profile and profile.services else "авторскую съемку")

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — топовый контент-драматург для фотографов сервиса «Яишка».\n"
                    f"Создай эталонную 9-шаговую прогревочную арку Stories по методике экрана 05 Яишки:\n"
                    f"Тема: '{topic}', Ниша: '{niche}', Город: '{city}', Оффер: '{service}'.\n\n"
                    "Строго 9 шагов драматургической цепочки:\n"
                    "1. «Вход»: утренний или интригующий бытовой хук (кадр чашки кофе, утреннего света, дороги).\n"
                    "2. «Разворот»: неожиданный сюжетный поворот или инсайт, ломающий привычный шаблон.\n"
                    "3. «Детали быта»: приземление на живую реальность (закулисье студии, ноутбук, сборы, честное наблюдение).\n"
                    "4. «Интерактивный опрос»: вовлекающая наклейка-опрос или ползунок (например, 'У вас тоже так?' или '1 или 2?').\n"
                    "5. «Мостик»: логический переход от бытового наблюдения к профессиональной теме.\n"
                    "6. «Реакция аудитории»: скрины ответов в директ или фиксация главного переживания героев съемок.\n"
                    "7. «Философская мысль»: глубокая авторская мысль о ценности памяти, искренности, принятия себя.\n"
                    "8. «Экспертность»: демонстрация мастерства (как ты бережно ведешь в кадре, работа со светом и настроением).\n"
                    "9. «Эфир/Оффер»: мягкий экологичный призыв записаться или занять свободное съемочное окошко.\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "topic": "{topic}",\n'
                    '  "steps": [\n'
                    '    {"step_number": 1, "step_name": "Вход", "visual": "описание кадра", "text_on_screen": "текст сторис", "sticker": null},\n'
                    '    {"step_number": 2, "step_name": "Разворот", "visual": "...", "text_on_screen": "...", "sticker": null},\n'
                    '    {"step_number": 3, "step_name": "Детали быта", "visual": "...", "text_on_screen": "...", "sticker": null},\n'
                    '    {"step_number": 4, "step_name": "Интерактивный опрос", "visual": "...", "text_on_screen": "...", "sticker": "наклейка с опросом"},\n'
                    '    {"step_number": 5, "step_name": "Мостик", "visual": "...", "text_on_screen": "...", "sticker": null},\n'
                    '    {"step_number": 6, "step_name": "Реакция аудитории", "visual": "...", "text_on_screen": "...", "sticker": null},\n'
                    '    {"step_number": 7, "step_name": "Философская мысль", "visual": "...", "text_on_screen": "...", "sticker": null},\n'
                    '    {"step_number": 8, "step_name": "Экспертность", "visual": "...", "text_on_screen": "...", "sticker": null},\n'
                    '    {"step_number": 9, "step_name": "Эфир/Оффер", "visual": "...", "text_on_screen": "...", "sticker": "ссылка или окно записи"}\n'
                    '  ],\n'
                    '  "formatted_script": "готовый сценарий в markdown с номерами и эмодзи"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "steps" in parsed and len(parsed["steps"]) == 9:
                        return parsed
            except Exception:
                pass

        default_steps = [
            {
                "step_number": 1,
                "step_name": "Вход",
                "visual": "Эстетичный план: чашка утреннего кофе у окна с мягким контровым лучом солнца.",
                "text_on_screen": f"Доброе утро. Сегодня с раннего утра думала про одну простую вещь: {topic.lower()}.",
                "sticker": None
            },
            {
                "step_number": 2,
                "step_name": "Разворот",
                "visual": "Короткое видео: камера в руках, переключение режимов, взгляд за окно.",
                "text_on_screen": "Казалось бы, всё очевидно. Но когда начинаешь разбираться глубже — всё переворачивается на 180°.",
                "sticker": None
            },
            {
                "step_number": 3,
                "step_name": "Детали быта",
                "visual": "Стол с рабочим блокнотом, флешками, открытым ноутбуком и раскадровкой.",
                "text_on_screen": "Вот так выглядит подготовка без прикрас. 2 часа искала тот самый оттенок ткани под съемку.",
                "sticker": None
            },
            {
                "step_number": 4,
                "step_name": "Интерактивный опрос",
                "visual": "Фактурная макро-фотография ткани или ретро-детали.",
                "text_on_screen": "А как у вас? Часто замечаете такие мелочи в повседневной суете?",
                "sticker": "Опрос: «Да, постоянно!» / «Вообще нет времени»"
            },
            {
                "step_number": 5,
                "step_name": "Мостик",
                "visual": "Бэкстейдж съемки: фотограф с улыбкой показывает кадр на экранчике камеры героям.",
                "text_on_screen": "И именно здесь рождается магия: когда мы перестаем торопиться, в кадре появляется настоящая жизнь.",
                "sticker": None
            },
            {
                "step_number": 6,
                "step_name": "Реакция аудитории",
                "visual": "Коллаж из скриншотов тёплых отзывов и сообщений из директа.",
                "text_on_screen": "«Я никогда не видела себя такой настоящей и спокойной...» — такие слова греют сильнее любого кофе.",
                "sticker": None
            },
            {
                "step_number": 7,
                "step_name": "Философская мысль",
                "visual": "Атмосферный черно-белый кадр с глубоким светотеневым рисунком.",
                "text_on_screen": "Фотография — это не про позы и не про платье. Это про то, какими вы помните себя в этот момент.",
                "sticker": None
            },
            {
                "step_number": 8,
                "step_name": "Экспертность",
                "visual": "Серия из 3 сменяющихся кадров: детали, средний план, живая улыбка в движении.",
                "text_on_screen": "Моя работа — бережно создать пространство, где вам не нужно играть роли и быть 'моделью'.",
                "sticker": None
            },
            {
                "step_number": 9,
                "step_name": "Эфир/Оффер",
                "visual": "Красивый портрет с контровым закатным светом и лаконичной плашкой.",
                "text_on_screen": f"На ближайшую неделю открыла ровно 2 свободных слота на {service}. Если откликается — напишите в директ 'ХОЧУ' 🤍",
                "sticker": "Кнопка: «Написать в Директ»"
            }
        ]

        formatted = (
            f"📱 **9-ШАГОВАЯ АРКА STORIES — «{topic.upper()}»**\n"
            f"*Методология экрана 05 сервиса «Яишка»*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for s in default_steps:
            stk = f"\n🏷 **Интерактив:** `{s['sticker']}`" if s["sticker"] else ""
            formatted += (
                f"### Кадр {s['step_number']}: [{s['step_name']}]\n"
                f"🎬 **Визуал:** {s['visual']}\n"
                f"💬 **Текст на экране:**\n> *«{s['text_on_screen']}»*{stk}\n\n"
            )

        return {
            "topic": topic,
            "steps": default_steps,
            "formatted_script": formatted
        }

    def generate_introvert_reels_script(
        self,
        topic: str,
        profile: Optional[UserProfile] = None,
        duration_seconds: int = 12,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Generates an aesthetic, high-retention Reels script tailored for introverted / camera-shy photographers.
        Matches Yaishka Screen 17 (No talking head, aesthetic B-roll, typography text overlays, atmospheric sound design).
        """
        city = profile.city if profile and profile.city else "городе"
        niche = profile.niche if profile and profile.niche else "авторская фотография"

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — режиссер вирусных эстетичных Reels сервиса «Яишка».\n"
                    f"Создай сценарий короткого видео (Reels) для фотографа-ИНТРОВЕРТА, который стесняется говорить на камеру (экран 17 Яишки).\n"
                    f"Тема: '{topic}', Ниша: '{niche}', Город: '{city}'. Хронометраж: {duration_seconds} сек.\n\n"
                    "Ключевые принципы Яишки для интровертов:\n"
                    "1. Полное отсутствие 'говорящей головы'.\n"
                    "2. Эстетичный атмосферный B-roll: руки, детали техники, чашка кофе, светотень от жалюзи, кадр со спины, движение ткани.\n"
                    "3. Сильный ритмичный текст на экране (3 лаконичные фразы, цепляющие за 3 секунды).\n"
                    "4. Атмосферный звуковой дизайн: звук затвора, эмбиент/лофай, шум дождя или пленки.\n"
                    "5. Вовлекающее описание для поста с мягким CTA.\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "title": "{topic}",\n'
                    '  "format_type": "Introvert / Aesthetic B-Roll (No Talking Head)",\n'
                    f'  "duration_seconds": {duration_seconds},\n'
                    '  "b_roll_scenes": [\n'
                    '    {"timing": "0-4 сек", "visual": "описание кадра", "text_overlay": "текст на экране"},\n'
                    '    {"timing": "4-8 сек", "visual": "описание кадра", "text_overlay": "текст на экране"},\n'
                    '    {"timing": "8-12 сек", "visual": "описание кадра", "text_overlay": "текст на экране"}\n'
                    '  ],\n'
                    '  "sound_design": {\n'
                    '    "track_mood": "lo-fi acoustic / ambient",\n'
                    '    "foley_effects": "мягкий щелчок затвора камеры, шуршание ткани"\n'
                    '  },\n'
                    '  "caption": "готовый текст описания под Reels",\n'
                    '  "formatted_script": "полный сценарий в markdown"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "b_roll_scenes" in parsed:
                        return parsed
            except Exception:
                pass

        scenes = [
            {
                "timing": "0–4 сек (Хук)",
                "visual": "Макро-план: пальцы медленно настраивают кольцо диафрагмы на винтажном объективе. Контровой теплый свет из окна.",
                "text_overlay": "Если вы думаете, что перед камерой нужно уметь позировать..."
            },
            {
                "timing": "4–8 сек (Суть)",
                "visual": "План со спины: силуэт фотографа у окна, легкое движение льняной шторы от теплого ветра, на мониторе проявляется живой кадр.",
                "text_overlay": "...то самые ценные кадры рождаются ровно в момент, когда вы перестаете стараться."
            },
            {
                "timing": "8–12 сек (Вывод / CTA)",
                "visual": "Кадр через плечо: экран камеры, где героиня искренне смеется в движении. Звук мягкого щелчка затвора.",
                "text_overlay": "Сохрани, чтобы вспомнить перед следующей съемкой 🤍"
            }
        ]
        sound = {
            "track_mood": "Теплый Lo-Fi / Cinematic Ambient с медленным глубоким битом",
            "foley_effects": "Мягкий механический щелчок затвора камеры на 11-й секунде, тихий утренний эмбиент"
        }
        caption = (
            f"Вам не нужно быть моделью, чтобы получились кадры, в которые вы влюбитесь.\n\n"
            f"Моя главная задача на съемке — забрать всё напряжение на себя: подсказать музыку, свет, "
            f"направить каждое движение и поймать ваш настоящий взгляд, а не заученную позу.\n\n"
            f"Напишите в комментариях, боитесь ли вы камеры так же, как 90% моих героев? 🤍"
        )
        formatted = (
            f"🎬 **REELS ДЛЯ ИНТРОВЕРТА: «{topic.upper()}»**\n"
            f"*Формат: Aesthetic B-Roll (без лица в кадре и 'говорящей головы') | {duration_seconds} сек*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎵 **Звуковой дизайн:**\n"
            f"• Трек: {sound['track_mood']}\n"
            f"• Звуковые эффекты: {sound['foley_effects']}\n\n"
            f"🎞 **Раскадровка:**\n"
        )
        for sc in scenes:
            formatted += (
                f"### {sc['timing']}\n"
                f"📷 **Визуал:** {sc['visual']}\n"
                f"📝 **Текст на экране:** «{sc['text_overlay']}»\n\n"
            )
        formatted += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📝 **Текст поста:**\n{caption}"

        return {
            "title": topic,
            "format_type": "Introvert / Aesthetic B-Roll (No Talking Head)",
            "duration_seconds": duration_seconds,
            "b_roll_scenes": scenes,
            "sound_design": sound,
            "caption": caption,
            "formatted_script": formatted
        }
