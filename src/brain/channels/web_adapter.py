"""
Web / Open WebUI Channel Adapter for Personal AI Brain.
Wraps OpenAI-compatible SSE streaming and standard REST interaction.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.brain.channels.base import BaseChannelAdapter
from src.brain.services.brain_service import BrainService

class WebAdapter(BaseChannelAdapter):
    def __init__(self, brain_service: Optional[BrainService] = None):
        super().__init__(channel_name="web")
        self.brain = brain_service or BrainService()

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
        return self.brain.process_chat(
            query=caption or "Разбор аудио",
            audio_path=str(audio_path)
        )

    def handle_photo(
        self,
        user_id: str,
        photo_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.brain.process_chat(
            query=caption or "Разбор фотографии",
            images=[str(photo_path)]
        )
