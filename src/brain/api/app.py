"""
FastAPI Application for Personal AI Brain Service.
"""
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from src.brain.api.routes.brain_routes import router as brain_router
from src.brain.api.routes.openai_routes import router as openai_router
from src.brain.api.routes.knowledge_routes import router as knowledge_router

app = FastAPI(
    title="Personal AI Brain API",
    description="Central Intelligence Layer for Photographer/Creator AI Assistant",
    version="2.0.0"
)

# Enable CORS for local web interfaces and development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(brain_router)
app.include_router(openai_router)
app.include_router(knowledge_router)

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Personal AI Brain",
        "version": "2.0.0"
    }

@app.get("/health/ready")
def health_ready():
    """Readiness probe for orchestration and container health checks."""
    from src.brain.db import get_connection
    from src.brain.config import STORAGE_DIR
    try:
        conn = get_connection()
        conn.cursor().execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception as e:
        db_ok = False

    storage_ok = STORAGE_DIR.exists()

    status_str = "ready" if (db_ok and storage_ok) else "degraded"
    return {
        "status": status_str,
        "database": "connected" if db_ok else "unavailable",
        "storage": "accessible" if storage_ok else "unavailable"
    }

@app.get("/health/knowledge")
def health_knowledge():
    """Observability check for knowledge indexes (SQLite, FTS5, Vector DB)."""
    from src.brain.db import get_connection
    from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
    from src.brain.knowledge.embeddings.implementations import get_embedding_provider

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge_sources")
    sources_cnt = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM knowledge_chunks")
    chunks_cnt = c.fetchone()[0]

    fts_ok = False
    try:
        c.execute("SELECT COUNT(*) FROM knowledge_chunks_fts")
        fts_ok = True
    except Exception:
        pass
    conn.close()

    vec_ok = False
    vec_cnt = 0
    try:
        v_idx = ChromaVectorIndex(embedding_provider=get_embedding_provider())
        vec_cnt = v_idx.collection.count()
        vec_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if (fts_ok and vec_ok) else "degraded",
        "total_sources": sources_cnt,
        "total_chunks": chunks_cnt,
        "fts5_active": fts_ok,
        "vector_index_active": vec_ok,
        "vector_chunks_count": vec_cnt
    }

@app.get("/health/queue")
def health_queue():
    """Observability check for background ingestion queue and worker leases."""
    from datetime import datetime, timezone
    from src.brain.db import get_connection
    from src.brain.knowledge.queue.ingestion_queue import IngestionQueue

    queue = IngestionQueue()
    stats = queue.get_stats()

    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT COUNT(*) FROM ingestion_jobs
    WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED')
      AND lease_until IS NOT NULL
      AND lease_until <= ?
    """, (now_str,))
    stale_count = c.fetchone()[0]
    conn.close()

    return {
        "status": "healthy",
        "queue_stats": stats,
        "stale_jobs_count": stale_count
    }

# --- Web UI & Upload Endpoints ---
@app.get("/", response_class=HTMLResponse)
@app.get("/studio", response_class=HTMLResponse)
def studio_ui():
    """Serves the Photographer Studio Single Page Application."""
    from src.brain.config import BRAIN_API_KEY
    ui_path = Path(__file__).parent.parent / "web" / "index.html"
    if ui_path.exists():
        content = ui_path.read_text(encoding="utf-8")
        content = content.replace("{{BRAIN_API_KEY}}", BRAIN_API_KEY)
        resp = HTMLResponse(content=content)
        resp.set_cookie(key="brain_token", value=BRAIN_API_KEY, httponly=False, samesite="lax")
        return resp
    return HTMLResponse("<h1>Personal AI Brain - Photographer Studio</h1>")

@app.post("/api/upload")
async def upload_asset(file: UploadFile = File(...)):
    """Uploads photo or audio file for Brain multimodal processing."""
    from src.brain.config import DATA_DIR
    import uuid
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    unique_name = f"{uuid.uuid4()}{ext}"
    target_path = upload_dir / unique_name

    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)

    return {
        "status": "success",
        "filename": file.filename,
        "file_path": str(target_path),
        "url": f"/api/uploads/{unique_name}"
    }

@app.get("/api/uploads/{filename}")
def get_uploaded_asset(filename: str):
    """Serves uploaded media for browser preview."""
    from src.brain.config import DATA_DIR
    target_path = DATA_DIR / "uploads" / filename
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target_path)

@app.post("/api/upload_knowledge")
async def upload_knowledge(file: UploadFile = File(...)):
    """Uploads course materials, PDFs, videos, or audio into Knowledge Ingestion Factory."""
    from src.brain.config import DATA_DIR
    from src.brain.knowledge.factory import KnowledgeIngestionFactory
    import uuid
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lower() if file.filename else ".pdf"
    unique_name = f"know_{uuid.uuid4()}{ext}"
    target_path = upload_dir / unique_name

    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)

    factory = KnowledgeIngestionFactory()
    source, chunks = factory.ingest_file(target_path, title=file.filename)
    return {
        "status": "success",
        "filename": file.filename,
        "chunks_count": len(chunks),
        "source_id": source.source_id,
        "layer": source.layer.value if hasattr(source, "layer") and source.layer else "PROFESSIONAL"
    }


