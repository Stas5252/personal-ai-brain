"""HTTP surface for real image generation.

The endpoint mirrors the guarantee of the engine: HTTP 200 means a file was
actually produced and can be downloaded, HTTP 503 carries the concrete reason
why it was not. There is no placeholder image and no invented URL.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.brain.channels.runtime_state import confined_file
from src.brain.config import DATA_DIR, GENERATED_DIR
from src.brain.engines.image_engine import MAX_PROMPT_CHARS, STATUS_AVAILABLE, ImageEngine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/brain", tags=["image"])
UPLOAD_ROOT = DATA_DIR / "uploads"


class ImageRequest(BaseModel):
    prompt: str = Field(default="", max_length=MAX_PROMPT_CHARS)
    reference_image_path: Optional[str] = Field(default=None, max_length=255)
    aspect_ratio: Optional[str] = Field(default=None, max_length=16)
    use_llm: bool = True


def _profile():
    """Best-effort owner profile; generation must not fail without one."""
    try:
        from src.brain.api.routes.brain_routes import brain

        return brain.profile_engine.get_profile()
    except Exception:
        log.warning("Profile unavailable for image generation", exc_info=True)
        return None


def _resolve_reference(name: str) -> Path:
    """Only files the server itself stored may be used as a reference."""
    candidate = Path(name).name
    for root in (UPLOAD_ROOT, GENERATED_DIR):
        try:
            return confined_file(root / candidate, root)
        except ValueError:
            continue
    raise HTTPException(404, "Reference image not found.")


@router.post("/image")
async def generate_image(req: ImageRequest):
    reference = str(_resolve_reference(req.reference_image_path)) if req.reference_image_path else None
    profile = await run_in_threadpool(_profile)
    call = functools.partial(
        ImageEngine().generate,
        request=req.prompt,
        profile=profile,
        reference_image_path=reference,
        use_llm=req.use_llm,
        aspect_ratio=req.aspect_ratio,
    )
    try:
        result = await run_in_threadpool(call)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if result.get("status") != STATUS_AVAILABLE:
        raise HTTPException(503, result.get("reason") or "Image generation unavailable.")
    result["url"] = f"/brain/image/{Path(result['image_path']).name}"
    return result


@router.get("/image/{filename}")
def generated_image(filename: str):
    try:
        path = confined_file(GENERATED_DIR / filename, GENERATED_DIR)
    except ValueError:
        raise HTTPException(404, "File not found.")
    return FileResponse(path, filename=path.name)
