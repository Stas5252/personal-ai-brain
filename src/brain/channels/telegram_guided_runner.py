"""Telegram runner with durable guided-action state."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.runtime_state import owner_allowed
from src.brain.channels.telegram_media import CAPTION_LIMIT, TelegramMedia
from src.brain.services.guided_actions import ACTION_BY_LABEL, IMAGE_ACTIONS, GuidedActionService, MissingActionInput, capability_markdown


class GuidedBot(legacy.Bot):
    def __init__(self, api, brain, state, owner):
        super().__init__(api, brain, state, owner); self.guided=GuidedActionService(); self.media=TelegramMedia()

    def _key(self): return f"guided_action:{self.owner}"

    @staticmethod
    def _chat_id(message):
        return message.get("chat",{}).get("id") or message.get("from",{}).get("id")

    @staticmethod
    def _status(action_id):
        return "upload_photo" if action_id in IMAGE_ACTIONS else "typing"

    def _deliver(self, chat, result):
        """Sends a generated file as a real photo; never fakes a delivery."""
        path = result.get("image_path"); markdown = result["markdown"]
        if not path or chat is None: return markdown
        caption = markdown[:CAPTION_LIMIT]
        if self.media.send_photo(chat, path, caption=caption):
            rest = markdown[CAPTION_LIMIT:].strip()
            if rest: self.api.send(chat, rest, keyboard=self._current_keyboard())
            return None
        return f"{markdown}\n\nОтправить файл в чат не удалось, он сохранён на сервере: `{path}`"

    def _execute(self,message,action_id,chat=None):
        text=(message.get("text") or message.get("caption") or "").strip(); temp=[]; image=None
        try:
            with self.media.typing(chat,self._status(action_id)):
                voice=message.get("voice") or message.get("audio")
                if voice:
                    from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
                    local=self.api.download(voice,".ogg"); temp.append(local)
                    with tempfile.TemporaryDirectory(prefix="brain-guided-") as derived: extracted=AudioExtractor().extract(local,str(uuid.uuid4()),Path(derived))
                    if not extracted.success or not extracted.raw_text.strip(): raise ValueError("Не удалось распознать голосовое.")
                    text=f"{text}\n{extracted.raw_text}".strip()
                if message.get("photo"):
                    local=self.api.download(message["photo"][-1],".jpg"); temp.append(local); image=str(local)
                if message.get("document") or message.get("video"): raise ValueError("В мастере используй текст или скриншот; документ можно добавить через /знания.")
                result=self.guided.execute(action_id,self.brain,text=text,image_path=image,use_llm=True); self.state.put(self._key(),None)
                return self._deliver(chat,result)
        finally:
            # Both a voice note and a photo can arrive in one message, so every
            # downloaded file is tracked instead of just the last one.
            for item in temp: Path(item).unlink(missing_ok=True)

    def reply(self,message):
        if not owner_allowed(message,self.owner): return None
        text=(message.get("text") or "").strip(); chat=self._chat_id(message); self._track_activity(); pending=self.state.get(self._key())
        if text in {"/capabilities","/возможности"}: self.api.send(chat,capability_markdown(),keyboard=legacy.KEYBOARD_MAIN); return None
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
            except MissingActionInput as exc: return str(exc)
        with self.media.typing(chat):
            return super().reply(message)


def run_polling():
    legacy.Bot=GuidedBot; legacy.run_polling()


if __name__=="__main__": run_polling()
