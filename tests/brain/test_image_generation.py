"""Image generation must produce a real file or an honest refusal.

Every test here runs offline: the upstream call is monkeypatched, and the
fixture PNG is built byte by byte, so the suite proves the decoding, magic-byte
validation and failure reporting rather than the network.
"""
import base64
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.brain.channels.bot_config import ACTIONS as MENU_ACTIONS
from src.brain.channels.bot_config import KEYBOARD_SHOOTS
from src.brain.engines.image_engine import (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    ImageEngine,
    ImageGenerationError,
)
from src.brain.services.guided_actions import ACTION_BY_LABEL, ACTIONS, GuidedActionService, MissingActionInput


def _chunk(tag: bytes, payload: bytes) -> bytes:
    body = tag + payload
    return len(payload).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")


def _png_bytes() -> bytes:
    """A real 1x1 PNG, not a string that merely claims to be one."""
    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + _chunk(b"IEND", b"")
    )


def _inline_response(raw: bytes) -> dict:
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(raw).decode()}}]}}]}


class _FakeBrain:
    def __init__(self):
        self.profile_engine = SimpleNamespace(
            get_profile=lambda: SimpleNamespace(
                niche="\u0441\u0435\u043c\u0435\u0439\u043d\u044b\u0439 \u043f\u043e\u0440\u0442\u0440\u0435\u0442",
                city="\u0421\u0430\u043c\u0430\u0440\u0430",
                visual_preferences="\u043c\u044f\u0433\u043a\u0438\u0439 \u043f\u043b\u0451\u043d\u043e\u0447\u043d\u044b\u0439 \u0441\u0432\u0435\u0442",
                forbidden_words=["\u043a\u0440\u0430\u0441\u043e\u0442\u043a\u0430"],
                audience="\u0441\u0435\u043c\u044c\u0438",
            )
        )


def test_missing_key_is_reported_instead_of_a_placeholder(tmp_path):
    result = ImageEngine(api_key="", output_dir=tmp_path).generate("\u043c\u0430\u043c\u0430 \u0441 \u0434\u043e\u0447\u043a\u043e\u0439 \u0443 \u043e\u043a\u043d\u0430")
    assert result["status"] == STATUS_UNAVAILABLE
    assert "GEMINI_API_KEY" in result["reason"]
    assert result["image_path"] is None
    assert not list(tmp_path.iterdir())


def test_empty_request_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ImageEngine(api_key="k", output_dir=tmp_path).generate("")


def test_prompt_is_built_from_the_stored_profile(tmp_path):
    prompt = ImageEngine(api_key="k", output_dir=tmp_path).build_prompt(
        "\u043c\u0430\u043c\u0430 \u0441 \u0434\u043e\u0447\u043a\u043e\u0439 \u0443 \u043e\u043a\u043d\u0430", profile=_FakeBrain().profile_engine.get_profile(), use_llm=False
    )
    assert "\u0441\u0435\u043c\u0435\u0439\u043d\u044b\u0439 \u043f\u043e\u0440\u0442\u0440\u0435\u0442" in prompt
    assert "\u0421\u0430\u043c\u0430\u0440\u0430" in prompt
    assert "\u043c\u044f\u0433\u043a\u0438\u0439 \u043f\u043b\u0451\u043d\u043e\u0447\u043d\u044b\u0439 \u0441\u0432\u0435\u0442" in prompt
    assert "\u0432\u043e\u0434\u044f\u043d\u044b\u0435 \u0437\u043d\u0430\u043a\u0438" in prompt
    assert "\u043a\u0440\u0430\u0441\u043e\u0442\u043a\u0430" in prompt


def test_only_real_image_bytes_reach_the_disk(tmp_path):
    engine = ImageEngine(api_key="k", output_dir=tmp_path)
    raw = _png_bytes()
    image, _notes = engine._extract(_inline_response(raw))
    assert image is not None
    saved = engine._save(image[1], image[0])
    assert saved.read_bytes() == raw
    assert saved.suffix == ".png"
    with pytest.raises(ImageGenerationError):
        engine._extract({"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(b"<html>error</html>").decode()}}]}}]})


def test_model_refusal_is_surfaced_verbatim(tmp_path, monkeypatch):
    engine = ImageEngine(api_key="k", output_dir=tmp_path)
    monkeypatch.setattr(engine, "_post", lambda url, payload: {"promptFeedback": {"blockReason": "SAFETY"}})
    result = engine.generate("\u043f\u043e\u0440\u0442\u0440\u0435\u0442", use_llm=False)
    assert result["status"] == STATUS_UNAVAILABLE
    assert "SAFETY" in result["reason"]
    assert not list(tmp_path.iterdir())


def test_generate_action_requires_a_brief():
    with pytest.raises(MissingActionInput):
        GuidedActionService().execute("shoot.generate", _FakeBrain(), use_llm=False)


def test_restyle_action_requires_a_photo():
    with pytest.raises(MissingActionInput):
        GuidedActionService().execute("shoot.restyle", _FakeBrain(), text="\u0441\u0434\u0435\u043b\u0430\u0439 \u0442\u0435\u043f\u043b\u0435\u0435", use_llm=False)


def test_guided_generation_returns_a_real_file(tmp_path, monkeypatch):
    service = GuidedActionService()
    raw = _png_bytes()
    monkeypatch.setattr(service.images, "api_key", "test-key")
    monkeypatch.setattr(service.images, "output_dir", tmp_path)
    monkeypatch.setattr(service.images, "_post", lambda url, payload: _inline_response(raw))
    result = service.execute("shoot.generate", _FakeBrain(), text="\u043c\u0430\u043c\u0430 \u0441 \u0434\u043e\u0447\u043a\u043e\u0439 \u0443 \u043e\u043a\u043d\u0430", use_llm=False)
    assert result["data"]["status"] == STATUS_AVAILABLE
    assert Path(result["image_path"]).read_bytes() == raw
    assert "\u2705" in result["markdown"]


def test_guided_generation_without_key_stays_honest(monkeypatch):
    service = GuidedActionService()
    monkeypatch.setattr(service.images, "api_key", "")
    result = service.execute("shoot.generate", _FakeBrain(), text="\u043f\u043e\u0440\u0442\u0440\u0435\u0442 \u0443 \u043e\u043a\u043d\u0430", use_llm=False)
    assert result["image_path"] is None
    assert "\u26a0\ufe0f" in result["markdown"]
    assert "GEMINI_API_KEY" in result["markdown"]


def test_photo_buttons_exist_in_the_menu_and_the_registry():
    assert set(MENU_ACTIONS) == set(ACTION_BY_LABEL)
    assert len(ACTIONS) == 37
    labels = {button["text"] for row in KEYBOARD_SHOOTS["keyboard"] for button in row}
    assert "\U0001f3a8 \u0421\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0444\u043e\u0442\u043e" in labels
    assert "\u267b\ufe0f \u041f\u0435\u0440\u0435\u0440\u0438\u0441\u043e\u0432\u0430\u0442\u044c \u043a\u0430\u0434\u0440" in labels
    # Without a tappable button the vault is unreachable for a phone user.
    assert "\U0001f9ec \u0420\u0435\u0444\u0435\u0440\u0435\u043d\u0441 \u0433\u0435\u0440\u043e\u044f" in labels
    assert "\U0001f4c7 \u041b\u0438\u0441\u0442 \u0433\u0435\u0440\u043e\u044f" in labels
    assert "\U0001f4c1 \u041d\u0430\u0431\u043e\u0440 \u0434\u043b\u044f \u0444\u043e\u0442\u043e" in labels
