"""Fail-closed production Telegram runner with a durable delivery outbox.

Handlers only record outbound intents. The inbox worker persists the immutable
plan before the first Telegram call, checkpoints every confirmed part, and
retries only the first unconfirmed part. Telegram has no idempotency key, so a
crash after Telegram accepts a part but before the local checkpoint may duplicate
that one in-flight part; confirmed prefixes are never replayed.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.bot_features import LIBRARY_CATEGORY_MAP, ReminderScheduler
from src.brain.channels.runtime_state import RuntimeState
from src.brain.channels.telegram_guided_runner import GuidedBot
from src.brain.channels.telegram_media import (
    CAPTION_LIMIT,
    MESSAGE_LIMIT,
    TelegramMedia,
    sanitize_markdown,
    split_message,
)

log = logging.getLogger(__name__)
_LEGACY_BOT = legacy.Bot
_BUTTON_COMMANDS = {"📚 Библиотека": "/library", "🎓 Уроки": "/uroki"}


class DeliveryError(RuntimeError):
    """A Telegram operation was not confirmed and must retry from its checkpoint."""


class DeliveryRecorder:
    """Collect logical outbound calls without contacting Telegram."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def begin(self) -> None:
        self.events = []

    def discard(self) -> None:
        self.events = []

    def record_text(self, chat, text, *, reply_markup=None, parse_mode=None) -> None:
        body = str(text or "").strip()
        if body:
            self.events.append({"kind": "text", "chat_id": str(chat or ""), "text": body, "reply_markup": reply_markup, "parse_mode": parse_mode})

    def record_photo(self, chat, path, *, caption=None, parse_mode="Markdown") -> None:
        self.events.append({"kind": "photo", "chat_id": str(chat or ""), "path": str(path), "caption": str(caption or "")[:CAPTION_LIMIT], "parse_mode": parse_mode})

    def snapshot(self, default_chat=None) -> dict[str, Any]:
        chat_id = str(default_chat or "")
        parts: list[dict[str, Any]] = []
        for event in self.events:
            event_chat = str(event.get("chat_id") or chat_id)
            if not chat_id:
                chat_id = event_chat
            if event_chat and chat_id and event_chat != chat_id:
                raise RuntimeError("A delivery plan cannot target multiple chats.")
            if event["kind"] == "photo":
                parts.append({"kind": "photo", "path": event["path"], "caption": event.get("caption") or "", "parse_mode": event.get("parse_mode")})
                continue
            chunks = split_message(event["text"])
            for index, chunk in enumerate(chunks):
                parts.append({"kind": "text", "text": sanitize_markdown(chunk), "parse_mode": event.get("parse_mode"), "reply_markup": event.get("reply_markup") if index == len(chunks) - 1 else None})
        return {"version": 1, "chat_id": chat_id, "parts": parts}


class _RecordingTelegramAPI:
    def __init__(self, delegate, recorder) -> None:
        self._delegate = delegate
        self._recorder = recorder

    def send(self, chat, text, keyboard=None, parse_mode=None):
        self._recorder.record_text(chat, text, reply_markup=legacy.KEYBOARD_MAIN if keyboard is None else keyboard, parse_mode=parse_mode)

    def __getattr__(self, name):
        return getattr(self._delegate, name)


