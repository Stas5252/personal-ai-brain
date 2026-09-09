"""Telegram runner with durable guided-action state."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.runtime_state import owner_allowed
from src.brain.services.guided_actions import ACTION_BY_LABEL, GuidedActionService, MissingActionInput, capability_markdown


class GuidedBot(legacy.Bot):
    def __init__(self, api, brain, state, owner):
        super().__init__(api, brain, state, owner); self.guided=GuidedActionService()

    def _key(self): return f"guided_action:{self.owner}"

    def _execute(self,message,action_id):
        text=(message.get("text") or message.get("caption") or "").strip(); local=None; image=None
        try:
            voice=message.get("voice") or message.get("audio")
            if voice:
                from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
                local=self.api.download(voice,".ogg");
                with tempfile.TemporaryDirectory(prefix="brain-guided-") as derived: extracted=AudioExtractor().extract(local,str(uuid.uuid4()),Path(derived))
                if not extracted.success or not extracted.raw_text.strip(): raise ValueError("Не удалось распознать голосовое.")
                text=f"{text}\n{extracted.raw_text}".strip()
            if message.get("photo"):
                local=self.api.download(message["photo"][-1],".jpg"); image=str(local)
            if message.get("document") or message.get("video"): raise ValueError("В мастере используй текст или скриншот; документ можно добавить через /знания.")
            result=self.guided.execute(action_id,self.brain,text=text,image_path=image,use_llm=True); self.state.put(self._key(),None); return result["markdown"]
        finally:
            if local: local.unlink(missing_ok=True)

    def reply(self,message):
        if not owner_allowed(message,self.owner): return None
        text=(message.get("text") or "").strip(); chat=message.get("chat",{}).get("id") or message.get("from",{}).get("id"); self._track_activity(); pending=self.state.get(self._key())
        if text in {"/capabilities","/возможности"}: self.api.send(chat,capability_markdown(),keyboard=legacy.KEYBOARD_MAIN); return None
        if text=="/cancel" and pending: self.state.put(self._key(),None); self.api.send(chat,"Мастер остановлен.",keyboard=self._current_keyboard()); return None
        if text.startswith("/"): return super().reply(message)
        if text in ACTION_BY_LABEL:
            action=ACTION_BY_LABEL[text]; start=self.guided.start(action.action_id)
            if start["requires_input"]: self.state.put(self._key(),action.action_id); self.api.send(chat,f"🧭 {action.label}\n\n{start['prompt']}",keyboard=self._current_keyboard()); return None
            return self.guided.execute(action.action_id,self.brain,use_llm=True)["markdown"]
        if pending:
            try: return self._execute(message,pending)
            except MissingActionInput as exc: return str(exc)
        return super().reply(message)


def run_polling():
    legacy.Bot=GuidedBot; legacy.run_polling()


if __name__=="__main__": run_polling()
