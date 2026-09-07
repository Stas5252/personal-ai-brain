"""
Configuration module for Personal AI Brain.
Centralizes environment settings, database paths, and context ranking hyperparameters.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = os.environ.get("BRAIN_DB_PATH", str(DATA_DIR / "brain.db"))

# Model Provider configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Upstream LLM Provider endpoint for Brain Service calls (Google Gemini OpenAI-compatible endpoint)
UPSTREAM_LLM_BASE_URL = os.environ.get(
    "UPSTREAM_LLM_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/"
)
# Open WebUI federation endpoint
OPENAI_API_BASE_URL = os.environ.get("OPENAI_API_BASE_URL", "http://host.docker.internal:8000/v1")
OPENWEBUI_BASE_URL = os.environ.get("OPENWEBUI_BASE_URL", "http://localhost:8080")

DEFAULT_MODEL = os.environ.get("BRAIN_DEFAULT_MODEL", "models/gemini-3.5-flash-lite")
FALLBACK_MODELS = [
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.5-flash",
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-flash-latest"
]

# Channel configurations
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "")

# Context Engine Weights
WEIGHT_RELEVANCE = float(os.environ.get("WEIGHT_RELEVANCE", "0.45"))
WEIGHT_IMPORTANCE = float(os.environ.get("WEIGHT_IMPORTANCE", "0.35"))
WEIGHT_RECENCY = float(os.environ.get("WEIGHT_RECENCY", "0.20"))

# Context Budget Limits (in characters / estimated tokens)
MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", "16000"))
BUDGET_QUOTAS = {
    "system_policy": 0.15,
    "user_profile": 0.15,
    "project_context": 0.20,
    "client_context": 0.15,
    "memories": 0.15,
    "knowledge": 0.20
}

# Internal API Secret for Brain endpoints (reads from environment; generates dynamic if not set)
BRAIN_API_KEY = os.environ.get("BRAIN_API_KEY", "brain-secure-stage4-key-2026")

# Knowledge Ingestion Factory paths
STORAGE_DIR = DATA_DIR / "storage"
ORIGINALS_DIR = STORAGE_DIR / "originals"
DERIVED_DIR = STORAGE_DIR / "derived"
VECTOR_DB_DIR = DATA_DIR / "vector_db"

for _dir in [STORAGE_DIR, ORIGINALS_DIR, DERIVED_DIR, VECTOR_DB_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# Security and limits
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_FILE_SIZE_BYTES", str(10 * 1024 * 1024 * 1024))) # 10 GB
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".html"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_EXTENSIONS = (
    ALLOWED_DOCUMENT_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS |
    ALLOWED_AUDIO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS
)

# Video extraction settings
VIDEO_FRAME_INTERVAL_SECONDS = float(os.environ.get("VIDEO_FRAME_INTERVAL_SECONDS", "10.0"))
VIDEO_MAX_FRAMES_PER_MINUTE = int(os.environ.get("VIDEO_MAX_FRAMES_PER_MINUTE", "6"))
VIDEO_SCENE_DETECTION_THRESHOLD = float(os.environ.get("VIDEO_SCENE_DETECTION_THRESHOLD", "0.35"))

# Chunking & Embedding settings
CHUNK_TARGET_CHARS = int(os.environ.get("CHUNK_TARGET_CHARS", "1500"))
CHUNK_OVERLAP_CHARS = int(os.environ.get("CHUNK_OVERLAP_CHARS", "200"))
EMBEDDING_PROVIDER_TYPE = os.environ.get("EMBEDDING_PROVIDER_TYPE", "chroma_onnx")
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
HYBRID_SEARCH_ALPHA = float(os.environ.get("HYBRID_SEARCH_ALPHA", "0.65")) # 0.65 dense vector + 0.35 keyword
