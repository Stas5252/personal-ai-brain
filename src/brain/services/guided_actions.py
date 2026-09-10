"""Stateful user-facing actions shared by Telegram and API clients."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.brain.engines.promotion_engine import PromotionEngine
from src.brain.services.pricing import PriceNotFound, format_money, parse_base_price


class MissingActionInput(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    action_id: str
    label: str
    prompt: str = ""
    image: bool = False

    @property
    def requires_input(self):
        return bool(self.prompt)


_RAW = (
("content.reels","🎥 Идеи Reels","О чём и для кого нужны Reels?",0),("content.week","📝 Контент-план","",0),("content.stories","📖 Сторис-арка","Назови тему и оффер.",0),("content.caption","✍️ Подпись к фото","Опиши реальную историю и цель.",1),("content.post","💡 Идея поста","Назови тему или вопрос клиента.",0),("content.script","🎙️ Сценарий Reels","Назови тему, аудиторию и длительность.",0),("content.hooks","🔥 Хуки для контента","",0),("content.rubrics","📅 Рубрикатор","",0),
("sales.dialogue","💬 Ответ клиенту","Пришли текст или скриншот переписки.",1),("sales.dispute","⚖️ Спорная ситуация","Опиши ситуацию или пришли претензию.",1),("sales.price","💰 Прайс-лист","Укажи базовую цену.",1),("sales.contract","📋 Договор","Опиши формат, страну и спорный пункт.",0),("sales.script","🎯 Скрипт продажи","Опиши услугу и клиента.",0),("sales.proposal","📊 КП клиенту","Опиши задачу и реальные условия.",0),("sales.repeat","🔄 Повторная продажа","Опиши прошлую съёмку и повод.",0),("sales.review","⭐ Запрос отзыва","Опиши завершённую съёмку.",0),
("shoot.moodboard","📸 Мудборд съёмки","Опиши идею или пришли фото локации.",1),("shoot.audit","✨ Разбор аккаунта","Пришли скриншот или текст профиля.",1),("shoot.critique","🔍 Разбор фото","Пришли фотографию.",1),("shoot.music","🎵 Подбор треков","Опиши серию и формат.",0),("shoot.outfits","👗 Образы клиента","Опиши героя, сезон и локацию.",0),("shoot.locations","📍 Локации","Укажи город, жанр и сезон.",0),("shoot.photoday","🗓️ Фотодень","Опиши тему, город и предполагаемый чек.",0),("shoot.brief","📦 Бриф клиента","Укажи жанр и тип клиента.",0),
("promo.strategy","📢 Стратегия продвижения","",0),("promo.collabs","🤝 Коллаборации","",0),("promo.tags","🏷️ Хэштеги","",0),("promo.competitors","📈 Анализ конкурентов","Пришли материалы минимум по двум конкурентам.",1),("promo.newsletter","💌 Email/рассылка","Опиши подтверждённый оффер.",0),("promo.offer","🎁 Акция/оффер","Опиши услугу, сезон и задачу.",0),("promo.reviews","🌟 Отзывы в контент","Пришли реальный текст отзыва.",0),("work.today","📅 План дня","",0))
ACTIONS = tuple(Action(a,b,c,bool(d)) for a,b,c,d in _RAW)
ACTION_BY_ID = {a.action_id:a for a in ACTIONS}
ACTION_BY_LABEL = {a.label:a for a in ACTIONS}


def capability_markdown():
    return "🧭 **32 guided-функции**\n\n" + "\n".join(f"• {a.label}" for a in ACTIONS) + "\n\nВыбери кнопку — бот запросит недостающие данные."


class GuidedActionService:
    def __init__(self):
        self.promo = PromotionEngine()

    def start(self, action_id):
        action = ACTION_BY_ID[action_id]
        return {"requires_input": action.requires_input, "accepts_image": action.image, "prompt": action.prompt}

    @staticmethod
    def _format(value):
        if isinstance(value, dict): return "\n\n".join(f"**{str(k).replace('_',' ').capitalize()}**\n{GuidedActionService._format(v)}" for k,v in value.items())
        if isinstance(value, list): return "\n".join(f"• {GuidedActionService._format(x)}" for x in value)
        return str(value)

    @staticmethod
    def _chat(brain, task, text=""):
        result = brain.process_chat(query=f"{task}\n\nВходные данные:\n{text}".strip(), auto_admission=False)
        if result.get("status_code") != 200: raise RuntimeError("LLM request failed")
        return {"result": result.get("response", "")}

    @staticmethod
    def _vision(brain, path, prompt):
        result = brain.shooting_engine.critique_shot(path, prompt=prompt)
        if result.get("status") != "AVAILABLE" or not result.get("description"): raise ValueError("Vision недоступен; пришли данные текстом.")
        return result["description"]

    def execute(self, action_id, brain, text="", image_path=None, use_llm=True):
        action = ACTION_BY_ID[action_id]
        if action.requires_input and not text.strip() and not image_path: raise MissingActionInput(action.prompt)
        profile = brain.profile_engine.get_profile()
        generic = {
        "content.reels":"Создай 5 идей Reels: аудитория, хук, визуал, текст, звук, CTA.","content.caption":"Подпись: хук, только реальные факты, смысл и CTA.","content.post":"Идея и каркас живого поста без клише.","content.script":"Сценарий Reels с таймкодами, кадрами и CTA.","content.hooks":"10 разных хуков под профиль без выдуманных цифр.","content.rubrics":"7 рубрик на месяц: цель, частота, темы и CTA.","sales.contract":"Информационный чек-лист договора и вопросы местному юристу; не юридическое заключение.","sales.script":"Бережный скрипт продажи: квалификация, ценность, два выбора.","sales.review":"Два мягких запроса честного отзыва.","sales.repeat":"Персональная реактивация только по данным пользователя.","shoot.outfits":"5 образов: цвет, фактура, обувь, аксессуары и стоп-лист.","shoot.locations":"5 типов локаций и критерии света, разрешений, погоды и логистики; без выдуманных адресов.","shoot.photoday":"Пакет запуска фотодня; цены, даты и слоты только из входных данных.","shoot.brief":"Клиентский бриф: цель, визуал, ограничения, сроки, публикация и согласия."}
        if action_id in generic:
            source = text
            if image_path: source += "\n" + self._vision(brain,image_path,"Опиши только видимые факты.")
            data = self._chat(brain,generic[action_id],source)
        elif action_id=="content.week": data=brain.content_engine.build_content_sprint_plan(profile=profile,days=7,use_llm=use_llm)
        elif action_id=="content.stories": data=brain.content_engine.generate_nine_step_stories_arc(text,profile=profile,use_llm=use_llm)
        elif action_id=="sales.dialogue":
            source=text+(("\n"+self._vision(brain,image_path,"Транскрибируй видимую переписку.")) if image_path else ""); data=brain.sales_engine.analyze_client_dialogue(source,use_llm=use_llm)
        elif action_id=="sales.dispute":
            source=text+(("\n"+self._vision(brain,image_path,"Транскрибируй претензию.")) if image_path else "")
            data=brain.sales_engine.handle_cancellation_and_reschedule(source,use_llm=use_llm) if any(w in source.lower() for w in ("отмен","перенос","погод","забол")) else brain.sales_engine.mediate_client_dispute(source,profile=profile,use_llm=use_llm)
        elif action_id=="sales.price":
            # A price list is a business decision. If the owner did not state a
            # base price we ask for one instead of inventing a number that
            # would quietly become their real pricing.
            source=text+(("\n"+self._vision(brain,image_path,"Перепиши видимые цены и услуги дословно.")) if image_path else "")
            try: base=parse_base_price(source)
            except PriceNotFound as exc: raise MissingActionInput(str(exc)) from exc
            shared="объём и срок — только из договора"
            data={"status":"draft","base_price":format_money(base),"tiers":[{"name":"ЛАЙТ","price":format_money(int(base*.7)),"features":["бриф","одна концепция",shared]},{"name":"ОПТИМАЛЬНЫЙ","price":format_money(base),"features":["мудборд","поддержка с образом",shared]},{"name":"ПРЕМИУМ","price":format_money(int(base*1.6)),"features":["продюсирование","несколько сцен",shared]}],"note":"База взята из твоих данных. Проверьте себестоимость, налог, предоплату и сроки."}
        elif action_id=="sales.proposal": data=self.promo.build_campaign_offer(text,profile,use_llm)
        elif action_id=="shoot.moodboard":
            location=self._vision(brain,image_path,"Опиши свет, цвета, фактуры и ограничения локации.") if image_path else ""; data=brain.shooting_engine.generate_moodboard_card(text or "Концепция по локации",location=location,use_llm=use_llm)
        elif action_id=="shoot.audit": data=brain.shooting_engine.audit_profile_and_grid(image_path or text,profile=profile,use_llm=use_llm)
        elif action_id=="shoot.critique":
            if not image_path: raise MissingActionInput(action.prompt)
            data=brain.shooting_engine.analyze_photo_with_critique(image_path,user_question=text or None)
        elif action_id=="shoot.music":
            data=brain.shooting_engine.recommend_music_soundtrack(text,use_llm=use_llm); data["licensing_note"]="Проверьте доступность и лицензию трека."
        elif action_id=="promo.strategy": data=self.promo.build_monthly_strategy(profile,use_llm=use_llm)
        elif action_id=="promo.collabs": data=self.promo.generate_collaboration_ideas(profile,use_llm)
        elif action_id=="promo.tags": data=self.promo.build_hashtag_clusters(profile,use_llm)
        elif action_id=="promo.competitors": data=self.promo.analyze_competitors(text,profile,use_llm)
        elif action_id=="promo.newsletter": data=self.promo.build_client_newsletter(text,profile,use_llm)
        elif action_id=="promo.offer": data=self.promo.build_campaign_offer(text,profile,use_llm)
        elif action_id=="promo.reviews": data=self.promo.repurpose_review(text,profile,use_llm)
        elif action_id=="work.today": data=brain.proactive_engine.generate_daily_plan(profile=profile,use_llm=use_llm)
        else: raise KeyError(action_id)
        return {"action_id":action_id,"title":action.label,"data":data,"markdown":f"✅ **{action.label}**\n\n{self._format(data)}"}
