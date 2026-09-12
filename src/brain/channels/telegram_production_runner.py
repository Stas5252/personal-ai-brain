"""Fail-closed production Telegram runner.

The legacy polling loop already has a durable SQLite inbox and processes it in
a dedicated worker thread.  GuidedBot used a second, in-memory worker and
acknowledged the durable inbox before generation or delivery completed.  This
adapter keeps slow work synchronous inside the durable worker, propagates final
delivery failures, and restores category/library keyboard navigation.
"""
from __future__ import annotations

import os
from typing import Any, Callable

import src.brain.channels.telegram_runner as legacy
from src.brain.channels.bot_features import LIBRARY_CATEGORY_MAP
from src.brain.channels.telegram_guided_runner import GuidedBot
from src.brain.channels.telegram_media import sanitize_markdown, split_message
from src.brain.channels.telegram_ratelimit import limiter

# telegram_guided_runner replaces legacy.Bot at runtime. Keep the actual legacy
# class so slash commands and navigation cannot recurse after that replacement.
_LEGACY_BOT = legacy.Bot
_BUTTON_COMMANDS = {
    "📚 Библиотека": "/library",
    "🎓 Уроки": "/uroki",
}


def configured_owner_id() -> str:
    """Return the configured owner or refuse to start.

    Production must never register the first person who happens to message the
    bot. Compose validates the same invariant before this module is executed,
    while this guard also protects direct ``python -m`` launches.
    """
    owner = os.environ.get("TELEGRAM_OWNER_ID", "").strip()
    if not owner.isdigit() or int(owner) <= 0:
        raise RuntimeError(
            "TELEGRAM_OWNER_ID must be the positive numeric Telegram user ID of the owner."
        )
    return owner


class ProductionGuidedBot(GuidedBot):
    """Guided UX with durable processing and fail-closed delivery."""

    def _legacy_command(self, message: dict[str, Any]):
        return _LEGACY_BOT.reply(self, message)

    def _defer(self, chat: Any, job: Callable[..., Any], *args: Any):
        """Run inside the durable inbox worker and ACK only after delivery.

        ``legacy.run_polling`` polls Telegram in the main thread and processes
        the SQLite inbox in a separate worker, so this does not block polling.
        It deliberately avoids GuidedBot's second, volatile SerialWorker.
        """
        return self._guard(chat, job, *args)

    def _say(self, chat: Any, text: Any, keyboard: bool = True):
        """Deliver every chunk or raise so the durable inbox can retry it."""
        body = str(text or "").strip()
        if not body:
            return None
        if chat is None:
            return body

        for index, chunk in enumerate(split_message(body)):
            payload = sanitize_markdown(chunk)
            is_last = index == len(split_message(body)) - 1

            if is_last and keyboard:
                try:
                    limiter().acquire(chat)
                    self.api.send(chat, payload, keyboard=self._current_keyboard())
                    continue
                except Exception:
                    # Fall through to the plain-text transport below.
                    pass

            delivered = False
            try:
                delivered = bool(self.media.send_text(chat, payload))
            except Exception:
                delivered = False
            if delivered:
                continue

            try:
                limiter().acquire(chat)
                self.api.send(chat, payload)
            except Exception as exc:
                raise RuntimeError("Telegram delivery failed; update will be retried.") from exc
        return None

    def reply(self, message: dict[str, Any]):
        """Route navigation buttons to the legacy menu, actions to GuidedBot."""
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


def run_polling() -> None:
    configured_owner_id()
    legacy.Bot = ProductionGuidedBot
    legacy.run_polling()


if __name__ == "__main__":
    run_polling()
