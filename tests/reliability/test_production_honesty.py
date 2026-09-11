"""Production honesty checks for vision and readiness boundaries."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.brain.channels.telegram_guided_runner import GuidedBot


def test_guided_freeform_stops_when_live_vision_fails(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fixture")
    bot = object.__new__(GuidedBot)
    bot.brain = Mock()
    bot.brain.shooting_engine.critique_shot.return_value = {"status": "ERROR"}
    bot._collect = lambda message, temp: ("Разбери кадр", str(image))
    bot._history = lambda: []
    bot.media = SimpleNamespace(typing=lambda *args, **kwargs: nullcontext())
    with patch("src.brain.channels.telegram_guided_runner.legacy.UPLOADS", tmp_path):
        answer = bot._freeform({}, None)
    assert "анализ изображения недоступен" in answer.lower()
    bot.brain.process_chat.assert_not_called()


def test_readiness_is_degraded_without_live_model_key():
    from src.brain.api import app as app_module
    with patch.object(app_module, "GEMINI_API_KEY", ""):
        response = app_module.ready()
    assert response.status_code == 503
    payload = json.loads(response.body)
    assert payload["status"] == "degraded"
    assert payload["model_key_configured"] is False
