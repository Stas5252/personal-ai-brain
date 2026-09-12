"""Production Telegram delivery invariants."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import src.brain.channels.telegram_production_runner as production
from src.brain.channels.runtime_state import RuntimeState


class StateDouble:
    def __init__(self): self.values = {}
    def get(self, key, default=None): return self.values.get(key, default)
    def put(self, key, value): self.values[key] = value


class ApiDouble:
    def __init__(self): self.call = Mock(return_value={"message_id": 77})
    @staticmethod
    def typing_loop(chat, stop_event): return None


class MediaDouble:
    def __init__(self): self.send_photo = Mock(return_value=True)


def bare_bot():
    bot = object.__new__(production.ProductionGuidedBot)
    bot.owner = "42"
    bot.state = StateDouble()
    bot.brain = SimpleNamespace()
    bot.delivery_recorder = production.DeliveryRecorder()
    bot.delivery_api = ApiDouble()
    bot.delivery_media = MediaDouble()
    bot.api = production._RecordingTelegramAPI(bot.delivery_api, bot.delivery_recorder)
    bot.media = production._RecordingTelegramMedia(bot.delivery_media, bot.delivery_recorder)
    return bot


def message(text="hello", update_id=1):
    return {"update_id": update_id, "message": {"text": text, "chat": {"id": 42, "type": "private"}, "from": {"id": 42}}}


def text_plan(*parts):
    return {"version": 1, "chat_id": "42", "parts": [{"kind": "text", "text": part, "parse_mode": None, "reply_markup": None} for part in parts]}


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
    value = message("📚 Библиотека")["message"]
    with patch.object(production._LEGACY_BOT, "reply", autospec=True, return_value="ok") as reply:
        assert bot.reply(value) == "ok"
    assert reply.call_args.args[1]["text"] == "/library"
    assert value["text"] == "📚 Библиотека"


def test_navigation_is_captured_without_a_network_send():
    bot = bare_bot()
    plan = bot.prepare_delivery(message("✍️ Контент")["message"])
    assert bot.delivery_api.call.call_count == 0
    assert plan["chat_id"] == "42"
    assert plan["parts"][0]["text"] == production.legacy.CATEGORY_INTROS["✍️ Контент"]
    assert plan["parts"][0]["reply_markup"] is not None


def test_guided_say_uses_the_same_capture_path():
    bot = bare_bot()
    bot.reply = lambda incoming: bot._say(42, "guided answer")
    plan = bot.prepare_delivery(message()["message"])
    assert bot.delivery_api.call.call_count == 0
    assert [part["text"] for part in plan["parts"]] == ["guided answer"]


def test_slow_job_runs_in_durable_worker_call_stack():
    bot = bare_bot()
    bot._guard = Mock(return_value="completed")
    job = Mock()
    assert bot._defer(42, job, "payload") == "completed"
    bot._guard.assert_called_once_with(42, job, "payload")


def test_long_answer_is_split_once_and_keyboard_is_only_on_last_part():
    recorder = production.DeliveryRecorder()
    recorder.record_text(42, "A" * 8000, reply_markup={"keyboard": []})
    plan = recorder.snapshot()
    assert len(plan["parts"]) >= 3
    assert all(len(part["text"]) <= 3500 for part in plan["parts"])
    assert all(part["reply_markup"] is None for part in plan["parts"][:-1])
    assert plan["parts"][-1]["reply_markup"] == {"keyboard": []}


def test_deliver_part_raises_a_typed_error():
    bot = bare_bot()
    bot.delivery_api.call.side_effect = OSError("telegram unavailable")
    with pytest.raises(production.DeliveryError, match="not confirmed"):
        bot.deliver_part(42, {"kind": "text", "text": "important response", "parse_mode": None, "reply_markup": None})


class WorkerBot:
    owner = "42"
    def __init__(self, plan, fail_once=None):
        self.plan = plan
        self.fail_once = fail_once
        self.failed = False
        self.prepare_calls = 0
        self.deliveries = []
        self.delivery_api = SimpleNamespace(typing_loop=lambda chat, stop: None)
    def prepare_delivery(self, incoming):
        self.prepare_calls += 1
        return self.plan
    def error_delivery(self, incoming, text): return text_plan(text)
    def deliver_part(self, chat, part):
        self.deliveries.append(part["text"])
        if part["text"] == self.fail_once and not self.failed:
            self.failed = True
            raise production.DeliveryError("network timeout")
        return len(self.deliveries)


def test_partial_retry_keeps_original_and_skips_confirmed_prefix(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(message(update_id=20))
    original = text_plan("part-0", "part-1", "part-2")
    bot = WorkerBot(original, fail_once="part-1")
    assert production.process_one_update(state, bot) is False
    assert state.get_delivery(20)["next_part"] == 1
    state.redrive_delivery(20)
    assert production.process_one_update(state, bot) is True
    assert bot.deliveries == ["part-0", "part-1", "part-1", "part-2"]
    assert bot.prepare_calls == 1


def test_delivery_error_never_replaces_the_staged_answer(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(message(update_id=21))
    bot = WorkerBot(text_plan("the original model answer"), fail_once="the original model answer")
    assert production.process_one_update(state, bot) is False
    stored = state.get_delivery(21)["parts"][0]["text"]
    assert stored == "the original model answer"
    assert "delivery" not in stored.lower()


def test_existing_outbox_is_delivered_without_running_product_logic(tmp_path):
    state = RuntimeState(tmp_path / "runtime.db")
    state.enqueue(message(update_id=22))
    state.stage_delivery(22, text_plan("already prepared"))
    bot = WorkerBot(text_plan("must not be generated"))
    assert production.process_one_update(state, bot) is True
    assert bot.prepare_calls == 0
    assert bot.deliveries == ["already prepared"]
