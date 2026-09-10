"""Telegram runner: guided actions, real onboarding and safe delivery.

Everything the owner sees goes through _say(): a long answer is split before
Telegram rejects it at 4096 characters and unbalanced Markdown is repaired,
so an answer that was computed is never lost on the way out.

Free-form questions are answered by BrainService directly with the last turns
of the dialogue attached — without that, a clarifying question and the answer
to it were two unrelated events.
"""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.runtime_state import owner_allowed
from src.brain.channels.telegram_media import CAPTION_LIMIT, TelegramMedia, sanitize_markdown, split_message
from src.brain.services.guided_actions import ACTION_BY_LABEL, IMAGE_ACTIONS, GuidedActionService, MissingActionInput, capability_markdown

HISTORY_TURNS = 6

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

PHOTO_HINT = (
    "Определи, что на изображении, и разбери по делу. "
    "Если это кадр — свет, композиция, поза и эмоция, цвет и скинтон, техника, плюс 3 шага к улучшению. "
    "Если это скриншот диалога — разбери переписку и предложи готовый ответ клиенту. "
    "Если это прайс или скрин экрана — разбери содержание и скажи, что улучшить."
)

STYLE_GUARD_PROMPT = (
    "Перепиши текст, полностью убрав запрещённые слова и выражения. "
    "Смысл, факты, цифры и структура остаются прежними. Ничего не добавляй от себя."
)


