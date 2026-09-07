"""
Telegram Channel Adapter for Personal AI Brain.
Connects Telegram Bot API events (text, voice, photo) directly to BrainService
without creating a separate "Telegram AI" — Telegram is strictly transport.
"""
import os
import json
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.brain.channels.base import BaseChannelAdapter
from src.brain.services.brain_service import BrainService

class TelegramAdapter(BaseChannelAdapter):
    def __init__(self, bot_token: Optional[str] = None, brain_service: Optional[BrainService] = None):
        super().__init__(channel_name="telegram")
        from src.brain.config import TELEGRAM_BOT_TOKEN
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.brain = brain_service or BrainService()
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def is_configured(self) -> bool:
        return bool(self.bot_token and len(self.bot_token) > 10)

    def handle_text(
        self,
        user_id: str,
        text: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Routes Telegram text message through BrainService orchestrator."""
        return self.brain.process_chat(
            query=text,
            conversation_history=history
        )

    def handle_voice(
        self,
        user_id: str,
        audio_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Routes Telegram voice note through BrainService with audio transcription."""
        query = caption or "Разбери голосовую заметку со съёмки и подготовь контент-пак."
        return self.brain.process_chat(
            query=query,
            audio_path=str(audio_path)
        )

    def handle_photo(
        self,
        user_id: str,
        photo_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Routes Telegram photo through BrainService with Gemini Vision critique."""
        query = caption or "Проанализируй этот кадр: свет, позу, композицию и что можно улучшить."
        return self.brain.process_chat(
            query=query,
            images=[str(photo_path)]
        )

    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = "Markdown", reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        """Sends a response back to Telegram user with automatic chunking and fallback."""
        if not self.is_configured():
            return False
        url = f"{self.api_base}/sendMessage"

        chunks = [text[i:i+3800] for i in range(0, len(text), 3800)] if len(text) > 3800 else [text]
        for idx, chunk in enumerate(chunks):
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup and idx == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    pass
            except Exception:
                if parse_mode:
                    payload.pop("parse_mode", None)
                    req2 = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                    try:
                        with urllib.request.urlopen(req2, timeout=15) as resp2:
                            pass
                    except Exception:
                        return False
        return True

    def process_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parses a standard Telegram update object and dispatches to appropriate handler.
        """
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        user_id = str(message.get("from", {}).get("id", "anonymous"))
        text = message.get("text")
        voice = message.get("voice") or message.get("audio")
        photo = message.get("photo")
        caption = message.get("caption")

        if text:
            return self.handle_text(user_id=user_id, text=text)
        elif voice:
            downloaded = False
            voice_path = voice.get("local_path") or voice.get("file_path") or message.get("voice_path")
            if not voice_path and self.is_configured() and voice.get("file_id"):
                try:
                    from src.brain.channels.telegram_runner import TelegramHTTP
                    api = TelegramHTTP(self.bot_token)
                    suffix = ".ogg" if message.get("voice") else Path(voice.get("file_name", "voice.mp3")).suffix or ".mp3"
                    voice_path = api.download(voice, suffix)
                    downloaded = True
                except Exception as e:
                    return {"status": "ERROR", "error": f"Failed to download voice: {e}"}
            if voice_path and Path(voice_path).exists():
                try:
                    return self.handle_voice(user_id=user_id, audio_path=Path(voice_path), caption=caption)
                finally:
                    if downloaded:
                        Path(voice_path).unlink(missing_ok=True)
            return {"status": "ERROR", "error": "Voice audio file unavailable for transcription"}
        elif photo:
            downloaded = False
            photo_item = photo[-1] if isinstance(photo, list) else photo
            photo_path = photo_item.get("local_path") or photo_item.get("file_path") or message.get("photo_path")
            if not photo_path and self.is_configured() and photo_item.get("file_id"):
                try:
                    from src.brain.channels.telegram_runner import TelegramHTTP
                    api = TelegramHTTP(self.bot_token)
                    photo_path = api.download(photo_item, ".jpg")
                    downloaded = True
                except Exception as e:
                    return {"status": "ERROR", "error": f"Failed to download photo: {e}"}
            if photo_path and Path(photo_path).exists():
                try:
                    return self.handle_photo(user_id=user_id, photo_path=Path(photo_path), caption=caption)
                finally:
                    if downloaded:
                        Path(photo_path).unlink(missing_ok=True)
            return {"status": "ERROR", "error": "Photo file unavailable for vision analysis"}
        return None
