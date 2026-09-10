"""Telegram runner: durable guided-action state and a real onboarding flow.

The owner is greeted, asked to introduce themselves, and everything they say is
parsed into the stored profile. Nothing about the photographer is invented: if
a field was not said, it stays empty and the bot asks again later.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.runtime_state import owner_allowed
from src.brain.channels.telegram_media import CAPTION_LIMIT, TelegramMedia
from src.brain.services.guided_actions import ACTION_BY_LABEL, IMAGE_ACTIONS, GuidedActionService, MissingActionInput, capability_markdown

INTRO_REQUEST = (
    "Привет! Я твой рабочий ИИ-напарник по фотобизнесу.\n\n"
    "Чтобы советы были про твой бизнес, а не «вообще», расскажи о себе одним сообщением — можно голосовым:\n"
    "• как тебя зовут и как называется проект;\n"
    "• что снимаешь и в каком городе;\n"
    "• пакеты и цены;\n"
    "• кто твои клиенты;\n"
    "• какой стиль и тон тебе близок, какие слова раздражают;\n"
    "• цели на ближайшие полгода.\n\n"
    "Чего не скажешь — я не придумаю, просто переспрошу позже."
)


class GuidedBot(legacy.Bot):
    def __init__(self, api, brain, state, owner):
        super().__init__(api, brain, state, owner); self.guided=GuidedActionService(); self.media=TelegramMedia()

    def _key(self): return f"guided_action:{self.owner}"

    def _intro_key(self): return f"guided_intro:{self.owner}"

    @staticmethod
    def _chat_id(message):
        return message.get("chat",{}).get("id") or message.get("from",{}).get("id")

    @staticmethod
    def _status(action_id):
        return "upload_photo" if action_id in IMAGE_ACTIONS else "typing"

    # -- profile ------------------------------------------------------------
    def _profile(self):
        try: return self.brain.profile_engine.get_profile()
        except Exception: return None

    @staticmethod
    def _known(profile):
        """A profile counts as known only with a name and a niche in it."""
        identity=str(getattr(profile,"identity","") or "").strip(); niche=str(getattr(profile,"niche","") or "").strip()
        return bool(identity and niche)

    @staticmethod
    def _profile_card(profile):
        rows=[f"👤 {getattr(profile,'identity','') or 'имя не указано'}",
              f"📸 Ниша: {getattr(profile,'niche','') or 'не указана'}",
              f"📍 Город: {getattr(profile,'city','') or 'не указан'}",
              f"🗣 Тон: {getattr(profile,'tone','') or 'не указан'}"]
        prices=getattr(profile,"prices",None) or {}
        if prices: rows.append("💰 Прайс: "+", ".join(f"{k}: {v}" for k,v in list(prices.items())[:4]))
        goals=getattr(profile,"goals",None) or []
        if goals: rows.append("🎯 Цели: "+", ".join(str(g) for g in goals[:4]))
        forbidden=getattr(profile,"forbidden_words",None) or []
        if forbidden: rows.append("🚫 Стоп-слова: "+", ".join(str(w) for w in forbidden[:6]))
        return "\n".join(rows)

    def _greet(self,chat):
        """/start: continue with a known owner, otherwise begin the introduction."""
        profile=self._profile()
        if profile is not None and self._known(profile):
            self.state.put(self._intro_key(),None)
            self.api.send(chat,f"С возвращением, {profile.identity}! Помню твой профиль:\n\n"
                                f"{self._profile_card(profile)}\n\nВыбери раздел в меню или просто напиши задачу. "
                                "Обновить данные — /знакомство.",keyboard=self._current_keyboard())
            return None
        self.state.put(self._intro_key(),"1")
        self.api.send(chat,INTRO_REQUEST,keyboard=self._current_keyboard())
        return None

    def _learn_about_owner(self,message,chat):
        """Turns a free-form introduction into the stored profile and memory."""
        temp=[]
        try:
            body,_=self._collect(message,temp)
            if not body: return "Расскажи о себе текстом или голосовым — я запомню нишу, город, цены и стоп-слова."
            with self.media.typing(chat):
                result=self.brain.profile_engine.extract_profile_from_freeform(body)
            if result.get("is_complete"): self.state.put(self._intro_key(),None)
            return result.get("friendly_summary") or "Записал."
        except ValueError as exc: return str(exc)
        finally:
            for item in temp: Path(item).unlink(missing_ok=True)

    # -- input --------------------------------------------------------------
    def _collect(self,message,temp):
        """Returns (text, image_path). Every download is tracked in temp.

        A voice note and a photo can arrive in one message, so both are kept
        instead of the last one overwriting the first.
        """
        text=(message.get("text") or message.get("caption") or "").strip(); image=None
        voice=message.get("voice") or message.get("audio")
        if voice:
            from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
            local=self.api.download(voice,".ogg"); temp.append(local)
            with tempfile.TemporaryDirectory(prefix="brain-guided-") as derived: extracted=AudioExtractor().extract(local,str(uuid.uuid4()),Path(derived))
            if not extracted.success or not extracted.raw_text.strip(): raise ValueError("Не удалось распознать голосовое.")
            text=f"{text}\n{extracted.raw_text}".strip()
        if message.get("photo"):
            local=self.api.download(message["photo"][-1],".jpg"); temp.append(local); image=str(local)
        return text,image

    def _deliver(self,chat,result):
        """Sends a generated file as a real photo; never fakes a delivery."""
        path=result.get("image_path"); markdown=result["markdown"]
        if not path or chat is None: return markdown
        caption=markdown[:CAPTION_LIMIT]
        if self.media.send_photo(chat,path,caption=caption):
            rest=markdown[CAPTION_LIMIT:].strip()
            if rest: self.api.send(chat,rest,keyboard=self._current_keyboard())
            return None
        return f"{markdown}\n\nОтправить файл в чат не удалось, он сохранён на сервере: `{path}`"

    def _execute(self,message,action_id,chat=None):
        temp=[]
        try:
            with self.media.typing(chat,self._status(action_id)):
                if message.get("document") or message.get("video"): raise ValueError("В мастере используй текст или скриншот; документ можно добавить через /знания.")
                text,image=self._collect(message,temp)
                result=self.guided.execute(action_id,self.brain,text=text,image_path=image,use_llm=True); self.state.put(self._key(),None)
                return self._deliver(chat,result)
        finally:
            for item in temp: Path(item).unlink(missing_ok=True)

    def reply(self,message):
        if not owner_allowed(message,self.owner): return None
        text=(message.get("text") or "").strip(); chat=self._chat_id(message); self._track_activity(); pending=self.state.get(self._key())
        if text in {"/capabilities","/возможности"}: self.api.send(chat,capability_markdown(),keyboard=self._current_keyboard()); return None
        if text in {"/start","/знакомство"}: self.state.put(self._key(),None); return self._greet(chat)
        if text in {"/profile","/профиль"}:
            profile=self._profile()
            if profile is None: return "Профиль сейчас недоступен: база не отвечает."
            if not self._known(profile): return "Профиль почти пустой. Напиши /знакомство — расскажешь о себе, и я запомню."
            return self._profile_card(profile)+"\n\nОбновить: /знакомство"
        if text=="/cancel" and pending: self.state.put(self._key(),None); self.api.send(chat,"Мастер остановлен.",keyboard=self._current_keyboard()); return None
        if text.startswith("/"): return super().reply(message)
        if text in ACTION_BY_LABEL:
            action=ACTION_BY_LABEL[text]; start=self.guided.start(action.action_id)
            if start["requires_input"]: self.state.put(self._key(),action.action_id); self.api.send(chat,f"🧭 {action.label}\n\n{start['prompt']}",keyboard=self._current_keyboard()); return None
            with self.media.typing(chat,self._status(action.action_id)):
                result=self.guided.execute(action.action_id,self.brain,use_llm=True)
            return self._deliver(chat,result)
        if pending:
            try: return self._execute(message,pending,chat)
            except (MissingActionInput,ValueError) as exc: return str(exc)
        if self.state.get(self._intro_key()): return self._learn_about_owner(message,chat)
        with self.media.typing(chat):
            return super().reply(message)


def run_polling():
    legacy.Bot=GuidedBot; legacy.run_polling()


if __name__=="__main__": run_polling()
