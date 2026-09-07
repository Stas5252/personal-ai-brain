"""
Layer Classifier for Knowledge Ingestion Factory.
Classifies sources into 6 layers with confidence and explainable classification method.
"""
from typing import Tuple, Optional, Dict, Any, List
from src.brain.models.knowledge import KnowledgeLayer, ClassificationMethod

LAYER_KEYWORDS = {
    KnowledgeLayer.GLOBAL: [
        "теория", "физика", "оптика", "экспозиция", "выдержка", "диафрагма", "iso",
        "цветовой круг", "иттен", "правило третей", "глубина резкости", "баланс белого"
    ],
    KnowledgeLayer.PROFESSIONAL: [
        "схема света", "октобокс", "софтбокс", "бьюти-диш", "рефлектор", "позирование",
        "модификатор", "портретная съемка", "бабочка", "рембрандт", "заполняющий свет",
        "моделирование", "ракурс", "ретушь", "кожа", "штрихи", "свет", "съемка", "рилс",
        "reels", "монтаж", "кадр", "визуал", "композиция", "цвет", "чб", "hypic", "lightroom",
        "photoshop", "обработка", "камера", "объектив", "настройки", "локация", "модель",
        "мудборд", "референс", "промт", "нейросети", "видео", "сценарий", "модели"
    ],
    KnowledgeLayer.PERSONAL: [
        "мой стиль", "мой подход", "авторский", "манифест", "философия", "обо мне",
        "почему я", "творческий", "вдохновение", "эстетика", "почерк", "личный бренд",
        "блог", "ведение блога", "сторис", "сторителлинг", "проявление", "состояние",
        "выгорание", "мышление", "уверенность", "позиционирование"
    ],
    KnowledgeLayer.BUSINESS: [
        "прайс", "пакет", "руб", "рублей", "цена", "стоимость", "договор", "оплата",
        "предоплата", "бронирование", "тариф", "услуги", "коммерческое", "смета",
        "продажи", "рассылки", "возражения", "оффер", "офферы", "клиентская база",
        "прогрев", "чек", "доход", "заработок", "монетизация", "воронка", "лидогенерация",
        "переговоры", "скрипт", "спринт", "ценности", "выгоды", "триггеры", "продающий"
    ],
    KnowledgeLayer.PROJECT: [
        "проект", "съемочный день", "тайминг", "кампейн", "фотодень", "воркшоп",
        "дедлайн", "лукбук", "коллекция", "локация", "бриф"
    ],
    KnowledgeLayer.CLIENT: [
        "клиент", "заказчик", "невеста", "модель", "пожелания", "референсы заказчика",
        "анна", "екатерина", "мария", "частная съемка", "фигура", "гардероб", "общение",
        "клиентская база", "коммуникация", "отзывы", "сервис", "лояльность"
    ]
}

class LayerClassifier:
    def __init__(self):
        pass

    def classify(
        self,
        title: str,
        text_snippet: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[KnowledgeLayer, float, ClassificationMethod, str]:
        """
        Classifies content into one of 6 layers.
        Returns (layer, confidence, method, reasoning).
        """
        meta = metadata or {}
        
        # 1. Explicit metadata / user specification
        if meta.get("layer"):
            try:
                layer = KnowledgeLayer(meta["layer"])
                return layer, 1.0, ClassificationMethod.MANUAL, "Specified explicitly via metadata"
            except ValueError:
                pass

        if meta.get("client") or meta.get("client_id"):
            return KnowledgeLayer.CLIENT, 0.95, ClassificationMethod.METADATA, "Bound to specific client_id"

        if meta.get("project") or meta.get("project_id"):
            return KnowledgeLayer.PROJECT, 0.95, ClassificationMethod.METADATA, "Bound to specific project_id"

        # 2. Rule-based keyword matching on title and snippet
        combined = f"{title.lower()} {text_snippet[:2000].lower()}"
        scores: Dict[KnowledgeLayer, int] = {layer: 0 for layer in KnowledgeLayer}

        for layer, kws in LAYER_KEYWORDS.items():
            for kw in kws:
                if kw in combined:
                    weight = 3 if kw in title.lower() else 1
                    scores[layer] += weight

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_layer, top_score = sorted_scores[0]
        second_layer, second_score = sorted_scores[1]

        # 3. Confidence calculation
        if top_score >= 5:
            confidence = 0.92
            method = ClassificationMethod.RULES
            reasoning = f"High keyword match ({top_score} points) for {top_layer.value}"
        elif top_score >= 2:
            confidence = 0.75
            method = ClassificationMethod.RULES
            reasoning = f"Moderate keyword match ({top_score} points) for {top_layer.value}"
        else:
            # Low confidence -> REVIEW_REQUIRED
            confidence = 0.40
            method = ClassificationMethod.REVIEW_REQUIRED
            reasoning = f"Low confidence match ({top_score} points). Recommended for manual review."

        return top_layer, confidence, method, reasoning
