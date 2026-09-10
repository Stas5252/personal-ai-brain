"""Stateful user-facing actions shared by Telegram and API clients."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.brain.engines import visual_identity as vi
from src.brain.engines.image_engine import STATUS_AVAILABLE, ImageEngine
from src.brain.engines.promotion_engine import PromotionEngine
from src.brain.services import reference_intake as intake
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
("content.reels","🎥 Идеи Reels","О чём и для кого нужны Reels?",0),("content.week","📝 Контент-план","",0),("content.stories","📖 Сторис-арка","Назови тему и оффер.",0),("content.caption","\u270d\ufe0f Подпись к фото","Опиши реальную историю и цель.",1),("content.post","💡 Идея поста","Назови тему или вопрос клиента.",0),("content.script","\ud83c\udf99\ufe0f Сценарий Reels","Назови тему, аудиторию и длительность.",0),("content.hooks","🔥 Хуки для контента","",0),("content.rubrics","📅 Рубрикатор","",0),
("sales.dialogue","💬 Ответ клиенту","Пришли текст или скриншот переписки.",1),("sales.dispute","\u2696\ufe0f Спорная ситуация","Опиши ситуацию или пришли претензию.",1),("sales.price","💰 Прайс-лист","Укажи базовую цену.",1),("sales.contract","📋 Договор","Опиши формат, страну и спорный пункт.",0),("sales.script","🎯 Скрипт продажи","Опиши услугу и клиента.",0),("sales.proposal","📊 КП клиенту","Опиши задачу и реальные условия.",0),("sales.repeat","🔄 Повторная продажа","Опиши прошлую съёмку и повод.",0),("sales.review","⭐ Запрос отзыва","Опиши завершённую съёмку.",0),
("shoot.moodboard","📸 Мудборд съёмки","Опиши идею или пришли фото локации.",1),("shoot.audit","✨ Разбор аккаунта","Пришли скриншот или текст профиля.",1),("shoot.critique","🔍 Разбор фото","Пришли фотографию.",1),("shoot.music","🎵 Подбор треков","Опиши серию и формат.",0),("shoot.outfits","👗 Образы клиента","Опиши героя, сезон и локацию.",0),("shoot.locations","📍 Локации","Укажи город, жанр и сезон.",0),("shoot.photoday","\ud83d\uddd3\ufe0f Фотодень","Опиши тему, город и предполагаемый чек.",0),("shoot.brief","📦 Бриф клиента","Укажи жанр и тип клиента.",0),("shoot.generate","🎨 Сгенерировать фото","Опиши кадр: сцена, герой, свет, настроение.",1),("shoot.restyle","\u267b\ufe0f Перерисовать кадр","Пришли фото и напиши, что изменить.",1),("shoot.reference","🧬 Референс героя","Пришли фото и подпиши одним словом: лицо, фигура, стиль, локация или предмет.",1),("shoot.character","📇 Лист героя","Напиши приметы парами «поле: значение», например «волосы: русые до плеч».",0),("shoot.refset","📁 Набор для фото","",0),
("promo.strategy","📢 Стратегия продвижения","",0),("promo.collabs","🤝 Коллаборации","",0),("promo.tags","\ud83c\udff7\ufe0f Хэштеги","",0),("promo.competitors","📈 Анализ конкурентов","Пришли материалы минимум по двум конкурентам.",1),("promo.newsletter","💌 Email/рассылка","Опиши подтверждённый оффер.",0),("promo.offer","🎁 Акция/оффер","Опиши услугу, сезон и задачу.",0),("promo.reviews","🌟 Отзывы в контент","Пришли реальный текст отзыва.",0),("work.today","📅 План дня","",0))
ACTIONS = tuple(Action(a,b,c,bool(d)) for a,b,c,d in _RAW)
ACTION_BY_ID = {a.action_id:a for a in ACTIONS}
ACTION_BY_LABEL = {a.label:a for a in ACTIONS}
# Actions whose payload is a real file on disk instead of text. Telegram sends
# them as a photo, the HTTP API returns a download URL.
IMAGE_ACTIONS = frozenset({"shoot.generate", "shoot.restyle"})
# Actions that read or write the reference vault. They are the only path by
# which a stored face, a stored style and a character sheet reach generation,
# so they must stay reachable from the menu.
VAULT_ACTIONS = frozenset({"shoot.reference", "shoot.character", "shoot.refset"})


def capability_markdown():
    return f"🧭 **{len(ACTIONS)} guided-функции**\n\n" + "\n".join(f"• {a.label}" for a in ACTIONS) + "\n\nВыбери кнопку — бот запросит недостающие данные."


class GuidedActionService:
    def __init__(self):
        self.promo = PromotionEngine()
        self.images = ImageEngine()
        self._vault = None

    @property
    def vault(self):
        """Opened on first use only.

        Prices, plans and most tests never touch the vault, and they must not
        pay for a sqlite connection — several of them build the service with
        __new__ and no __init__ at all.
        """
        vault = getattr(self, "_vault", None)
        if vault is None:
            from src.brain.engines.reference_vault import ReferenceVault

            vault = ReferenceVault()
            self._vault = vault
        return vault

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

    # -- reference vault ----------------------------------------------------
    def _add_reference(self, text="", image_path=None):
        """Stores one photo under the role the owner named.

        The role is never guessed: a face filed as a location quietly poisons
        every later generation, and the owner would not see why.
        """
        if not image_path:
            raise MissingActionInput(ACTION_BY_ID["shoot.reference"].prompt)
        role = intake.detect_role(text)
        if not role:
            raise MissingActionInput(intake.role_prompt())
        try:
            stored = intake.store_reference_file(image_path)
        except (ValueError, OSError) as exc:
            raise MissingActionInput(str(exc)) from exc
        try:
            row = self.vault.add_reference(stored, role=role, note=intake.reference_note(text))
        except ValueError as exc:
            # The vault refused the bytes, so the copy we just made is junk.
            # Delete it, but only if no earlier reference already points there.
            try:
                known = any(str(item.get("path")) == str(stored) for item in self.vault.list_references())
            except Exception:
                known = True
            if not known:
                Path(stored).unlink(missing_ok=True)
            raise MissingActionInput(str(exc)) from exc
        active = self.vault.active_references()
        return {
            "status": "saved",
            "role": vi.ROLE_LABELS.get(row.get("role"), row.get("role")),
            "note": row.get("note") or "без заметки",
            "file": Path(str(row.get("path"))).name,
            "count": f"{len(active)} из {vi.MAX_REFERENCES}",
            "next": "Пришли ещё кадры с подписью роли или нажми «🎨 Сгенерировать фото».",
        }

    def _character_sheet(self, text=""):
        """Writes only the fields the owner typed; unknown keys are reported."""
        accepted, unknown = intake.parse_traits(text)
        if not accepted:
            hint = intake.trait_prompt()
            if unknown:
                hint = "Таких полей в листе героя нет: " + ", ".join(unknown) + ". " + hint
            raise MissingActionInput(hint)
        saved = {}
        rejected = [f"{key} — поля нет в листе героя" for key in unknown]
        for key, value in accepted.items():
            try:
                saved[key] = self.vault.set_trait(key, value)
            except ValueError as exc:
                rejected.append(f"{key} — {exc}")
        data = {"status": "saved", "fields": saved, "sheet": self.vault.character_sheet() or "пока пустой"}
        if rejected:
            data["rejected"] = rejected
        return data

    def _reference_set(self):
        """Shows what generation will actually receive, after pruning dead paths."""
        removed = self.vault.prune_missing()
        active = self.vault.active_references()
        rows = []
        for item in active:
            label = vi.ROLE_LABELS.get(item.get("role"), item.get("role"))
            note = str(item.get("note") or "").strip()
            name = Path(str(item.get("path"))).name
            rows.append(f"{label} — {name}" + (f" ({note})" if note else ""))
        sheet = str(self.vault.character_sheet() or "").strip()
        data = {
            "status": "ready" if (active or sheet) else "empty",
            "count": f"{len(active)} из {vi.MAX_REFERENCES}",
            "references": rows or ["пока пусто — кнопка «🧬 Референс героя»"],
            "sheet": sheet or "пока пустой — кнопка «📇 Лист героя»",
            "summary": self.vault.summary(),
        }
        if removed:
            data["cleaned"] = f"исчезнувших файлов убрано: {removed}"
        return data

    def _image(self, profile, text, image_path=None, use_llm=True):
        """Returns a real generated file or an explicit UNAVAILABLE reason."""
        references, traits, vault_error = [], {}, ""
        try:
            references = self.vault.active_references()
            traits = self.vault.traits()
        except Exception as exc:
            # A locked or missing database must not block generation: the frame
            # is still worth making, the owner is told the set was not read.
            references, traits, vault_error = [], {}, str(exc)
        try:
            data = self.images.generate(request=text, profile=profile, reference_image_path=image_path, references=references, character_traits=traits, use_llm=use_llm)
        except ValueError as exc:
            raise MissingActionInput(str(exc)) from exc
        if vault_error and isinstance(data, dict):
            data["vault_error"] = vault_error
        return data

    @staticmethod
    def _image_markdown(action, data: Any):
        vault_error = str(data.get("vault_error") or "").strip()
        if data.get("status") == STATUS_AVAILABLE:
            head = f"✅ **{action.label}**\n\nФайл: `{data.get('file_name')}` · модель: {data.get('model')}"
            if data.get("reference_used"): head += " · исходный кадр учтён"
            from_set = int(data.get("references_used") or 0) - (1 if data.get("reference_used") else 0)
            if from_set > 0: head += f" · референсов набора: {from_set}"
            if int(data.get("attempts") or 1) > 1: head += " · пересобрал со второй попытки"
            extra = []
            sheet = str(data.get("character_sheet") or "").strip()
            if sheet: extra.append(f"Лист героя: {sheet}")
            skipped = [str(item) for item in (data.get("references_skipped") or [])]
            if skipped: extra.append("Пропустил референсы: " + "; ".join(skipped[:3]))
            if vault_error: extra.append(f"Набор референсов не прочитан: {vault_error}")
            notes = str(data.get("notes") or "").strip()
            if notes: extra.append(notes)
            qa_notes = str(data.get("qa_notes") or "").strip()
            if qa_notes: extra.append(qa_notes)
            return f"{head}\n\n" + "\n\n".join(extra) if extra else head
        tail = f"\n\nНабор референсов не прочитан: {vault_error}" if vault_error else ""
        return f"\u26a0\ufe0f **{action.label}**\n\nИзображение не создано. Причина: {data.get('reason')}{tail}"

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
        elif action_id=="shoot.reference": data=self._add_reference(text,image_path)
        elif action_id=="shoot.character": data=self._character_sheet(text)
        elif action_id=="shoot.refset": data=self._reference_set()
        elif action_id in IMAGE_ACTIONS:
            # Restyle edits an existing frame, so a photo is mandatory: without
            # it we would quietly generate something unrelated.
            if action_id=="shoot.restyle" and not image_path: raise MissingActionInput(action.prompt)
            data=self._image(profile,text,image_path,use_llm)
        elif action_id=="promo.strategy": data=self.promo.build_monthly_strategy(profile,use_llm=use_llm)
        elif action_id=="promo.collabs": data=self.promo.generate_collaboration_ideas(profile,use_llm)
        elif action_id=="promo.tags": data=self.promo.build_hashtag_clusters(profile,use_llm)
        elif action_id=="promo.competitors": data=self.promo.analyze_competitors(text,profile,use_llm)
        elif action_id=="promo.newsletter": data=self.promo.build_client_newsletter(text,profile,use_llm)
        elif action_id=="promo.offer": data=self.promo.build_campaign_offer(text,profile,use_llm)
        elif action_id=="promo.reviews": data=self.promo.repurpose_review(text,profile,use_llm)
        elif action_id=="work.today": data=brain.proactive_engine.generate_daily_plan(profile=profile,use_llm=use_llm)
        else: raise KeyError(action_id)
        markdown = self._image_markdown(action,data) if action_id in IMAGE_ACTIONS else f"✅ **{action.label}**\n\n{self._format(data)}"
        return {"action_id":action_id,"title":action.label,"data":data,"markdown":markdown,"image_path":data.get("image_path") if isinstance(data,dict) else None}
