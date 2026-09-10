"""Real image generation and image editing for photographers.

The contract of this module: it either returns a file that the upstream model
actually produced, or it returns status UNAVAILABLE together with the concrete
reason. It never writes a placeholder picture, never invents a URL and never
describes an image it did not receive. Every returned byte is checked against
image magic numbers before it is written to disk, so a text error page can not
be saved as a `.png`.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

from src.brain.config import (
    GEMINI_API_KEY,
    GENERATED_DIR,
    IMAGE_API_BASE_URL,
    IMAGE_FALLBACK_MODELS,
    IMAGE_MODEL,
    IMAGE_TIMEOUT_SECONDS,
)

STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"

MAX_REFERENCE_BYTES = 12 * 1024 * 1024
MAX_PROMPT_CHARS = 4000

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_SUFFIX_BY_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

_PROMPT_SYSTEM = (
    "Ты — арт-директор фотостудии. Преврати бриф фотографа в один связный промпт "
    "для генератора изображений: сцена, герой, поза, свет, оптика, цвет, фактуры, фон. "
    "Пиши по-русски, 60-140 слов, одним абзацем, без списков и заголовков. "
    "Не добавляй фактов о человеке, бренде, городе, ценах и наградах, которых нет в брифе. "
    "Сохрани все запреты из брифа дословно."
)


class ImageGenerationError(RuntimeError):
    """Upstream answered, but not with a usable image."""


def _looks_like_image(raw: bytes) -> bool:
    if raw.startswith(_PNG_MAGIC) or raw.startswith(_JPEG_MAGIC):
        return True
    return raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"


def _mime_of(raw: bytes) -> str:
    if raw.startswith(_PNG_MAGIC):
        return "image/png"
    if raw.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Референс должен быть PNG, JPEG или WebP.")


class ImageEngine:
    """Generates and edits images through the Generative Language API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
        models: Optional[list[str]] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.api_key = (GEMINI_API_KEY if api_key is None else api_key).strip()
        self.base_url = (base_url or IMAGE_API_BASE_URL).rstrip("/")
        self.output_dir = Path(output_dir) if output_dir else GENERATED_DIR
        self.timeout = int(timeout or IMAGE_TIMEOUT_SECONDS)
        candidates = list(models) if models else [IMAGE_MODEL, *IMAGE_FALLBACK_MODELS]
        self.models = list(dict.fromkeys(m.strip() for m in candidates if m and m.strip()))

    # -- configuration ------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _unavailable(self, reason: str, prompt: Optional[str] = None) -> dict[str, Any]:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": reason,
            "image_path": None,
            "prompt": prompt,
            "model": None,
        }

    # -- prompt building ----------------------------------------------------
    @staticmethod
    def _deterministic_prompt(
        brief: str, profile: Any = None, aspect_ratio: Optional[str] = None, editing: bool = False
    ) -> str:
        """Builds the prompt from the brief and the stored profile only.

        No invented biography, no invented city, no invented awards: every line
        below is either a constant instruction or a value the owner supplied.
        """
        niche = str(getattr(profile, "niche", "") or "").strip()
        city = str(getattr(profile, "city", "") or "").strip()
        visual = str(getattr(profile, "visual_preferences", "") or "").strip()
        forbidden = [str(w).strip() for w in (getattr(profile, "forbidden_words", None) or []) if str(w).strip()]

        lines: list[str] = []
        if editing:
            lines.append(
                "Отредактируй присланное изображение, сохранив геометрию сцены, "
                "пропорции и узнаваемость героя."
            )
        else:
            lines.append("Сгенерируй фотореалистичное изображение по брифу фотографа.")
        lines.append(f"Бриф: {brief}" if brief else "Бриф: доработай присланный кадр без смены сюжета.")
        if niche:
            lines.append(f"Жанр съёмки: {niche}.")
        if city:
            lines.append(f"Гео-контекст: {city}.")
        if visual:
            lines.append(f"Визуальный стиль автора: {visual}.")
        lines.append(
            "Свет и цвет: естественные, кожа с текстурой и без пластика, без пересветов "
            "и без грязных теней."
        )
        lines.append("Не добавляй текст, логотипы, водяные знаки, подписи и рамки на изображение.")
        lines.append("Не изображай узнаваемых реальных людей и чужие торговые марки.")
        lines.append("Не рисуй лишние пальцы, конечности и деформации анатомии.")
        if forbidden:
            lines.append("Избегай визуальных клише: " + ", ".join(forbidden[:10]) + ".")
        if aspect_ratio:
            lines.append(f"Соотношение сторон: {aspect_ratio}.")
        return "\n".join(lines)

    def build_prompt(
        self,
        brief: str,
        profile: Any = None,
        use_llm: bool = True,
        aspect_ratio: Optional[str] = None,
        editing: bool = False,
    ) -> str:
        base = self._deterministic_prompt(brief, profile, aspect_ratio, editing)
        if not use_llm:
            return base
        try:
            from src.brain.services.llm_provider import LLMProvider

            status, text, _, _ = LLMProvider().chat_completion(
                [
                    {"role": "system", "content": _PROMPT_SYSTEM},
                    {"role": "user", "content": base},
                ],
                temperature=0.4,
            )
        except Exception:
            return base
        enriched = (text or "").strip()
        # A short or empty answer means the model added nothing; the
        # deterministic prompt is always the safer input.
        if status != 200 or len(enriched) < 60:
            return base
        tail = base.split("Не добавляй текст", 1)[-1]
        return (enriched[:MAX_PROMPT_CHARS] + "\nНе добавляй текст" + tail)[:MAX_PROMPT_CHARS]

    # -- transport ----------------------------------------------------------
    def _endpoint(self, model: str) -> str:
        return f"{self.base_url}/models/{model}:generateContent"

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _payload_variants(parts: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Image models want responseModalities; older ones reject it with 400."""
        contents = [{"role": "user", "parts": parts}]
        yield {
            "contents": contents,
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        }
        yield {"contents": contents}

    # -- response parsing ---------------------------------------------------
    @staticmethod
    def _iter_parts(response: dict[str, Any]) -> Iterator[dict[str, Any]]:
        for candidate in response.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if isinstance(part, dict):
                    yield part

    @staticmethod
    def _decode(payload: str) -> bytes:
        if not payload:
            raise ImageGenerationError("модель вернула пустые данные изображения")
        try:
            raw = base64.b64decode(re.sub(r"\s+", "", payload), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenerationError("модель вернула повреждённый base64") from exc
        if not raw:
            raise ImageGenerationError("модель вернула пустой файл")
        if not _looks_like_image(raw):
            raise ImageGenerationError("полученные байты не являются PNG, JPEG или WebP")
        return raw

    def _extract(self, response: dict[str, Any]) -> tuple[Optional[tuple[str, bytes]], str]:
        image: Optional[tuple[str, bytes]] = None
        notes: list[str] = []
        for part in self._iter_parts(response):
            blob = part.get("inlineData") or part.get("inline_data")
            if isinstance(blob, dict) and image is None:
                raw = self._decode(str(blob.get("data") or ""))
                image = (_mime_of(raw), raw)
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                notes.append(text.strip())
        return image, "\n".join(notes)

    @staticmethod
    def _refusal(response: dict[str, Any]) -> str:
        feedback = response.get("promptFeedback") or {}
        block = feedback.get("blockReason")
        if block:
            return f" (модель отказала: {block})"
        for candidate in response.get("candidates") or []:
            finish = candidate.get("finishReason")
            if finish and finish != "STOP":
                return f" (finishReason: {finish})"
        return ""

    # -- persistence --------------------------------------------------------
    def _save(self, raw: bytes, mime: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = _SUFFIX_BY_MIME.get(mime, ".png")
        name = f"gen-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{suffix}"
        path = self.output_dir / name
        path.write_bytes(raw)
        return path

    @staticmethod
    def _reference_part(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError(f"Референс не найден: {path.name}")
        raw = path.read_bytes()
        if not raw:
            raise ValueError("Референс пустой.")
        if len(raw) > MAX_REFERENCE_BYTES:
            raise ValueError("Референс больше 12 МБ — сожми файл и пришли снова.")
        return {
            "inline_data": {
                "mime_type": _mime_of(raw),
                "data": base64.b64encode(raw).decode("ascii"),
            }
        }

    # -- public API ---------------------------------------------------------
    def generate(
        self,
        request: str = "",
        profile: Any = None,
        reference_image_path: Optional[str | Path] = None,
        use_llm: bool = True,
        aspect_ratio: Optional[str] = None,
    ) -> dict[str, Any]:
        brief = (request or "").strip()[:MAX_PROMPT_CHARS]
        if not brief and not reference_image_path:
            raise ValueError("Опиши, что нужно сгенерировать, или пришли фото-референс.")
        if not self.is_configured():
            return self._unavailable(
                "GEMINI_API_KEY не задан, поэтому генерация изображений выключена. "
                "Добавь ключ в .env и перезапусти контейнер — заглушку вместо картинки я не пришлю."
            )

        parts: list[dict[str, Any]] = []
        reference = None
        if reference_image_path:
            reference = self._reference_part(Path(reference_image_path))
        prompt = self.build_prompt(
            brief, profile=profile, use_llm=use_llm, aspect_ratio=aspect_ratio, editing=bool(reference)
        )
        parts.append({"text": prompt})
        if reference:
            parts.append(reference)

        errors: list[str] = []
        for model in self.models:
            for payload in self._payload_variants(parts):
                try:
                    response = self._post(self._endpoint(model), payload)
                except urllib.error.HTTPError as exc:
                    detail = ""
                    try:
                        detail = exc.read().decode("utf-8", "replace")[:160]
                    except Exception:
                        detail = ""
                    errors.append(f"{model}: HTTP {exc.code} {detail}".strip())
                    if exc.code in (400, 404):
                        continue
                    break
                except Exception as exc:
                    errors.append(f"{model}: {type(exc).__name__}: {exc}")
                    break

                try:
                    image, notes = self._extract(response)
                except ImageGenerationError as exc:
                    errors.append(f"{model}: {exc}")
                    break
                if image is None:
                    errors.append(f"{model}: изображение не вернулось{self._refusal(response)}")
                    break

                mime, raw = image
                path = self._save(raw, mime)
                return {
                    "status": STATUS_AVAILABLE,
                    "image_path": str(path),
                    "file_name": path.name,
                    "mime_type": mime,
                    "bytes": len(raw),
                    "model": model,
                    "prompt": prompt,
                    "notes": notes,
                    "reference_used": bool(reference),
                }

        return self._unavailable(
            "Генерация не удалась. " + "; ".join(errors[:3] or ["upstream не ответил"]), prompt
        )
