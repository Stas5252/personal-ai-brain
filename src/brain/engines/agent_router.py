"""Agent Router for Intent Classification and Multi-Agent Specialization."""
import re
from typing import List, Dict, Set, Tuple, Optional, Any
from src.brain.models.routing import IntentType, RoutingDecision

INTENT_KEYWORDS: Dict[IntentType, List[str]] = {
    IntentType.PHOTO: [
        "фотосесси", "фотограф", "свет", "съемк", "камер", "объектив", "диафрагм", "выдержк", "iso", "портрет",
        "софтбокс", "рефлектор", "позирован", "ракурс", "кадр", "экспозици",
        "фокус", "вспышк", "студийный свет", "схема света", "октобокс"
    ],
    IntentType.CONTENT: [
        "пост", "текст", "стать", "контент", "блог", "тема для", "о чем написать",
        "заголовок", "рубрик", "план публикаци", "нечего выложить", "нет идей", "что выложить"
    ],
    IntentType.REELS: [
        "reels", "рилс", "сценарий", "видео", "ролик", "хук", "хронометраж", "динамик", "раскадровк"
    ],
    IntentType.STORIES: ["сторис", "stories", "прогрев", "интерактив", "опрос", "окошко", "сториз"],
    IntentType.SALES: [
        "дорого", "дешев", "дешевле", "возражен", "клиент говорит", "как ответить", "продать", "скидк",
        "скрипт", "лид", "заявк", "переписк", "аргументир", "обоснова", "отказ", "конверси"
    ],
    IntentType.PRICING: [
        "цена", "прайс", "пакет", "стоимость", "тариф", "сколько стоит", "чек", "расценк", "поднять цену", "ценообразование"
    ],
    IntentType.CLIENT: [
        "клиент", "заказчик", "невеста", "модель", "девушк",
        "общение с клиентом", "бюджет клиента", "пожелания клиент", "переписка", "диалог"
    ],
    IntentType.PROJECT: [
        "проект", "фотодень", "фотодня", "фотодне", "воркшоп", "кампейн", "дедлайн", "дедлайны",
        "статус подготовки", "подготовк", "решение по", "съемочный день", "тайминг"
    ],
    IntentType.MOODBOARD: ["мудборд", "moodboard", "референсы", "визуал", "концепт", "палитра", "стилистик", "образ", "подбор образов", "лукбук", "что надеть", "одежда на съемку", "цветовая гамма"],
    IntentType.MARKETING: [
        "продвижен", "маркетинг", "трафик", "реклам", "таргет", "упаковк", "аудитори", "позиционирован", "воронк"
    ],
    IntentType.PROFILE_AUDIT: ["шапк", "аудит", "аккаунт", "профиль", "биографи", "оформлен", "визитк", "разбор аккаунта", "аудит ленты", "лента", "сетка", "хайлайтс", "актуальное", "шапка профиля"],
    IntentType.KNOWLEDGE_SEARCH: ["что такое", "объясни", "архив", "база знани", "по регламенту", "по инструкции", "согласно"],
    IntentType.VOICE: ["голосовое", "войс", "аудио", "надиктовал", "наговорил", "запись голоса", "расшифровка"],
    IntentType.OBJECTION: [
        "дорого", "подумаем", "посоветуемся", "нашли дешевле", "позже", "не умеем позировать", "муж против",
        "посовет", "муж", "партнер", "подума", "не уме", "позиров", "стесня", "боюсь камер", "страх камер", "страх перед", "боязн", "боюсь", "бревно", "деревянн"
    ],
    IntentType.COMPETITOR: ["конкурент", "другие фотографы", "отстроиться", "отстройка", "рынок", "анализ рынка"],
    IntentType.TASK: ["задач", "дедлайн", "создай задачу", "напомни", "контроль"],
    IntentType.DAILY_PLAN: ["что мне сегодня делать", "что делать", "план на день", "с чего начать", "приоритеты на сегодня"],
    IntentType.MUSIC: ["трек", "треки", "музык", "саундтрек", "подбор треков", "песня", "аудиодорожк", "фоновая музык"],
    IntentType.DISPUTE: [
        "спор", "конфликт", "спорная ситуация", "претензи", "недовольн", "требует исходник",
        "докопал", "жалоб", "скандал", "разбор ситуации", "исходники raw", "отдать raw", "исходники", "не по договору",
        "отмен", "перенос", "перенес", "заболе", "простуд", "погод", "дожд", "дождь", "ливн", "ливень", "гроз", "снегопад", "метел", "грипп", "боле", "больниц", "форс-мажор"
    ]
}