class GuidedBot(legacy.Bot):
    def __init__(self, api, brain, state, owner):
        super().__init__(api, brain, state, owner); self.guided=GuidedActionService(); self.media=TelegramMedia()

    def _key(self): return f"guided_action:{self.owner}"

    def _intro_key(self): return f"guided_intro:{self.owner}"

    def _history_key(self): return f"guided_history:{self.owner}"

    @staticmethod
    def _chat_id(message):
        return message.get("chat",{}).get("id") or message.get("from",{}).get("id")

    @staticmethod
    def _status(action_id):
        return "upload_photo" if action_id in IMAGE_ACTIONS else "typing"

    # -- delivery -----------------------------------------------------------
    def _say(self,chat,text,keyboard=True):
        """Delivers an answer of any length and returns None.

        Telegram refuses messages over 4096 characters and unbalanced Markdown,
        so a price list or a long script used to disappear silently.
        """
        body=(text or "").strip()
        if not body: return None
        if chat is None: return body
        chunks=split_message(body)
        for index,chunk in enumerate(chunks):
            payload=sanitize_markdown(chunk); last=index==len(chunks)-1
            if last and keyboard:
                try:
                    self.api.send(chat,payload,keyboard=self._current_keyboard()); continue
                except Exception: pass
            if not self.media.send_text(chat,payload):
                try: self.api.send(chat,payload)
                except Exception: pass
        return None

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
            return self._say(chat,f"С возвращением, {profile.identity}! Помню твой профиль:\n\n"
                                  f"{self._profile_card(profile)}\n\nВыбери раздел в меню или просто напиши задачу. "
                                  "Обновить данные — /знакомство, посмотреть память — /память.")
        self.state.put(self._intro_key(),"1")
        return self._say(chat,INTRO_REQUEST)

    def _learn_about_owner(self,message,chat):
        """Turns a free-form introduction into the stored profile.

        Returns None when the message carried no profile facts at all, so the
        owner can ask a normal question instead of being stuck in onboarding.
        """
        temp=[]
        try:
            try: body,_=self._collect(message,temp)
            except ValueError as exc: return str(exc)
            if not body: return "Расскажи о себе текстом или голосовым — я запомню нишу, город, цены и стоп-слова."
            with self.media.typing(chat):
                result=self.brain.profile_engine.extract_profile_from_freeform(body)
            if not (result.get("extracted_data") or {}):
                self.state.put(self._intro_key(),None)
                return None
            if result.get("is_complete"): self.state.put(self._intro_key(),None)
            summary=result.get("friendly_summary") or "Записал."
            question=result.get("next_clarifying_question")
            if question and not result.get("is_complete"): return f"{summary}\n\n{question}"
            return summary
        finally:
            for item in temp: Path(item).unlink(missing_ok=True)

    # -- dialogue memory ----------------------------------------------------
    def _history(self):
        raw=self.state.get(self._history_key())
        if not raw: return []
        try: data=json.loads(raw)
        except Exception: return []
        return data if isinstance(data,list) else []

    def _remember_turn(self,question,answer):
        history=self._history()
        history.append({"role":"user","content":str(question)[:2000]})
        history.append({"role":"assistant","content":str(answer)[:2000]})
        try: self.state.put(self._history_key(),json.dumps(history[-(HISTORY_TURNS*2):],ensure_ascii=False))
        except Exception: pass

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
            if rest: self._say(chat,rest)
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

    # -- free-form chat -----------------------------------------------------
    def _style_guard(self,answer,benchmark):
        """Rewrites an answer once if it used the owner's forbidden words.

        The benchmark was already being calculated and then thrown away, so a
        stop word could reach the chat even though the bot had detected it.
        """
        violations=benchmark.get("forbidden_violations") if isinstance(benchmark,dict) else None
        if not violations: return answer
        profile=self._profile()
        words=[str(w) for w in (getattr(profile,"forbidden_words",None) or [])]
        if isinstance(violations,(list,tuple,set)): words=[str(v) for v in violations] or words
        if not words: return answer
        try:
            status,rewritten,_,_=self.brain.llm.chat_completion(
                messages=[{"role":"system","content":STYLE_GUARD_PROMPT},
                          {"role":"user","content":f"Запрещены: {', '.join(words)}\n\nТекст:\n{answer}"}],
                temperature=0.3)
        except Exception: return answer
        if status==200 and rewritten and rewritten.strip(): return rewritten.strip()
        return answer

    def _freeform(self,message,chat):
        """Answers a plain question through BrainService with dialogue history."""
        temp=[]
        try:
            try: text,image=self._collect(message,temp)
            except ValueError as exc: return str(exc)
            if not text and not image: return None
            query=text or PHOTO_HINT
            with self.media.typing(chat,"upload_photo" if image else "typing"):
                result=self.brain.process_chat(query=query,conversation_history=self._history(),images=[image] if image else None)
            answer=(result.get("response") or "").strip()
            if not answer: return "Модель вернула пустой ответ. Повтори запрос или уточни задачу."
            answer=self._style_guard(answer,result.get("style_benchmark") or {})
            self._remember_turn(query,answer)
            return answer
        except Exception as exc:
            return f"Не смог обработать запрос: {exc}"
        finally:
            for item in temp: Path(item).unlink(missing_ok=True)

    # -- memory commands ----------------------------------------------------
    def _memory_digest(self):
        try:
            engine=self.brain.memory_engine; lines=engine.digest(limit=20); stats=engine.stats()
        except Exception as exc: return f"Память сейчас недоступна: {exc}"
        if not lines: return "Пока ничего не запомнил. Расскажи о себе через /знакомство."
        active=stats.get("active_by_type") or {}
        tail=", ".join(f"{k}: {v}" for k,v in active.items())
        body="🧠 Что я помню:\n\n"+"\n".join(f"• {line}" for line in lines)
        if tail: body+=f"\n\nАктивные записи — {tail}."
        return body+"\n\nУдалить лишнее: /забудь <фраза>"

    def _forget(self,text):
        phrase=text.split(" ",1)[1].strip() if " " in text else ""
        if not phrase: return "Напиши так: /забудь тариф 15000"
        try: removed=self.brain.memory_engine.forget_matching(phrase)
        except Exception as exc: return f"Не смог почистить память: {exc}"
        return f"Удалил записей: {removed}." if removed else "Ничего похожего в памяти нет."

    # -- entry point --------------------------------------------------------
    def reply(self,message):
        if not owner_allowed(message,self.owner): return None
        text=(message.get("text") or "").strip(); chat=self._chat_id(message); self._track_activity(); pending=self.state.get(self._key())
        if text in {"/capabilities","/возможности"}: return self._say(chat,capability_markdown())
        if text in {"/start","/знакомство"}: self.state.put(self._key(),None); return self._greet(chat)
        if text in {"/profile","/профиль"}:
            profile=self._profile()
            if profile is None: return self._say(chat,"Профиль сейчас недоступен: база не отвечает.")
            if not self._known(profile): return self._say(chat,"Профиль почти пустой. Напиши /знакомство — расскажешь о себе, и я запомню.")
            return self._say(chat,self._profile_card(profile)+"\n\nОбновить: /знакомство")
        if text in {"/memory","/память"}: return self._say(chat,self._memory_digest())
        if text.startswith("/забудь") or text.startswith("/forget"): return self._say(chat,self._forget(text))
        if text=="/cancel" and pending: self.state.put(self._key(),None); return self._say(chat,"Мастер остановлен.")
        if text.startswith("/"):
            answer=super().reply(message)
            return self._say(chat,answer) if isinstance(answer,str) else answer
        if text in ACTION_BY_LABEL:
            action=ACTION_BY_LABEL[text]; start=self.guided.start(action.action_id)
            if start["requires_input"]:
                self.state.put(self._key(),action.action_id)
                return self._say(chat,f"🧭 {action.label}\n\n{start['prompt']}")
            with self.media.typing(chat,self._status(action.action_id)):
                result=self.guided.execute(action.action_id,self.brain,use_llm=True)
            return self._say(chat,self._deliver(chat,result))
        if pending:
            try: return self._say(chat,self._execute(message,pending,chat))
            except (MissingActionInput,ValueError) as exc: return self._say(chat,str(exc))
        if self.state.get(self._intro_key()):
            learned=self._learn_about_owner(message,chat)
            if learned is not None: return self._say(chat,learned)
        else:
            profile=self._profile()
            if profile is not None and not self._known(profile):
                self.state.put(self._intro_key(),"1"); self._say(chat,INTRO_REQUEST,keyboard=False)
        return self._say(chat,self._freeform(message,chat))


def run_polling():
    legacy.Bot=GuidedBot; legacy.run_polling()


if __name__=="__main__": run_polling()
