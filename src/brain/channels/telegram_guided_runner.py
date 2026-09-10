"""Telegram runner: guided actions, real onboarding, style learning, safe delivery.

Everything the owner sees goes through _say(): a long answer is split before
Telegram rejects it at 4096 characters and unbalanced Markdown is repaired,
so an answer that was computed is never lost on the way out.

Free-form questions are answered by BrainService directly with the last turns
of the dialogue attached — without that, a clarifying question and the answer
to it were two unrelated events.

The bot also learns the owner's own voice: /учись stores her texts, «пиши так
же» turns the last answer into a good example and «так не пиши» stores it as
an anti-example. StyleEngine measures those samples and every prompt is built
from the measurements, so the voice is learned instead of imagined.

Slow work — a guided action, a generated photo, onboarding extraction, a
free-form answer — is handed to one FIFO worker thread. Generating a photo
takes up to two minutes, and while that ran inside the polling loop no new
messages were read at all: the bot looked dead. With chat=None everything
stays synchronous, so the adapter keeps getting the answer as a return value.
"""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.runtime_state import owner_allowed
from src.brain.channels.task_queue import SerialWorker
from src.brain.channels.telegram_media import CAPTION_LIMIT, TelegramMedia, sanitize_markdown, split_message
from src.brain.channels.telegram_ratelimit import limiter
from src.brain.engines.style_engine import MIN_EXEMPLARS_FOR_VOICE, StyleEngine
from src.brain.models.style import ExemplarType
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
    "Чего не скажешь — я не придумаю, просто переспрошу позже.\n"
    "А пришлёшь 2-3 своих текста через /учись — начну писать твоим голосом, а не общим."
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

LEARN_REQUEST = (
    "Пришли следующим сообщением свой текст — пост, сторис, переписку с клиенткой или прайс.\n"
    "Я замерю длину фраз, эмодзи, пунктуацию и твои слова — и буду писать так же.\n"
    "Отмена — /cancel."
)

BUSY_NOTE = "Секунду, доделываю предыдущую задачу — отвечу сразу после неё."

APPROVE_MARKERS = ("вот так пиши", "так пиши", "пиши так же", "сохрани этот стиль", "запомни этот стиль", "запомни стиль")
REJECT_MARKERS = ("так не пиши", "так больше не пиши", "никогда так не пиши", "убери этот стиль")

CATEGORY_LABELS = {
    "POST": "пост",
    "STORIES": "сторис",
    "REELS_SCRIPT": "сценарий рилс",
    "CLIENT_DM": "переписка с клиенткой",
    "OFFER": "прайс/оффер",
    "DESCRIPTION": "описание",
}


