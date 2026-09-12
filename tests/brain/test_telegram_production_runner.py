"""Production Telegram runner invariants."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import src.brain.channels.telegram_production_runner as production


class StateDouble:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def put(self, key, value):
        self.values[key] = value


def bare_bot():
    bot = object.__new__(production.ProductionGuidedBot)
    bot.owner = "42"
    bot.state = StateDouble()
    return bot


def test_owner_configuration_is_fail_closed(monkeypatch):
    monkeypatch.delenv("TELEGRAM_OWNER_ID", raising=False)
    with pytest.raises(RuntimeError, match="TELEGRAM_OWNER_ID"):
        production.configured_owner_id()

    monkeypatch.setenv("TELEGRAM_OWNER_ID", "0")
    with pytest.raises(RuntimeError, match="positive numeric"):
        production.configured_owner_id()

    monkeypatch.setenv("TELEGRAM_OWNER_ID", "123456789")
    assert production.configured_owner_id() == "123456789"


def test_main_library_button_routes_to_real_library_command():
    bot = bare_bot()
    message = {
        "text": "📚 Библиотека",
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42},
    }
    with patch.object(production._LEGACY_BOT, "reply", autospec=True, return_value="ok") as reply:
        assert bot.reply(message) == "ok"
    routed = reply.call_args.args[1]
    assert routed["text"] == "/library"
    assert message["text"] == "📚 Библиотека"


def test_category_button_routes_to_submenu():
    bot = bare_bot()
    message = {
        "text": "✍️ Контент",
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42},
    }
    with patch.object(production._LEGACY_BOT, "reply", autospec=True, return_value=None) as reply:
        bot.reply(message)
    assert reply.call_args.args[1]["text"] == "✍️ Контент"


def test_slow_job_runs_in_durable_worker_call_stack():
    bot = bare_bot()
    bot._guard = Mock(return_value="completed")
    job = Mock()
    assert bot._defer(42, job, "payload") == "completed"
    bot._guard.assert_called_once_with(42, job, "payload")


def test_final_delivery_failure_is_not_swallowed():
    bot = bare_bot()
    bot.media = SimpleNamespace(send_text=lambda *args, **kwargs: False)
    bot.api = SimpleNamespace(send=Mock(side_effect=OSError("telegram unavailable")))
    bot._current_keyboard = lambda: {"keyboard": []}

    with pytest.raises(RuntimeError, match="will be retried"):
        bot._say(42, "important response")
