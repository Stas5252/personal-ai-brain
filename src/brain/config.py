"""Central configuration for Personal AI Brain.

All writable paths and production limits are environment driven. Defaults are
safe for local development and intentionally contain no usable credentials.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _env_path(name: str, default: str | Path) -> Path:
    """Resolve an optional environment path without depending on cwd later."""
    value = os.environ.get(name)
    return Path(value if value else default).expanduser().resolve()


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, defaults: Iterable[str]) -> list[str]:
    raw = os.environ.get(name, "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(defaults)


DATA_DIR = _env_path("BRAIN_DATA_DIR", BASE_DIR / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_env_path("BRAIN_DB_PATH", DATA_DIR / "brain.db"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
UPSTREAM_LLM_BASE_URL = os.environ.get(
    "UPSTREAM_LLM_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai",
).rstrip("/")
DEFAULT_MODEL = os.environ.get("BRAIN_DEFAULT_MODEL", "gemini-2.5-flash").strip()
FALLBACK_MODELS = _csv_env(
    "BRAIN_FALLBACK_MODELS",
    ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"),
)

OPENAI_API_BASE_URL = os.environ.get(
    "OPENAI_API_BASE_URL", "http://host.docker.internal:8000/v1"
)
OPENWEBUI_BASE_URL = os.environ.get("OPENWEBUI_BASE_URL", "http://localhost:8080")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()

WEIGHT_RELEVANCE = float(os.environ.get("WEIGHT_RELEVANCE", "0.45"))
WEIGHT_IMPORTANCE = float(os.environ.get("WEIGHT_IMPORTANCE", "0.35"))
WEIGHT_RECENCY = float(os.environ.get("WEIGHT_RECENCY", "0.20"))
MAX_CONTEXT_CHARS = _env_int("MAX_CONTEXT_CHARS", 16_000, minimum=1_000)
BUDGET_QUOTAS = {
    "system_policy": 0.15,
    "user_profile": 0.15,
    "project_context": 0.20,
    "client_context": 0.15,
    "memories": 0.15,
    "knowledge": 0.20,
}

BRAIN_API_KEY = os.environ.get("BRAIN_API_KEY", "").strip()

# Request ceiling for the API. This is a single-owner service, so the limit
# exists to bound damage from a leaked key or a runaway retry loop rather than
# to shape traffic between tenants.
RATE_LIMIT_ENABLED = _env_bool("BRAIN_RATE_LIMIT_ENABLED", True)
RATE_LIMIT_REQUESTS = _env_int("BRAIN_RATE_LIMIT_REQUESTS", 120)
RATE_LIMIT_WINDOW_SECONDS = _env_int("BRAIN_RATE_LIMIT_WINDOW_SECONDS", 60)

STORAGE_DIR = _env_path("BRAIN_STORAGE_DIR", DATA_DIR / "storage")
ORIGINALS_DIR = _env_path("BRAIN_ORIGINALS_DIR", STORAGE_DIR / "originals")
DERIVED_DIR = _env_path("BRAIN_DERIVED_DIR", STORAGE_DIR / "derived")
VECTOR_DB_DIR = _env_path(
    "VECTOR_DB_DIR", os.environ.get("CHROMA_PATH", str(DATA_DIR / "vector_db"))
)
for _directory in (STORAGE_DIR, ORIGINALS_DIR, DERIVED_DIR, VECTOR_DB_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = _env_int("MAX_FILE_SIZE_BYTES", 20 * 1024 * 1024)

# The course corpus shipped in the repository is trusted, version-controlled
# content, so it gets its own, higher ceiling. MAX_FILE_SIZE_BYTES stays small
# because it guards an internet-facing upload endpoint; six of the shipped
# course PDFs are larger than 20 MB and were rejected outright before this
# split existed, which is why none of them were ever in the knowledge base.
CORPUS_DIR = _env_path("BRAIN_CORPUS_DIR", BASE_DIR / "материалы для ии")
CORPUS_MAX_FILE_SIZE_BYTES = _env_int("CORPUS_MAX_FILE_SIZE_BYTES", 64 * 1024 * 1024)

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".html"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_EXTENSIONS = (
    ALLOWED_DOCUMENT_EXTENSIONS
    | ALLOWED_IMAGE_EXTENSIONS
    | ALLOWED_AUDIO_EXTENSIONS
    | ALLOWED_VIDEO_EXTENSIONS
)

VIDEO_FRAME_INTERVAL_SECONDS = float(os.environ.get("VIDEO_FRAME_INTERVAL_SECONDS", "10.0"))
VIDEO_MAX_FRAMES_PER_MINUTE = _env_int("VIDEO_MAX_FRAMES_PER_MINUTE", 6)
VIDEO_SCENE_DETECTION_THRESHOLD = float(
    os.environ.get("VIDEO_SCENE_DETECTION_THRESHOLD", "0.35")
)
CHUNK_TARGET_CHARS = _env_int("CHUNK_TARGET_CHARS", 1_500, minimum=100)
CHUNK_OVERLAP_CHARS = _env_int("CHUNK_OVERLAP_CHARS", 200, minimum=0)
EMBEDDING_PROVIDER_TYPE = os.environ.get("EMBEDDING_PROVIDER_TYPE", "chroma_onnx")
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
HYBRID_SEARCH_ALPHA = float(os.environ.get("HYBRID_SEARCH_ALPHA", "0.65"))
