"""
MAX Messenger Channel Adapter for Personal AI Brain.
Provides channel parity for MAX messenger (second target platform).
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.brain.channels.base import BaseChannelAdapter
from src.brain.services.brain_service import BrainService

class MaxAdapter(BaseChannelAdapter):
    def __init__(self, bot_token: Optional[str] = None, brain_service: Optional[BrainService] = None):
        super().__init__(channel_name="max")
        from src.brain.config import MAX_BOT_TOKEN
        self.bot_token = bot_token or MAX_BOT_TOKEN
        self.brain = brain_service or BrainService()

    def is_configured(self) -> bool:
        return bool(self.bot_token and len(self.bot_token) > 5)

    def handle_text(
        self,
        user_id: str,
        text: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        return self.brain.process_chat(query=text, conversation_history=history)

    def handle_voice(
        self,
        user_id: str,
        audio_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        query = caption or "Разбери голосовую заметку со съёмки."
        return self.brain.process_chat(query=query, audio_path=str(audio_path))

    def handle_photo(
        self,
        user_id: str,
        photo_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        query = caption or "Проанализируй кадр."
        return self.brain.process_chat(query=query, images=[str(photo_path)])