SPECIALIZED_PROMPTS: Dict[IntentType, str] = {
    IntentType.PHOTO: "Фокус: Профессиональная постановка света, оптика, композиция и практическое руководство для съемки.",
    IntentType.CONTENT: "Фокус: Авторский копирайтинг для блога, вовлекающая драматургия, живой ритм и соблюдение редполитики.",
    IntentType.REELS: "Фокус: Сценарное мастерство коротких видео: цепляющий хук в первые 2 секунды, визуальный ряд, удержание внимания и CTA.",
    IntentType.STORIES: "Фокус: Сюжетные линии для Stories, эмоциональные триггеры, интерактив и естественное раскрытие экспертности.",
    IntentType.SALES: "Фокус: Мягкие экспертные продажи без давления, закрытие возражений ('дорого', 'я подумаю') через ценность и доверие.",
    IntentType.PRICING: "Фокус: Ценообразование, обоснование ценности пакетов фотоуслуг и прозрачные коммерческие предложения.",
    IntentType.CLIENT: "Фокус: Клиентский сервис, забота, выявление истинных потребностей заказчика и безупречный диалог.",
    IntentType.PROJECT: "Фокус: Продюсирование и проектный менеджмент съемки: тайминг, референсы, команда, логистика и контроль договоренностей.",
    IntentType.MOODBOARD: "Фокус: Арт-дирекшн, визуальные мудборды с 5 HEX-оттенками, 7 сетами образов, локацией, 5 планами крупности и блоком 'Важно ♡'.",
    IntentType.MARKETING: "Фокус: Маркетинговая стратегия, поиск платежеспособной аудитории и отстройка от конкурентов.",
    IntentType.PROFILE_AUDIT: "Фокус: Экспресс-аудит шапки профиля, УТП, навигации актуального и шахматного ритма планов ленты фотографа.",
    IntentType.KNOWLEDGE_SEARCH: "Фокус: Точный поиск и синтез информации из базы знаний фотографа с обязательной ссылкой на источники.",
    IntentType.VOICE: "Фокус: Анализ голосовой заметки фотографа, извлечение событий, драматургии, инсайтов и декомпозиция на контент и задачи.",
    IntentType.OBJECTION: "Фокус: Глубокая отработка клиентских возражений ('дорого', 'подумаем', 'не умеем позировать') через эмпатию, ценность и диагностику.",
    IntentType.COMPETITOR: "Фокус: Анализ конкурентов, выявление свободных ниш, отстройка и формулирование уникального предложения.",
    IntentType.TASK: "Фокус: Структурирование рабочих задач фотографа, приоритизация, дедлайны и контроль выполнения.",
    IntentType.DAILY_PLAN: "Фокус: Персональное планирование рабочего дня фотографа: анализ дедлайнов, клиентов в статусе ожидания, съемок и контент-пауз.",
    IntentType.MUSIC: "Фокус: Профессиональный подбор музыкальных треков под визуал, гармония настроения, темпа и ритма серии.",
    IntentType.DISPUTE: "Фокус: Антикризисная медиация конфликтов с клиентами фотографа: объективный разбор просадки, прав клиентки, перегибов и сдержанный скрипт.",
    IntentType.GENERAL: "Фокус: Комплексный персональный ассистент фотографа."
}


