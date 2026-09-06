"""
Agent Router for Intent Classification and Multi-Agent Specialization.
"""
import re
from typing import List, Dict, Set, Tuple
from src.brain.models.routing import IntentType, RoutingDecision

INTENT_KEYWORDS: Dict[IntentType, List[str]] = {
    IntentType.PHOTO: [
        "свет", "съемк", "камер", "объектив", "диафрагм", "выдержк", "iso", "портрет",
        "софтбокс", "рефлектор", "позирован", "ракурс", "кадр", "экспозици",
        "фокус", "вспышк", "студийный свет", "схема света", "октобокс"
    ],
    IntentType.CONTENT: [
        "пост", "текст", "стать", "контент", "блог", "тема для", "о чем написать",
        "заголовок", "рубрик", "план публикаци"
    ],
    IntentType.REELS: [
        "reels", "рилс", "сценарий", "видео", "ролик", "хук", "хронометраж", "динамик",
        "раскадровк"
    ],
    IntentType.STORIES: [
        "сторис", "stories", "прогрев", "интерактив", "опрос", "окошко", "сториз"
    ],
    IntentType.SALES: [
        "дорого", "дешев", "дешевле", "возражен", "клиент говорит", "как ответить", "продать", "скидк",
        "скрипт", "лид", "заявк", "переписк", "аргументир", "обоснова", "отказ", "конверси"
    ],
    IntentType.PRICING: [
        "цена", "прайс", "пакет", "стоимость", "тариф", "сколько стоит", "чек", "расценк"
    ],
    IntentType.CLIENT: [
        "клиент", "клиентк", "заказчик", "невеста", "модель", "девушк", "анна", "мария",
        "общение с клиентом", "бюджет клиента", "пожелания клиент"
    ],
    IntentType.PROJECT: [
        "проект", "фотодень", "фотодня", "фотодне", "воркшоп", "кампейн", "дедлайн", "дедлайны",
        "статус подготовки", "подготовк", "решение по", "съемочный день", "тайминг"
    ],
    IntentType.MOODBOARD: [
        "мудборд", "moodboard", "референсы", "визуал", "концепт", "палитра", "стилистик", "образ"
    ],
    IntentType.MARKETING: [
        "продвижен", "маркетинг", "трафик", "реклам", "таргет", "упаковк", "аудитори",
        "позиционирован", "воронк"
    ],
    IntentType.PROFILE_AUDIT: [
        "шапк", "аудит", "аккаунт", "профиль", "биографи", "оформлен", "визитк"
    ],
    IntentType.KNOWLEDGE_SEARCH: [
        "что такое", "объясни", "архив", "база знани", "по регламенту", "по инструкции", "согласно"
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
    IntentType.MOODBOARD: "Фокус: Арт-дирекшн, визуальные ассоциации, работа с колористикой, текстурами, стилем моделей и светом.",
    IntentType.MARKETING: "Фокус: Маркетинговая стратегия, поиск платежеспособной аудитории и отстройка от конкурентов.",
    IntentType.PROFILE_AUDIT: "Фокус: Упаковка личного бренда фотографа и оптимизация конверсии профиля.",
    IntentType.KNOWLEDGE_SEARCH: "Фокус: Точный поиск и синтез информации из базы знаний фотографа с обязательной ссылкой на источники.",
    IntentType.GENERAL: "Фокус: Комплексный персональный ассистент фотографа."
}

class AgentRouter:
    def __init__(self):
        pass

    def route(self, query: str) -> RoutingDecision:
        q_lower = query.lower()
        matched_scores: Dict[IntentType, int] = {}
        
        for intent, kws in INTENT_KEYWORDS.items():
            score = 0
            for kw in kws:
                if kw in q_lower:
                    weight = 2 if (len(kw) > 6 or " " in kw) else 1
                    score += weight
            if score > 0:
                matched_scores[intent] = score
                
        if not matched_scores:
            return RoutingDecision(
                primary_intent=IntentType.GENERAL,
                secondary_intents=[],
                specialized_system_prompt=SPECIALIZED_PROMPTS[IntentType.GENERAL],
                confidence=0.85,
                reasoning="General query matching default personal assistant flow"
            )
            
        # Sort by score descending
        sorted_intents = sorted(matched_scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_intents[0][0]
        secondary = [item[0] for item in sorted_intents[1:4]]
        
        # Determine tools
        required_tools = []
        if primary in [IntentType.PHOTO, IntentType.MOODBOARD] or IntentType.MOODBOARD in secondary:
            required_tools.append("image_generation")
        if primary == IntentType.KNOWLEDGE_SEARCH or IntentType.KNOWLEDGE_SEARCH in secondary:
            required_tools.append("knowledge_retrieval")
            
        reasoning = f"Detected primary intent '{primary.value}' with secondary intents: {[s.value for s in secondary]}"
        
        return RoutingDecision(
            primary_intent=primary,
            secondary_intents=secondary,
            specialized_system_prompt=SPECIALIZED_PROMPTS.get(primary, SPECIALIZED_PROMPTS[IntentType.GENERAL]),
            required_tools=required_tools,
            confidence=0.92,
            reasoning=reasoning
        )
