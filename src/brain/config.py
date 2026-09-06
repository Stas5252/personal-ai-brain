"""
Configuration module for Personal AI Brain.
Centralizes environment settings, database paths, and context ranking hyperparameters.
"""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = os.environ.get("BRAIN_DB_PATH", str(DATA_DIR / "brain.db"))

# Model Provider configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_BASE_URL = os.environ.get("OPENAI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
OPENWEBUI_BASE_URL = os.environ.get("OPENWEBUI_BASE_URL", "http://localhost:8080")

DEFAULT_MODEL = os.environ.get("BRAIN_DEFAULT_MODEL", "models/gemini-2.5-flash")
FALLBACK_MODELS = [
    "models/gemini-3.5-flash",
    "models/gemini-3.5-flash-lite",
    "models/gemini-2.5-flash"
]

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

# Internal API Secret for Brain endpoints
BRAIN_API_KEY = os.environ.get("BRAIN_API_KEY", "brain-internal-key-2026")
