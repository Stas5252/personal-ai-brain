"""Real image generation and image editing for photographers.

The contract of this module: it either returns a file that the upstream model
actually produced, or it returns status UNAVAILABLE together with the concrete
reason. It never writes a placeholder picture, never invents a URL and never
describes an image it did not receive. Every returned byte is checked against
image magic numbers before it is written to disk, so a text error page can not
be saved as a `.png`.

One more rule holds since the visual identity work: when a reference set or a
character sheet is supplied, the prompt carries an identity lock, the finished
frame is audited offline, and exactly one strengthened retry is made when the
audit finds something a prompt can actually fix.
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
from src.brain.engines import visual_identity as vi

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
        brief: str,
        profile: Any = None,
        aspect_ratio: Optional[str] = None,
        editing: bool = False,
        identity: str = "",
    ) -> str:
        """Builds the prompt from the brief, the stored profile and the character sheet.

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
        identity_block = (identity or "").strip()
        if identity_block:
            lines.append(identity_block)
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
        identity: str = "",
    ) -> str:
        base = self._deterministic_prompt(brief, profile, aspect_ratio, editing, identity)
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
        merged = enriched[:MAX_PROMPT_CHARS] + "\nНе добавляй текст" + tail
        # The rewrite is free to drop anything, and the first thing it drops is
        # the boring repetition about the face. Put the lock back, in front,
        # so it also survives the length cap.
        if identity and vi.IDENTITY_MARKER not in merged:
            merged = identity.strip() + "\n" + merged
        return merged[:MAX_PROMPT_CHARS]

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

    def _reference_parts(
        self, selected: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Turns a stored reference set into request parts.

        A single unreadable file must not kill the whole generation: it is
        skipped and reported by name, the rest of the set still goes out.
        """
        parts: list[dict[str, Any]] = []
        used: list[dict[str, Any]] = []
        skipped: list[str] = []
        for item in selected:
            path = Path(str(item.get("path") or ""))
            try:
                parts.append(self._reference_part(path))
            except (ValueError, OSError) as exc:
                skipped.append(f"{path.name}: {exc}")
                continue
            used.append(item)
        return parts, used, skipped

    # -- one round trip -----------------------------------------------------
    def _attempt(self, parts: list[dict[str, Any]], errors: list[str]) -> Optional[dict[str, Any]]:
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
                    "notes": notes,
                }
        return None

    # -- public API ---------------------------------------------------------
    def generate(
        self,
        request: str = "",
        profile: Any = None,
        reference_image_path: Optional[str | Path] = None,
        use_llm: bool = True,
        aspect_ratio: Optional[str] = None,
        references: Optional[list[dict[str, Any]]] = None,
        character_traits: Optional[dict[str, Any]] = None,
        qa_retry: bool = True,
    ) -> dict[str, Any]:
        brief = (request or "").strip()[:MAX_PROMPT_CHARS]
        if not brief and not reference_image_path and not references:
            raise ValueError("Опиши, что нужно сгенерировать, или пришли фото-референс.")
        if not self.is_configured():
            return self._unavailable(
                "GEMINI_API_KEY не задан, поэтому генерация изображений выключена. "
                "Добавь ключ в .env и перезапусти контейнер — заглушку вместо картинки я не пришлю."
            )

        edit_reference = None
        if reference_image_path:
            edit_reference = self._reference_part(Path(reference_image_path))

        selected = vi.select_references(
            references, limit=vi.MAX_REFERENCES - (1 if edit_reference else 0)
        )
        extra_parts, used, skipped = self._reference_parts(selected)
        sheet = vi.character_sheet(character_traits)
        identity = vi.identity_lock(sheet, [item["role"] for item in used]) if (sheet or used) else ""

        prompt = self.build_prompt(
            brief,
            profile=profile,
            use_llm=use_llm,
            aspect_ratio=aspect_ratio,
            editing=bool(edit_reference),
            identity=identity,
        )

        def _parts(text: str) -> list[dict[str, Any]]:
            payload: list[dict[str, Any]] = [{"text": text}]
            if edit_reference:
                payload.append(edit_reference)
            payload.extend(extra_parts)
            return payload

        reference_count = (1 if edit_reference else 0) + len(used)
        common = {
            "reference_used": bool(edit_reference),
            "references_used": reference_count,
            "references_skipped": skipped,
            "character_sheet": sheet,
        }

        errors: list[str] = []
        first = self._attempt(_parts(prompt), errors)
        if first is None:
            return self._unavailable(
                "Генерация не удалась. " + "; ".join(errors[:3] or ["upstream не ответил"]), prompt
            )
        first.update(common)
        first["prompt"] = prompt
        first["attempts"] = 1

        findings = vi.qa_findings(
            first, prompt=prompt, references=reference_count, aspect_ratio=aspect_ratio
        )
        if findings and qa_retry and vi.should_retry(findings):
            stronger = vi.strengthen_prompt(
                prompt, findings, sheet=sheet, aspect_ratio=aspect_ratio
            )
            retry_errors: list[str] = []
            second = self._attempt(_parts(stronger), retry_errors)
            if second is not None:
                second.update(common)
                second["prompt"] = stronger
                second["attempts"] = 2
                second["retry_reason"] = vi.explain_findings(findings)
                second_findings = vi.qa_findings(
                    second, prompt=stronger, references=reference_count, aspect_ratio=aspect_ratio
                )
                second["qa"] = second_findings
                second["qa_notes"] = vi.explain_findings(second_findings)
                return second
            errors.extend(retry_errors)

        first["qa"] = findings
        first["qa_notes"] = vi.explain_findings(findings)
        return first
