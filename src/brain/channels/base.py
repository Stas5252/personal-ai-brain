"""
Base Channel Adapter Abstraction for Personal AI Brain.
Provides unified interface across Telegram, MAX, and Web UI.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path

class BaseChannelAdapter(ABC):
    def __init__(self, channel_name: str):
        self.channel_name = channel_name

    @abstractmethod
    def handle_text(
        self,
        user_id: str,
        text: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Processes incoming text from channel user."""
        pass

    @abstractmethod
    def handle_voice(
        self,
        user_id: str,
        audio_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes incoming voice note from channel user."""
        pass

    @abstractmethod
    def handle_photo(
        self,
        user_id: str,
        photo_path: Path,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes incoming photograph for analysis / critique."""
        pass