class _RecordingTelegramMedia:
    def __init__(self, delegate, recorder) -> None:
        self._delegate = delegate
        self._recorder = recorder

    def send_text(self, chat_id, text, parse_mode="Markdown", reply_markup=None) -> bool:
        self._recorder.record_text(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True

    def send_photo(self, chat_id, photo_path, caption=None, parse_mode="Markdown") -> bool:
        self._recorder.record_photo(chat_id, photo_path, caption=caption, parse_mode=parse_mode)
        return True

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def configured_owner_id() -> str:
    owner = os.environ.get("TELEGRAM_OWNER_ID", "").strip()
    if not owner.isdigit() or int(owner) <= 0:
        raise RuntimeError("TELEGRAM_OWNER_ID must be the positive numeric Telegram user ID of the owner.")
    return owner


class ProductionGuidedBot(GuidedBot):
    def __init__(self, api, brain, state, owner):
        super().__init__(api, brain, state, owner)
        self.delivery_api = api
        self.delivery_media = self.media
        self.delivery_recorder = DeliveryRecorder()
        self.api = _RecordingTelegramAPI(api, self.delivery_recorder)
        self.media = _RecordingTelegramMedia(self.delivery_media, self.delivery_recorder)

    def _legacy_command(self, message: dict[str, Any]):
        return _LEGACY_BOT.reply(self, message)

    def _defer(self, chat: Any, job: Callable[..., Any], *args: Any):
        return self._guard(chat, job, *args)

    def _say(self, chat, text, keyboard=True):
        body = str(text or "").strip()
        if not body:
            return None
        if chat is None:
            return body
        self.delivery_recorder.record_text(chat, body, reply_markup=self._current_keyboard() if keyboard else None, parse_mode="Markdown")
        return None

    def prepare_delivery(self, message):
        chat = self._chat_id(message) or (int(self.owner) if self.owner else None)
        self.delivery_recorder.begin()
        try:
            answer = self.reply(message)
            if isinstance(answer, str) and answer.strip():
                self.delivery_recorder.record_text(chat, answer, reply_markup=self._current_keyboard(), parse_mode="Markdown")
            return self.delivery_recorder.snapshot(chat)
        except Exception:
            self.delivery_recorder.discard()
            raise

    def error_delivery(self, message, text):
        chat = self._chat_id(message) or (int(self.owner) if self.owner else None)
        self.delivery_recorder.begin()
        self.delivery_recorder.record_text(chat, text, reply_markup=self._current_keyboard(), parse_mode=None)
        return self.delivery_recorder.snapshot(chat)

    def deliver_part(self, chat, part):
        try:
            if part.get("kind") == "photo":
                if not self.delivery_media.send_photo(chat, part["path"], caption=part.get("caption") or None, parse_mode=part.get("parse_mode")):
                    raise DeliveryError("Telegram photo delivery was not confirmed.")
                return None
            text = str(part.get("text") or "")
            if not text or len(text) > MESSAGE_LIMIT:
                raise DeliveryError("Invalid Telegram text delivery part.")
            payload = {"chat_id": chat, "text": text}
            if part.get("parse_mode"):
                payload["parse_mode"] = part["parse_mode"]
            if part.get("reply_markup") is not None:
                payload["reply_markup"] = part["reply_markup"]
            result = self.delivery_api.call("sendMessage", payload)
            return result.get("message_id") if isinstance(result, dict) else None
        except DeliveryError:
            raise
        except Exception as exc:
            raise DeliveryError("Telegram delivery was not confirmed; retrying the same part.") from exc

    def reply(self, message):
        text = str(message.get("text") or "").strip()
        mapped = _BUTTON_COMMANDS.get(text)
        if mapped:
            routed = dict(message)
            routed["text"] = mapped
            return _LEGACY_BOT.reply(self, routed)
        if text in legacy.CATEGORY_INTROS or text == "⬅️ Назад":
            return _LEGACY_BOT.reply(self, message)
        if text in LIBRARY_CATEGORY_MAP:
            return _LEGACY_BOT.reply(self, message)
        if text == "Назад" and self.state.get(f"category:{self.owner}") == "library":
            return _LEGACY_BOT.reply(self, message)
        if text.isdigit() and self.state.get(f"lib_cat:{self.owner}"):
            return _LEGACY_BOT.reply(self, message)
        return super().reply(message)


def process_one_update(state, bot):
    pending = state.next_update()
    if not pending:
        return False
    ident, update, attempts = pending
    delivery = state.get_delivery(ident)
    if delivery is None:
        message = update.get("message", {})
        chat = message.get("chat", {}).get("id") or message.get("from", {}).get("id") or (int(bot.owner) if bot.owner else None)
        typing_stop = threading.Event()
        if chat:
            threading.Thread(target=bot.delivery_api.typing_loop, args=(chat, typing_stop), daemon=True).start()
        try:
            try:
                plan = bot.prepare_delivery(message)
            except (ValueError, RuntimeError) as exc:
                plan = bot.error_delivery(message, str(exc))
            except Exception:
                log.exception("Processing failed for update %s", ident)
                plan = bot.error_delivery(message, "Не удалось обработать запрос. Проверь настройки и повтори.")
        finally:
            typing_stop.set()
        state.stage_delivery(ident, plan)
        delivery = state.get_delivery(ident)
    while True:
        part = state.next_delivery_part(ident)
        if part is None:
            state.complete_delivery(ident)
            return True
        try:
            message_id = bot.deliver_part(delivery["chat_id"], part)
        except DeliveryError as exc:
            status = state.fail_delivery(ident, exc)
            log.error("Delivery failed for update %s (attempt %s, status %s)", ident, attempts + 1, status)
            return False
        state.confirm_delivery_part(ident, part["part_index"], message_id)


def run_polling() -> None:
    owner = configured_owner_id()
    if not legacy.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env before starting.")
    from src.brain.services.brain_service import BrainService
    state = RuntimeState(legacy.DATA_DIR / "telegram_runtime.db")
    api = legacy.TelegramHTTP(legacy.TELEGRAM_BOT_TOKEN)
    bot = ProductionGuidedBot(api, BrainService(), state, owner)
    reminder = ReminderScheduler(api, state, owner)
    reminder.start()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                processed = process_one_update(state, bot)
            except Exception:
                log.exception("Durable Telegram worker failed; retrying.")
                processed = False
            if not processed:
                stop.wait(0.5)

    thread = threading.Thread(target=worker, name="brain-worker", daemon=True)
    thread.start()
    log.info("Production Telegram bot started with durable delivery.")
    try:
        while not stop.is_set():
            try:
                updates = api.call("getUpdates", {"offset": state.get("offset", 0), "timeout": 25, "allowed_updates": ["message"]})
                for update in updates:
                    message = update.get("message", {})
                    if not legacy.owner_allowed(message, owner):
                        update = {"update_id": update["update_id"]}
                    state.enqueue(update)
            except Exception:
                log.error("Polling error; retrying in 3s...")
                stop.wait(3)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        reminder.stop()
        thread.join(timeout=10)
        log.info("Bot stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_polling()
