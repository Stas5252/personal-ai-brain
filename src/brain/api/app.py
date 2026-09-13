"""HTTP API for personal brain."""
import hmac
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from src.brain.config import BRAIN_API_KEY, GEMINI_API_KEY, MAX_FILE_SIZE_BYTES, STORAGE_DIR
from src.brain.health import metrics_text, readiness_report
from src.brain.knowledge.knowledge_tool import get_knowledge_tool
from src.brain.migration import import_legacy_notes
from src.brain.models.model_router import ModelRouter
from src.brain.orchestrator import BrainOrchestrator

logger = logging.getLogger(__name__)
app = FastAPI(title="Personal AI Brain API", version="1.0.0")
orchestrator = BrainOrchestrator()

RATE_LIMIT_ENABLED = os.environ.get("BRAIN_RATE_LIMIT_ENABLED", "true").lower() in {"1", "true", "yes"}
RATE_LIMIT_REQUESTS = int(os.environ.get("BRAIN_RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("BRAIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT_LOCK = Lock()
_PUBLIC_PATHS = {"/health", "/health/live"}
_RATE_LIMIT_EXEMPT_PATHS = _PUBLIC_PATHS | {"/health/ready", "/metrics"}


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    path = request.url.path
    request_id = (request.headers.get("x-request-id") or str(uuid.uuid4()))[:128]
    if path not in _PUBLIC_PATHS:
        authorization = request.headers.get("authorization", "")
        expected = f"Bearer {BRAIN_API_KEY}"
        if not BRAIN_API_KEY or not hmac.compare_digest(authorization, expected):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"}, headers={"X-Request-ID": request_id})
    if RATE_LIMIT_ENABLED and path not in _RATE_LIMIT_EXEMPT_PATHS:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        key = f"{client_ip}:{path}"
        with _RATE_LIMIT_LOCK:
            bucket = _RATE_LIMIT_BUCKETS[key]
            while bucket and bucket[0] <= now - RATE_LIMIT_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= RATE_LIMIT_REQUESTS:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}, headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS), "X-Request-ID": request_id})
            bucket.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=100_000)
    max_tokens: int = Field(default=2048, ge=64, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    limit: int = Field(default=8, ge=1, le=50)


class FeedbackRequest(BaseModel):
    chat_id: Optional[int] = None
    query_text: str = Field(..., min_length=1, max_length=10_000)
    response_text: str = Field(..., min_length=1, max_length=100_000)
    result_id: Optional[str] = Field(default=None, max_length=256)
    source_id: Optional[str] = Field(default=None, max_length=256)
    chunk_id: Optional[str] = Field(default=None, max_length=256)
    score: int = Field(..., ge=-1, le=1)
    note: str = Field(default="", max_length=5000)


@app.get("/health")
def health():
    """Backwards-compatible public liveness alias."""
    return {"status": "alive"}


@app.get("/health/live")
def live():
    """Public process liveness only; no dependency checks."""
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    """Authenticated, fail-closed readiness composed entirely of offline checks."""
    payload, is_ready = readiness_report(model_key=GEMINI_API_KEY)
    return JSONResponse(status_code=200 if is_ready else 503, content=payload)


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Authenticated low-cardinality Prometheus metrics with no provider traffic."""
    return PlainTextResponse(content=metrics_text(), media_type="text/plain; version=0.0.4")


@app.get("/health/knowledge")
def knowledge_health():
    try:
        tool = get_knowledge_tool()
        details = tool.health_check()
        status = "ok" if details.get("status") in {"healthy", "ok"} else "degraded"
        return {"status": status, "details": details}
    except Exception as exc:
        logger.exception("Knowledge health check failed")
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(exc)})


@app.get("/v1/models")
def models():
    model_ids = ModelRouter.supported_models()
    return {"object": "list", "data": [{"id": model_id, "object": "model", "owned_by": "personal-brain"} for model_id in model_ids]}


@app.post("/chat")
def chat(req: ChatRequest):
    response = orchestrator.process_chat(user_id=req.user_id, message=req.message, max_tokens=req.max_tokens, temperature=req.temperature)
    return {"response": response}


@app.post("/v1/chat/completions")
def chat_completions(payload: dict):
    messages = payload.get("messages") or []
    user_id = str(payload.get("user") or "open-webui")
    prompt = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "user")
    if not prompt:
        raise HTTPException(status_code=400, detail="No user message")
    result = orchestrator.process_chat(user_id=user_id, message=prompt)
    return {"id": f"chatcmpl-{int(time.time())}", "object": "chat.completion", "created": int(time.time()), "model": payload.get("model") or "personal-ai-brain", "choices": [{"index": 0, "message": {"role": "assistant", "content": result}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


@app.post("/knowledge/search")
def search(req: SearchRequest):
    tool = get_knowledge_tool()
    return {"results": tool.search(req.query, limit=req.limit)}


@app.post("/knowledge/feedback")
def feedback(req: FeedbackRequest):
    tool = get_knowledge_tool()
    try:
        feedback_id = tool.add_feedback(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"feedback_id": feedback_id, "status": "saved"}


def _safe_upload_path(filename: str) -> Path:
    candidate = Path(filename).name
    if not candidate or candidate in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    destination = Path(STORAGE_DIR) / "uploads" / candidate
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


@app.post("/knowledge/upload")
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    destination = _safe_upload_path(file.filename or "upload.bin")
    received = 0
    with destination.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            received += len(chunk)
            if received > MAX_FILE_SIZE_BYTES:
                handle.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            handle.write(chunk)
    tool = get_knowledge_tool()
    background_tasks.add_task(tool.ingest, destination)
    return {"status": "queued", "filename": destination.name, "bytes": received}


@app.post("/admin/import-legacy-notes")
def migrate_notes():
    count = import_legacy_notes()
    return {"imported": count}
