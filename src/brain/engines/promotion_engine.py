"""Evidence-safe promotion workflows for photographers."""
from __future__ import annotations

import re
from typing import Any, Optional

from src.brain.models.profile import UserProfile


class PromotionEngine:
    @staticmethod
    def _ctx(profile: Optional[UserProfile]) -> dict[str, str]:
        return {
            "niche": getattr(profile, "niche", None) or "авторская фотография",
            "city": getattr(profile, "city", None) or "город не указан",
            "audience": getattr(profile, "audience", None) or "клиенты съёмок",
        }

    def build_monthly_strategy(self, profile=None, goal="стабильные целевые обращения", use_llm=True) -> dict[str, Any]:
        c = self._ctx(profile)
        return {
            "positioning": f"{c['niche']} в {c['city']}: понятный результат, подготовка и прозрачный процесс.",
            "goal": goal,
            "weekly_sprints": [
                {"week": 1, "focus": "Упаковка", "actions": ["Проверить нишу, город, ценность и CTA", "Закрепить реальный кейс", "Собрать вопросы клиентов"]},
                {"week": 2, "focus": "Охват", "actions": ["Два Reels с разными хуками", "Одна коллаборация", "Опрос в Stories"]},
                {"week": 3, "focus": "Продажи", "actions": ["Разобрать тариф через результат", "Показать процесс", "Оффер только с подтверждёнными условиями"]},
                {"week": 4, "focus": "Повторные продажи", "actions": ["Follow-up прошлым клиентам", "Отзыв с разрешением", "Сравнить фактические KPI"]},
            ],
            "kpis": ["целевые обращения", "диалоги", "сохранения", "переходы к условиям", "бронирования"],
            "measurement_note": "Сначала заполните базовые KPI: система не имеет live-аналитики аккаунта.",
        }

    def generate_collaboration_ideas(self, profile=None, use_llm=True):
        c = self._ctx(profile)
        pairs = [("визажист/стилист", "образ и backstage"), ("студия", "демо локации"), ("бренд одежды", "editorial-серия"), ("эксперт близкой ниши", "история бренда"), ("организатор событий", "портретная мини-зона")]
        return [{"partner": p, "value": v, "mechanic": "Один пилот, взаимная маркировка и измеримый CTA", "message": f"Здравствуйте! Я работаю в направлении «{c['niche']}» в {c['city']}. Предлагаю пилот: {v}. Пришлю концепт на одну страницу?", "metric": "целевые диалоги с пометкой партнёра"} for p, v in pairs]

    def build_hashtag_clusters(self, profile=None, use_llm=True):
        c = self._ctx(profile)
        niche = re.sub(r"[^а-яa-z0-9]+", "", c["niche"].lower())[:25] or "фотограф"
        city = re.sub(r"[^а-яa-z0-9]+", "", c["city"].lower())[:20]
        return {"geo": [f"#фотограф{city}", f"#фотосессия{city}", "#локальныйфотограф"], "service": [f"#{niche}", "#портретнаясъемка", "#семейнаяфотосессия", "#контентсъемка"], "intent": ["#подготовкакфотосессии", "#какпозировать", "#идеидляфотосессии", "#записьнафотосессию"], "note": "Частотность и ограничения проверьте непосредственно в соцсети."}

    def analyze_competitors(self, notes: str, profile=None, use_llm=True):
        if not notes.strip():
            raise ValueError("Добавьте материалы минимум по двум конкурентам.")
        c = self._ctx(profile)
        return {"observations": [x.strip(" •-") for x in notes.splitlines() if x.strip()][:8], "gaps_to_validate": ["ясность процесса", "CTA и тарифы", "подтверждённые кейсы"], "differentiation": f"Для «{c['niche']}» покажите свой процесс, реальные серии и поддержку клиента.", "evidence_scope": "Только материалы пользователя; live-аккаунты не просматривались."}

    def build_client_newsletter(self, offer: str, profile=None, use_llm=True):
        if not offer.strip():
            raise ValueError("Опишите подтверждённый оффер или новость.")
        return {"subjects": ["Продолжим вашу фотоисторию?", "Новая глава для знакомых героев", f"Идея съёмки: {offer[:50]}"], "body": f"Здравствуйте! Подумал(а) о продолжении нашей фотоистории. {offer.strip()}\n\nЕсли идея откликается, ответьте — пришлю актуальные условия и проверю подходящий формат.", "cta": "Ответить и получить актуальные условия", "note": "Персонализируйте первую строку и не создавайте ложный дефицит."}

    def build_campaign_offer(self, idea: str, profile=None, use_llm=True):
        if not idea.strip():
            raise ValueError("Опишите услугу, сезон или задачу.")
        return {"problem": "Клиенту сложно собрать идею, образ и план", "promise": f"{idea.strip()}: понятный путь от брифа до серии", "deliverables": ["бриф", "мудборд", "согласованный план", "объём и срок из договора"], "proof_needed": ["реальный кейс", "отзыв с разрешением", "серия целиком"], "cta": "Опишите задачу и месяц — предложу формат после проверки календаря."}

    def repurpose_review(self, review: str, profile=None, use_llm=True):
        if len(review.strip()) < 15:
            raise ValueError("Пришлите реальный текст отзыва.")
        return {"quote": review.strip(), "stories": ["Страх до съёмки", review.strip(), "Как проходит подготовка + CTA"], "post_outline": ["страх", "процесс", "точная цитата", "вывод", "CTA"], "permission_note": "Получите разрешение на имя, переписку и фотографии."}