class AgentRouter:
    def __init__(self):
        pass

    def route(self, query: str, context: Optional[Dict[str, Any]] = None) -> RoutingDecision:
        q_lower = query.lower().replace("ё", "е")
        matched_scores: Dict[IntentType, int] = {}
        for intent, kws in INTENT_KEYWORDS.items():
            score = 0
            for kw in kws:
                if kw == "цена":
                    # Avoid collision inside "сценарий", "сцена"
                    if re.search(r'(?<![а-яa-z0-9])цен[а-я]*', q_lower):
                        score += 1
                    continue
                if kw == "свет":
                    # Avoid collision inside "совет", "посовет", "просвет"
                    if re.search(r'(?<![а-яa-z0-9])свет[а-я]*', q_lower):
                        score += 1
                    continue
                if kw == "муж":
                    # Avoid collision inside "мужчина", "мужской", "мужество"
                    if re.search(r'(?<![а-яa-z0-9])муж(?!(чин|ск|еств|еск|ик))[а-я]*', q_lower):
                        score += 1
                    continue
                if kw in q_lower:
                    weight = 2 if (len(kw) > 6 or " " in kw) else 1
                    score += weight
            if score > 0:
                matched_scores[intent] = score

        if any(w in q_lower for w in [
            "спорн", "конфликт", "претензи", "требует исходник", "отдать raw", "исходники raw",
            "отмен", "перенос", "перенес", "заболе", "простуд", "погод", "дожд", "ливн", "гроз", "снегопад", "метел", "грипп", "форс-мажор"
        ]):
            matched_scores[IntentType.DISPUTE] = matched_scores.get(IntentType.DISPUTE, 0) + 10

        is_burnout = any(w in q_lower for w in ["выгоран", "выгоре", "ступор", "кризис", "ничего не хочет", "нет сил", "опускаются руки"])
        if is_burnout:
            matched_scores[IntentType.GENERAL] = matched_scores.get(IntentType.GENERAL, 0) + 15

        is_photozone = any(w in q_lower for w in ["фотозон", "декоратор"])
        if is_photozone:
            matched_scores[IntentType.PHOTO] = matched_scores.get(IntentType.PHOTO, 0) + 15

        is_introvert_reels = ("интроверт" in q_lower or "без лица" in q_lower or "без говорящей головы" in q_lower or "b-roll" in q_lower) and any(w in q_lower for w in ["reels", "рилс", "ролик", "видео"])
        is_stories_arc = any(w in q_lower for w in ["арк", "9", "яишк", "прогрев", "шагов", "сценари"]) and any(w in q_lower for w in ["сторис", "stories", "сториз"])

        if is_stories_arc:
            matched_scores[IntentType.STORIES] = matched_scores.get(IntentType.STORIES, 0) + 15
        if is_introvert_reels:
            matched_scores[IntentType.REELS] = matched_scores.get(IntentType.REELS, 0) + 15

        if not matched_scores:
            return RoutingDecision(
                primary_intent=IntentType.GENERAL,
                secondary_intents=[],
                compound_intents=["GENERAL"],
                specialized_system_prompt=SPECIALIZED_PROMPTS[IntentType.GENERAL],
                confidence=0.85,
                reasoning="General query matching default personal assistant flow"
            )
        sorted_intents = sorted(matched_scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_intents[0][0]
        secondary = [item[0] for item in sorted_intents[1:4]]
        compound_names = [primary.name] + [s.name for s in secondary]
        workflow_suggested = None
        if "фотодень" in q_lower or "запустить фотодень" in q_lower:
            workflow_suggested = "photoday_launch"
        elif is_burnout:
            workflow_suggested = "burnout_recovery"
        elif is_photozone:
            workflow_suggested = "photozone_prototyping"
        elif is_introvert_reels:
            workflow_suggested = "introvert_reels"
        elif is_stories_arc:
            workflow_suggested = "nine_step_stories"
        elif any(w in q_lower for w in ["отмен", "перенос", "перенес", "заболе", "простуд", "дожд", "ливн", "гроз", "снегопад", "метел", "грипп", "форс-мажор"]):
            workflow_suggested = "cancellation_mediation"
        elif "нечего выложить" in q_lower or "нет идей" in q_lower or "что выложить" in q_lower:
            workflow_suggested = "no_content_emergency"
        elif "переписк" in q_lower and ("клиент" in q_lower or "пропал" in q_lower or "дорого" in q_lower):
            workflow_suggested = "client_chat_analysis"
        elif ("подготов" in q_lower or "концепц" in q_lower) and ("съемк" in q_lower or "съёмк" in q_lower):
            workflow_suggested = "shoot_preparation"
        elif "что мне сегодня делать" in q_lower or "план на день" in q_lower or primary == IntentType.DAILY_PLAN:
            workflow_suggested = "daily_planning"
        elif primary == IntentType.VOICE or IntentType.VOICE in secondary:
            workflow_suggested = "voice_to_content"
        elif primary == IntentType.PROFILE_AUDIT:
            workflow_suggested = "account_audit"
        elif primary == IntentType.PRICING or ("прайс" in q_lower and "пост" in q_lower):
            workflow_suggested = "pricing_strategy"
        elif primary == IntentType.MOODBOARD or ("мудборд" in q_lower or ("образ" in q_lower and "съемк" in q_lower)):
            workflow_suggested = "moodboard_creation"
        elif primary == IntentType.DISPUTE or ("спор" in q_lower or "конфликт" in q_lower):
            workflow_suggested = "dispute_mediation"
        elif primary == IntentType.MUSIC or any(w in q_lower for w in ["подбор трек", "подбери трек", "подборка трек", "треки для", "трек для"]) or bool(re.search(r'музык[а-я]* для|саундтрек[а-я]* к', q_lower)):
            workflow_suggested = "music_selection"
        missing_vars: List[str] = []
        clarifying_questions: List[str] = []
        action_type = "DIRECT"
        if workflow_suggested == "photoday_launch":
            action_type = "WORKFLOW"
            has_genre = False
            has_pricing = False
            has_location = False
            if context:
                prof = context.get("profile")
                if prof and getattr(prof, "genres", None):
                    has_genre = True
                if prof and getattr(prof, "pricing", None):
                    has_pricing = True
                proj = context.get("project")
                if proj and getattr(proj, "location", None):
                    has_location = True
            if not has_location and ("где" not in q_lower and "студи" not in q_lower and "локаци" not in q_lower):
                missing_vars.append("location_or_studio")
            if "дат" not in q_lower and "числ" not in q_lower and "сезон" not in q_lower and "когда" not in q_lower:
                missing_vars.append("date_or_season")
            if missing_vars and ("быстро" not in q_lower and "сделай всё сам" not in q_lower):
                if "date_or_season" in missing_vars:
                    clarifying_questions.append("На какую дату или сезон (например, ближайшие выходные, золотая осень) планируем фотодень?")
                if "location_or_studio" in missing_vars:
                    clarifying_questions.append("Есть ли уже конкретная локация/студия на примете, или подберем вместе под твой стиль?")
                if clarifying_questions:
                    action_type = "CLARIFY"
        required_tools = []
        if primary in [IntentType.PHOTO, IntentType.MOODBOARD] or IntentType.MOODBOARD in secondary:
            required_tools.append("image_generation")
        if primary == IntentType.KNOWLEDGE_SEARCH or IntentType.KNOWLEDGE_SEARCH in secondary:
            required_tools.append("knowledge_retrieval")
        if primary == IntentType.VOICE or IntentType.VOICE in secondary:
            required_tools.append("stt_transcription")
        reasoning = f"Detected primary intent '{primary.value}' with secondary intents: {[s.value for s in secondary]}"
        if workflow_suggested:
            reasoning += f" | workflow={workflow_suggested}"
        return RoutingDecision(
            primary_intent=primary, secondary_intents=secondary, compound_intents=compound_names,
            specialized_system_prompt=SPECIALIZED_PROMPTS.get(primary, SPECIALIZED_PROMPTS[IntentType.GENERAL]),
            required_tools=required_tools, confidence=0.92, reasoning=reasoning,
            missing_variables=missing_vars, clarifying_questions=clarifying_questions,
            workflow_suggested=workflow_suggested, action_type=action_type
        )
