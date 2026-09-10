"""Evidence-safe promotion workflows for photographers."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from src.brain.models.profile import UserProfile

# Keys that carry a factual guarantee: scope of evidence, permissions, the
# owner's own words. The model may rewrite wording elsewhere, but never these —
# they are the difference between an honest draft and an invented claim.
_LOCKED_KEYS = frozenset({
    "measurement_note",
    "evidence_scope",
    "permission_note",
    "note",
    "licensing_note",
    "proof_needed",
    "observations",
    "quote",
    "stories",
    "goal",
})

_SYSTEM = (
    "Ты — маркетолог фотографа. Верни строго JSON с теми же ключами и типами, что в шаблоне. "
    "Улучшай только формулировки: конкретнее, живее, без клише и без воды. "
    "Запрещено придумывать цифры, охваты, кейсы, отзывы, даты, цены, адреса и названия брендов, "
    "которых нет во входных данных. Никакого текста вне JSON."
)


class PromotionEngine:
    """Template first, model second.

    Every method returns a usable draft with zero network calls. When
    ``use_llm=True`` the model is allowed to rewrite the wording of existing
    keys only. If it is unavailable, returns malformed JSON, changes types or
    invents new fields, the deterministic template is returned unchanged — so
    ``use_llm`` is a real switch, not a parameter that is quietly ignored.
    """

    _LLM_FAILURE_LIMIT = 3
    _BREAKER_SECONDS = 300.0
    _llm_failures = 0
    _llm_blocked_until = 0.0

    @staticmethod
    def _ctx(profile: Optional[UserProfile]) -> dict[str, str]:
        return {
            "niche": getattr(profile, "niche", None) or "авторская фотография",
            "city": getattr(profile, "city", None) or "город не указан",
            "audience": getattr(profile, "audience", None) or "клиенты съёмок",
        }

    # -- model-assisted rewriting -------------------------------------------
    @classmethod
    def _note_failure(cls) -> None:
        """Stops hammering a dead endpoint; retries again after the cooldown."""
        cls._llm_failures += 1
        if cls._llm_failures >= cls._LLM_FAILURE_LIMIT:
            cls._llm_blocked_until = time.monotonic() + cls._BREAKER_SECONDS
            cls._llm_failures = 0

    @classmethod
    def _note_success(cls) -> None:
        cls._llm_failures = 0
        cls._llm_blocked_until = 0.0

    @classmethod
    def _model_json(cls, task: str, evidence: str, skeleton: Any) -> Optional[dict[str, Any]]:
        if time.monotonic() < cls._llm_blocked_until:
            return None
        try:
            from src.brain.services.llm_provider import LLMProvider

            status, text, _, _ = LLMProvider().chat_completion(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Задача: {task}\n\n"
                            f"Данные пользователя:\n{(evidence or 'дополнительных данных нет').strip()}\n\n"
                            f"Шаблон JSON:\n{json.dumps(skeleton, ensure_ascii=False)}"
                        ),
                    },
                ],
                temperature=0.5,
                max_retries_per_model=1,
            )
        except Exception:
            cls._note_failure()
            return None
        if status != 200 or not text:
            cls._note_failure()
            return None
        raw = re.sub(r"^```[a-zA-Z]*|```$", "", str(text).strip()).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            cls._note_failure()
            return None
        try:
            parsed = json.loads(raw[start:end + 1])
        except ValueError:
            cls._note_failure()
            return None
        if not isinstance(parsed, dict):
            cls._note_failure()
            return None
        cls._note_success()
        return parsed

    @staticmethod
    def _merge(template: dict[str, Any], parsed: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Accepts rewritten wording only: same key, same type, never locked."""
        if not parsed:
            return template
        merged = dict(template)
        for key, value in parsed.items():
            if key in _LOCKED_KEYS or key not in merged:
                continue
            current = merged[key]
            if isinstance(current, str) and isinstance(value, str) and value.strip():
                merged[key] = value.strip()
            elif isinstance(current, list) and isinstance(value, list) and all(isinstance(x, str) for x in current):
                cleaned = [v.strip() for v in value if isinstance(v, str) and v.strip()]
                if cleaned:
                    merged[key] = cleaned
        return merged

    @classmethod
    def _refine(cls, template: dict[str, Any], task: str, evidence: str = "", use_llm: bool = True) -> dict[str, Any]:
        if not use_llm:
            return template
        return cls._merge(template, cls._model_json(task, evidence, template))

    @classmethod
    def _refine_items(cls, items: list[dict[str, Any]], task: str, evidence: str = "", use_llm: bool = True) -> list[dict[str, Any]]:
        if not use_llm or not items:
            return items
        parsed = cls._model_json(task, evidence, {"items": items})
        values = (parsed or {}).get("items")
        if not isinstance(values, list) or len(values) != len(items):
            return items
        return [cls._merge(base, value) if isinstance(value, dict) else base for base, value in zip(items, values)]

    # -- workflows ----------------------------------------------------------
    def build_monthly_strategy(self, profile=None, goal="стабильные целевые обращения", use_llm=True) -> dict[str, Any]:
        c = self._ctx(profile)
        template = {
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
        return self._refine(template, f"План продвижения на месяц. Ниша: {c['niche']}. Город: {c['city']}. Цель: {goal}.", f"Аудитория: {c['audience']}", use_llm)

    def generate_collaboration_ideas(self, profile=None, use_llm=True):
        c = self._ctx(profile)
        pairs = [("визажист/стилист", "образ и backstage"), ("студия", "демо локации"), ("бренд одежды", "editorial-серия"), ("эксперт близкой ниши", "история бренда"), ("организатор событий", "портретная мини-зона")]
        items = [{"partner": p, "value": v, "mechanic": "Один пилот, взаимная маркировка и измеримый CTA", "message": f"Здравствуйте! Я работаю в направлении «{c['niche']}» в {c['city']}. Предлагаю пилот: {v}. Пришлю концепт на одну страницу?", "metric": "целевые диалоги с пометкой партнёра"} for p, v in pairs]
        return self._refine_items(items, f"Пять коллабораций для ниши «{c['niche']}» в городе {c['city']}. Сохрани ровно пять пунктов и все ключи.", f"Аудитория: {c['audience']}", use_llm)

    def build_hashtag_clusters(self, profile=None, use_llm=True):
        c = self._ctx(profile)
        niche = re.sub(r"[^а-яa-z0-9]+", "", c["niche"].lower())[:25] or "фотограф"
        city = re.sub(r"[^а-яa-z0-9]+", "", c["city"].lower())[:20]
        template = {"geo": [f"#фотограф{city}", f"#фотосессия{city}", "#локальныйфотограф"], "service": [f"#{niche}", "#портретнаясъемка", "#семейнаяфотосессия", "#контентсъемка"], "intent": ["#подготовкакфотосессии", "#какпозировать", "#идеидляфотосессии", "#записьнафотосессию"], "note": "Частотность и ограничения проверьте непосредственно в соцсети."}
        return self._refine(template, f"Кластеры хэштегов для ниши «{c['niche']}» в городе {c['city']}. Только валидные теги без пробелов.", f"Аудитория: {c['audience']}", use_llm)

    def analyze_competitors(self, notes: str, profile=None, use_llm=True):
        if not notes.strip():
            raise ValueError("Добавьте материалы минимум по двум конкурентам.")
        c = self._ctx(profile)
        template = {"observations": [x.strip(" •-") for x in notes.splitlines() if x.strip()][:8], "gaps_to_validate": ["ясность процесса", "CTA и тарифы", "подтверждённые кейсы"], "differentiation": f"Для «{c['niche']}» покажите свой процесс, реальные серии и поддержку клиента.", "evidence_scope": "Только материалы пользователя; live-аккаунты не просматривались."}
        return self._refine(template, f"Разбор конкурентов для ниши «{c['niche']}». Опирайся только на присланные заметки.", notes, use_llm)

    def build_client_newsletter(self, offer: str, profile=None, use_llm=True):
        if not offer.strip():
            raise ValueError("Опишите подтверждённый оффер или новость.")
        template = {"subjects": ["Продолжим вашу фотоисторию?", "Новая глава для знакомых героев", f"Идея съёмки: {offer[:50]}"], "body": f"Здравствуйте! Подумал(а) о продолжении нашей фотоистории. {offer.strip()}\n\nЕсли идея откликается, ответьте — пришлю актуальные условия и проверю подходящий формат.", "cta": "Ответить и получить актуальные условия", "note": "Персонализируйте первую строку и не создавайте ложный дефицит."}
        return self._refine(template, "Письмо клиентской базе по подтверждённому офферу. Без дедлайнов и скидок, которых нет во входных данных.", offer, use_llm)

    def build_campaign_offer(self, idea: str, profile=None, use_llm=True):
        if not idea.strip():
            raise ValueError("Опишите услугу, сезон или задачу.")
        template = {"problem": "Клиенту сложно собрать идею, образ и план", "promise": f"{idea.strip()}: понятный путь от брифа до серии", "deliverables": ["бриф", "мудборд", "согласованный план", "объём и срок из договора"], "proof_needed": ["реальный кейс", "отзыв с разрешением", "серия целиком"], "cta": "Опишите задачу и месяц — предложу формат после проверки календаря."}
        return self._refine(template, "Оффер/КП по задаче пользователя. Цены и сроки не выдумывать.", idea, use_llm)

    def repurpose_review(self, review: str, profile=None, use_llm=True):
        if len(review.strip()) < 15:
            raise ValueError("Пришлите реальный текст отзыва.")
        template = {"quote": review.strip(), "stories": ["Страх до съёмки", review.strip(), "Как проходит подготовка + CTA"], "post_outline": ["страх", "процесс", "точная цитата", "вывод", "CTA"], "permission_note": "Получите разрешение на имя, переписку и фотографии."}
        return self._refine(template, "Как раскатать реальный отзыв в контент. Цитату не переписывать.", review, use_llm)
