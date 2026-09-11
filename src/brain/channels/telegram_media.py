"""Telegram status and media calls shared by every Telegram entry point.

Split out of the polling runner so the adapter and the guided runner use one
implementation instead of two that drift apart. Every method returns a bool:
Telegram delivery is best effort and must never crash a reply that was already
computed.

Every outbound call goes through the shared rate limiter, and a 429 is no
longer swallowed: `parameters.retry_after` is read and waited out exactly once
before the send is retried.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

from src.brain.channels.telegram_ratelimit import limiter, parse_retry_after

API_ROOT = "https://api.telegram.org"
CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096
SAFE_CHUNK = 3500


def api_base(token: str) -> str:
    """Returns the Bot API base URL for a token."""
    return f"{API_ROOT}/bot{token}"


def split_message(text: str, limit: int = SAFE_CHUNK) -> list[str]:
    """Splits a long answer into Telegram-sized parts.

    Telegram rejects anything over 4096 characters with HTTP 400, and a price
    list or a nine-step stories arc easily crosses that line, so the reply has
    to be cut before it is sent. Cuts are made on a blank line, then a line
    break, then a space — a hard cut is the last resort.
    """
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    rest = body
    floor = max(1, limit // 3)
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind("\n\n")
        if cut < floor:
            cut = window.rfind("\n")
        if cut < floor:
            cut = window.rfind(" ")
        if cut < floor:
            cut = limit
        piece = rest[:cut].strip()
        if piece:
            chunks.append(piece)
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def sanitize_markdown(text: str) -> str:
    """Repairs Markdown that Telegram would refuse to parse.

    A single unbalanced asterisk or underscore makes the Bot API answer
    "can't parse entities" and the user sees nothing at all. Losing one
    emphasis marker is always better than losing the whole message.
    """
    body = text or ""
    if body.count("```") % 2:
        body = f"{body}\n```"
    markers = ("*", "_") if "```" in body else ("*", "_", "`")
    for marker in markers:
        if body.count(marker) % 2:
            body = body.replace(marker, "")
    return body


class TelegramMedia:
    def __init__(self, bot_token: Optional[str] = None, timeout: int = 20) -> None:
        if bot_token is None:
            from src.brain.config import TELEGRAM_BOT_TOKEN

            bot_token = TELEGRAM_BOT_TOKEN
        self.bot_token = (bot_token or "").strip()
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.bot_token and len(self.bot_token) > 10)

    def _attempt(self, request: urllib.request.Request, timeout: int) -> tuple[bool, Optional[float]]:
        """Performs one call. Returns (delivered, retry_after or None).

        Only flood control reports a retry_after; anything else returns None so
        the caller falls back instead of waiting for a failure that is not
        going to fix itself.
        """
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                return True, None
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read()
            except Exception:
                body = b""
            retry_after = parse_retry_after(body)
            if retry_after is None and getattr(exc, "code", None) == 429 and exc.headers is not None:
                retry_after = parse_retry_after(exc.headers.get("Retry-After"))
            return False, retry_after
        except Exception:
            return False, None

    def _post_json(self, method: str, payload: dict[str, Any], per_chat: bool = True) -> bool:
        if not self.is_configured():
            return False
        url = f"{api_base(self.bot_token)}/{method}"
        data = json.dumps(payload).encode("utf-8")

        def attempt() -> tuple[bool, Optional[float]]:
            request = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            return self._attempt(request, self.timeout)

        chat_id = payload.get("chat_id") if per_chat else None
        return limiter().run(chat_id, attempt)

    def chat_action(self, chat_id: Any, action: str = "typing") -> bool:
        """Shows '... печатает' / '... отправляет фото' for about five seconds."""
        if chat_id is None:
            return False
        # Paced globally but not against the per-chat budget: a typing ping
        # must never delay the answer it is announcing.
        return self._post_json("sendChatAction", {"chat_id": chat_id, "action": action}, per_chat=False)

    def typing(self, chat_id: Any, action: str = "typing") -> "TypingSession":
        """Context manager that keeps the status alive for the whole task."""
        return TypingSession(self, chat_id, action)

    def send_text(
        self,
        chat_id: Any,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Sends an answer of any length, retrying once without Markdown."""
        if not self.is_configured() or chat_id is None:
            return False
        chunks = split_message(text)
        if not chunks:
            return False
        delivered = True
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": sanitize_markdown(chunk)}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup is not None and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            if self._post_json("sendMessage", payload):
                continue
            payload.pop("parse_mode", None)
            payload["text"] = chunk
            if not self._post_json("sendMessage", payload):
                delivered = False
        return delivered

    def send_photo(
        self,
        chat_id: Any,
        photo_path: str | Path,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> bool:
        path = Path(photo_path)
        if not self.is_configured() or chat_id is None or not path.is_file():
            return False
        fields: dict[str, str] = {"chat_id": str(chat_id)}
        if caption:
            fields["caption"] = caption[:CAPTION_LIMIT]
            if parse_mode:
                fields["parse_mode"] = parse_mode
        boundary = f"----brain{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            body += f"{value}\r\n".encode()
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="photo"; filename="{path.name}"\r\n'
        ).encode()
        body += f"Content-Type: {mime}\r\n\r\n".encode()
        body += path.read_bytes()
        body += f"\r\n--{boundary}--\r\n".encode()
        url = f"{api_base(self.bot_token)}/sendPhoto"
        payload = bytes(body)
        timeout = max(self.timeout, 60)

        def attempt() -> tuple[bool, Optional[float]]:
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            return self._attempt(request, timeout)

        if limiter().run(chat_id, attempt):
            return True
        # An unbalanced Markdown caption is the usual cause, so retry once
        # as plain text before reporting failure.
        if parse_mode and caption:
            return self.send_photo(chat_id, path, caption=caption, parse_mode=None)
        return False


class TypingSession:
    """Re-sends a chat action every few seconds until the work finishes."""

    def __init__(self, media: TelegramMedia, chat_id: Any, action: str = "typing", interval: float = 4.0) -> None:
        self._media = media
        self._chat_id = chat_id
        self._action = action
        self._interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "TypingSession":
        if not self._media.is_configured() or self._chat_id is None:
            return self
        self._media.chat_action(self._chat_id, self._action)
        self._thread = threading.Thread(target=self._loop, name="tg-typing", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            if not self._media.chat_action(self._chat_id, self._action):
                return

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return False