class GuidedBot(legacy.Bot):
    def __init__(self, api, brain, state, owner):
        super().__init__(api, brain, state, owner); self.guided=GuidedActionService(); self.media=TelegramMedia(); self.style=StyleEngine(); self.worker=SerialWorker(name="tg-guided")

    def _key(self): return f"guided_action:{self.owner}"

    def _intro_key(self): return f"guided_intro:{self.owner}"

    def _history_key(self): return f"guided_history:{self.owner}"

    def _learn_key(self): return f"guided_learn:{self.owner}"

    @staticmethod
    def _chat_id(message):
        return message.get("chat",{}).get("id") or message.get("from",{}).get("id")

    @staticmethod
    def _status(action_id):
        return "upload_photo" if action_id in IMAGE_ACTIONS else "typing"

    # -- background work ----------------------------------------------------
    def _guard(self,chat,job,*args):
        """Runs one job and delivers its answer, converting failures to text.

        Without a chat the answer is returned instead of sent, so the adapter
        and the tests keep the synchronous contract they already rely on.
        """
        try: answer=job(*args)
        except (MissingActionInput,ValueError) as exc: answer=str(exc)
        except Exception as exc: answer=f"Не смог обработать запрос: {exc}"
        if chat is None: return answer
        if answer: self._say(chat,answer)
        return None

    def _defer(self,chat,job,*args):
        """Hands slow work to the worker so the polling loop keeps reading."""
        if chat is None: return self._guard(None,job,*args)
        if self.worker.pending(): self.media.send_text(chat,BUSY_NOTE)
        self.worker.submit(self._guard,chat,job,*args)
        return None

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
                    limiter().acquire(chat); self.api.send(chat,payload,keyboard=self._current_keyboard()); continue
                except Exception: pass
            if not self.media.send_text(chat,payload):
                try: limiter().acquire(chat); self.api.send(chat,payload)
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
        visual=str(getattr(profile,"visual_preferences","") or "").strip()
        if visual: rows.append("📷 Визуальный стиль: "+visual[:180])
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
                                  "Обновить данные — /знакомство, память — /память, мой стиль — /стиль.")
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

    def _last_answer(self):
        for turn in reversed(self._history()):
            if turn.get("role")=="assistant": return str(turn.get("content") or "").strip()
        return ""

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

    def _run_action(self,action_id,chat):
        """Runs an action that needs no input from her (photo generation included)."""
        with self.media.typing(chat,self._status(action_id)):
            result=self.guided.execute(action_id,self.brain,use_llm=True)
        return self._deliver(chat,result)

    def _legacy_command(self,message):
        answer=legacy.Bot.reply(self,message)
        return answer if isinstance(answer,str) else None

    # -- style learning -----------------------------------------------------
    @staticmethod
    def _reply_text(message):
        """Text of the message the owner replied to, if any."""
        source=message.get("reply_to_message") or {}
        return (source.get("text") or source.get("caption") or "").strip()

    def _remember_preference(self,text,positive):
        """Stylistic verdict also lands in memory, not only in the vault."""
        try:
            from src.brain.models.memory import MemoryType
            self.brain.memory_engine.add_memory(
                content=("Стиль, который нравится: " if positive else "Стилевой запрет: ")+str(text)[:300],
                memory_type=MemoryType.PREFERENCE,importance=0.9 if positive else 0.95,force=True)
        except Exception: pass

    def _learn_style(self,text,exemplar_type=ExemplarType.GOOD_EXAMPLE):
        """Stores one of her texts as a sample and reports what was measured."""
        try: saved=self.style.learn_from_text(text,exemplar_type=exemplar_type)
        except Exception as exc: return f"Не смог сохранить образец: {exc}"
        if saved is None: return "Для образца текст коротковат — пришли настоящий пост, сторис, прайс или переписку."
        label=CATEGORY_LABELS.get(saved.category.value,saved.category.value)
        if exemplar_type==ExemplarType.BAD_EXAMPLE:
            return f"Понял, так больше не пишу. Забраковано как антипример ({label}): «{saved.title}»."
        try: voice=self.style.analyze_voice()
        except Exception: voice={}
        head=f"Запомнил твой {label}: «{saved.title}»."
        if voice.get("learned"):
            return (head+f"\n\nВсего образцов: {voice['exemplar_count']}. Твой голос замерен: "
                    f"предложения ~{voice['sentence_length_avg']} слов, {voice['emoji_frequency'].lower()}, "
                    f"{voice['punctuation_habits']}. Пишу по этим меркам.")
        left=max(0,MIN_EXEMPLARS_FOR_VOICE-int(voice.get("exemplar_count") or 0))
        return head+f"\n\nНужно ещё {left} — и я перестану писать «вообще» и начну писать тобой."

    def _learn_from_message(self,message):
        """Turns the next message — text or voice — into a style sample."""
        temp=[]
        try:
            try: body,_=self._collect(message,temp)
            except ValueError as exc: return str(exc)
        finally:
            for item in temp: Path(item).unlink(missing_ok=True)
        self.state.put(self._learn_key(),None)
        return self._learn_style(body)

    def _style_feedback(self,message,text):
        """«пиши так же» / «так не пиши» превращают ответ в эталон или антипример."""
        lowered=(text or "").lower()
        if not lowered or len(lowered)>120: return None
        rejected=any(marker in lowered for marker in REJECT_MARKERS)
        approved=(not rejected) and any(marker in lowered for marker in APPROVE_MARKERS)
        if not rejected and not approved: return None
        sample=self._reply_text(message) or self._last_answer()
        if not sample: return "Не вижу, о каком тексте речь — ответь этой фразой на нужное сообщение."
        self._remember_preference(text,approved)
        return self._learn_style(sample,ExemplarType.GOOD_EXAMPLE if approved else ExemplarType.BAD_EXAMPLE)

    def _style_card(self):
        """/стиль: честный отчёт о том, чему бот научился на её текстах."""
        try: summary=self.style.vault_summary()
        except Exception as exc: return f"Хранилище стиля недоступно: {exc}"
        voice=summary.get("voice") or {}
        by_type=summary.get("by_type") or {}
        good=int(by_type.get("GOOD_EXAMPLE") or 0); bad=int(by_type.get("BAD_EXAMPLE") or 0)
        profile=self._profile()
        visual=str(getattr(profile,"visual_preferences","") or "").strip()
        if not summary.get("total"):
            return ("🎨 Я ещё не видел ни одного твоего текста, поэтому пишу нейтрально и твой голос не выдумываю.\n\n"
                    "Пришли 3 своих текста: /учись <текст> — или отправь текст и ответь на него «пиши так же».\n"
                    f"📷 Визуальный стиль для фото: {visual or 'не задан — /фотостиль <описание>'}")
        rows=["🎨 Чему я научился на твоих текстах",""]
        cats=", ".join(f"{CATEGORY_LABELS.get(k,k)}: {v}" for k,v in (summary.get("by_category") or {}).items())
        rows.append(f"Образцов: {good}"+(f" ({cats})" if cats else ""))
        if bad: rows.append(f"Антипримеров: {bad}")
        if voice.get("learned"):
            rows+=["","Замерено по твоим текстам:",
                   f"• Предложения: ~{voice.get('sentence_length_avg')} слов",
                   f"• Эмодзи: {voice.get('emoji_frequency')}",
                   f"• Пунктуация: {voice.get('punctuation_habits')}"]
            if voice.get("signature_words"): rows.append("• Твои слова: "+", ".join(voice["signature_words"][:8]))
            if voice.get("signature_phrases"): rows.append("• Твои связки: "+"; ".join(voice["signature_phrases"][:4]))
            rate=float(voice.get("cta_rate") or 0.0)
            if rate>=0.5: rows.append("• Призыв в конце — почти всегда, сохраняю")
            elif rate<=0.2: rows.append("• Призыв в конце ставишь редко — не навязываю")
        else:
            left=max(0,MIN_EXEMPLARS_FOR_VOICE-int(voice.get("exemplar_count") or 0))
            rows+=["",f"Голос ещё не выучен: нужно ещё {left} текст(а)."]
        rows+=["",f"📷 Визуальный стиль для фото: {visual or 'не задан — /фотостиль <описание>'}",
               "","Добавить образец: /учись <текст>. Забраковать ответ: ответь на него «так не пиши»."]
        return "\n".join(rows)

    def _photo_style(self,text):
        """/фотостиль: пишет визуальный почерк в профиль, откуда его берёт генератор фото."""
        description=text.split(" ",1)[1].strip() if " " in text else ""
        profile=self._profile()
        if not description:
            current=str(getattr(profile,"visual_preferences","") or "").strip()
            if current: return f"📷 Сейчас я генерирую фото в таком стиле:\n\n{current}\n\nПоменять: /фотостиль <описание>"
            return ("Визуальный стиль пока не задан. Напиши так:\n"
                    "/фотостиль мягкий плёночный свет, тёплые тона, живая кожа без пластика, минимум реквизита")
        if profile is None: return "Профиль недоступен: база не отвечает."
        try:
            profile.visual_preferences=description
            self.brain.profile_engine.save_profile(profile)
        except Exception as exc: return f"Не смог сохранить визуальный стиль: {exc}"
        try: self.style.learn_visual_style(description)
        except Exception: pass
        return f"📷 Запомнил. Теперь подставляю это в каждую генерацию фото:\n\n{description}"

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

    def _intro_or_answer(self,message,chat):
        """Onboarding first, otherwise a normal answer — decided in one place."""
        if self.state.get(self._intro_key()):
            learned=self._learn_about_owner(message,chat)
            if learned is not None: return learned
        else:
            profile=self._profile()
            if profile is not None and not self._known(profile):
                self.state.put(self._intro_key(),"1"); self._say(chat,INTRO_REQUEST,keyboard=False)
        return self._freeform(message,chat)

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
        return body+"\n\nУдалить лишнее: /забудь <фраза>. Что я знаю о твоём стиле: /стиль"

    def _forget(self,text):
        phrase=text.split(" ",1)[1].strip() if " " in text else ""
        if not phrase: return "Напиши так: /забудь тариф 15000"
        try: removed=self.brain.memory_engine.forget_matching(phrase)
        except Exception as exc: return f"Не смог почистить память: {exc}"
        try: dropped=self.style.forget_exemplars(phrase)
        except Exception: dropped=0
        if not removed and not dropped: return "Ничего похожего ни в памяти, ни в образцах стиля нет."
        parts=[]
        if removed: parts.append(f"записей памяти: {removed}")
        if dropped: parts.append(f"образцов стиля: {dropped}")
        return "Удалил — "+", ".join(parts)+"."

    # -- entry point --------------------------------------------------------
    def reply(self,message):
        if not owner_allowed(message,self.owner): return None
        text=(message.get("text") or "").strip(); chat=self._chat_id(message); self._track_activity(); pending=self.state.get(self._key())
        if text in {"/capabilities","/возможности"}: return self._say(chat,capability_markdown())
        if text in {"/start","/знакомство"}: self.state.put(self._key(),None); self.state.put(self._learn_key(),None); return self._greet(chat)
        if text in {"/profile","/профиль"}:
            profile=self._profile()
            if profile is None: return self._say(chat,"Профиль сейчас недоступен: база не отвечает.")
            if not self._known(profile): return self._say(chat,"Профиль почти пустой. Напиши /знакомство — расскажешь о себе, и я запомню.")
            return self._say(chat,self._profile_card(profile)+"\n\nОбновить: /знакомство")
        if text in {"/memory","/память"}: return self._say(chat,self._memory_digest())
        if text in {"/стиль","/style"}: return self._say(chat,self._style_card())
        if text.startswith("/учись") or text.startswith("/learn"):
            sample=text.split(" ",1)[1].strip() if " " in text else self._reply_text(message)
            if not sample:
                self.state.put(self._learn_key(),"1"); return self._say(chat,LEARN_REQUEST)
            return self._say(chat,self._learn_style(sample))
        if text.startswith("/фотостиль") or text.startswith("/photostyle"): return self._say(chat,self._photo_style(text))
        if text.startswith("/забудь") or text.startswith("/forget"): return self._say(chat,self._forget(text))
        if text=="/cancel" and (pending or self.state.get(self._learn_key())):
            self.state.put(self._key(),None); self.state.put(self._learn_key(),None); return self._say(chat,"Остановил.")
        if text.startswith("/"):
            return self._defer(chat,self._legacy_command,message)
        if text in ACTION_BY_LABEL:
            self.state.put(self._learn_key(),None)
            action=ACTION_BY_LABEL[text]; start=self.guided.start(action.action_id)
            if start["requires_input"]:
                self.state.put(self._key(),action.action_id)
                return self._say(chat,f"🧭 {action.label}\n\n{start['prompt']}")
            return self._defer(chat,self._run_action,action.action_id,chat)
        if self.state.get(self._learn_key()):
            return self._defer(chat,self._learn_from_message,message)
        if pending:
            return self._defer(chat,self._execute,message,pending,chat)
        verdict=self._style_feedback(message,text)
        if verdict is not None: return self._say(chat,verdict)
        return self._defer(chat,self._intro_or_answer,message,chat)


def run_polling():
    legacy.Bot=GuidedBot; legacy.run_polling()


if __name__=="__main__": run_polling()
