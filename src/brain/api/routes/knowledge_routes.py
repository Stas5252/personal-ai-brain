"""Knowledge API: producers register durable jobs; only the worker ingests."""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.brain.api.security import verify_brain_api_key
from src.brain.config import ALLOWED_EXTENSIONS, DATA_DIR, MAX_FILE_SIZE_BYTES
from src.brain.db import get_connection
from src.brain.knowledge.registration import IngestionRegistrar, job_status
from src.brain.models.knowledge import KnowledgeLayer

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(verify_brain_api_key)])


class KnowledgeSearchRequest(BaseModel):
    query: str
    layer: Optional[KnowledgeLayer] = None
    project: Optional[str] = None
    client: Optional[str] = None
    limit: int = 4
    min_score: float = 0.20


class DirectoryIngestRequest(BaseModel):
    directory_path: str
    recursive: bool = True
    default_layer: Optional[KnowledgeLayer] = None


def _accepted(result):
    location = f"/knowledge/jobs/{result.job.job_id}"
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, headers={"Location": location}, content={
        "job_id": result.job.job_id, "source_id": result.source_id,
        "status": result.job.status.value, "stage": result.job.stage,
        "progress": result.job.progress, "duplicate": result.duplicate,
        "status_url": location,
    })


@router.post("/sources")
async def create_or_upload_source(
    file: Optional[UploadFile] = File(None), title: Optional[str] = Form(None),
    content: Optional[str] = Form(None), layer: Optional[str] = Form(None),
    subcategory: Optional[str] = Form(None), tags: Optional[str] = Form(None),
    project: Optional[str] = Form(None), client: Optional[str] = Form(None),
    author: Optional[str] = Form(None), force: bool = Form(False),
):
    tag_list = [value.strip() for value in tags.split(",") if value.strip()] if tags else []
    try:
        layer_value = KnowledgeLayer(layer.upper()) if layer else KnowledgeLayer.GLOBAL
    except ValueError:
        raise HTTPException(400, f"Unknown knowledge layer: {layer}")
    registrar = IngestionRegistrar()
    kwargs = dict(layer=layer_value, author=author or "User", subcategory=subcategory,
                  tags=tag_list, project=project, client=client, force=force)
    if file and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file extension '{suffix}'.")
        temp_dir = DATA_DIR / "uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp = temp_dir / f"register-{uuid.uuid4().hex}{suffix}"
        try:
            with temp.open("xb") as target:
                shutil.copyfileobj(file.file, target)
            if temp.stat().st_size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(413, "File exceeds configured size limit.")
            return _accepted(registrar.register_file(temp, original_filename=file.filename, title=title, **kwargs))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        finally:
            await file.close()
            temp.unlink(missing_ok=True)
    if content:
        try:
            return _accepted(registrar.register_text(content, title=title or "User Text Source", **kwargs))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    raise HTTPException(400, "Either 'file' or 'content' must be provided.")


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    result = job_status(job_id)
    if result is None:
        raise HTTPException(404, "Ingestion job not found")
    return result


@router.get("/sources")
def list_sources(layer: Optional[KnowledgeLayer] = Query(None), status_filter: Optional[str] = Query(None, alias="status"), query: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    sql = "SELECT * FROM knowledge_sources WHERE 1=1"
    params: list[object] = []
    if layer:
        sql += " AND category=?"; params.append(layer.value)
    if status_filter:
        sql += " AND ingestion_status=?"; params.append(status_filter.upper())
    if query:
        sql += " AND (title LIKE ? OR subcategory LIKE ?)"; params.extend([f"%{query}%", f"%{query}%"])
    count_sql = sql.replace("SELECT *", "SELECT COUNT(*)")
    sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    connection = get_connection()
    try:
        rows = connection.execute(sql, params + [limit, offset]).fetchall()
        total = connection.execute(count_sql, params).fetchone()[0]
    finally:
        connection.close()
    return {"sources": [{"source_id": row["source_id"], "title": row["title"], "author": row["author"], "date": row["date"], "type": row["type"], "layer": row["category"], "subcategory": row["subcategory"], "tags": json.loads(row["tags_json"] or "[]"), "project": row["project"], "client": row["client"], "language": row["language"], "status": row["ingestion_status"], "timestamp": row["timestamp"]} for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/sources/{source_id}")
def get_source_detail(source_id: str):
    connection = get_connection()
    try:
        source = connection.execute("SELECT * FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone()
        if source is None:
            raise HTTPException(404, "Knowledge source not found")
        chunks = connection.execute("SELECT * FROM knowledge_chunks WHERE source_id=? ORDER BY id", (source_id,)).fetchall()
    finally:
        connection.close()
    return {"source": {"source_id": source["source_id"], "title": source["title"], "author": source["author"], "date": source["date"], "type": source["type"], "layer": source["category"], "subcategory": source["subcategory"], "tags": json.loads(source["tags_json"] or "[]"), "project": source["project"], "client": source["client"], "language": source["language"], "status": source["ingestion_status"], "source_path": source["source_path"], "timestamp": source["timestamp"]}, "chunks": [dict(row) for row in chunks], "chunks_count": len(chunks)}


def _requeue(source_id: str, priority: int):
    connection = get_connection()
    try:
        row = connection.execute("SELECT storage_path FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(404, "Knowledge source not found")
    if not row["storage_path"] or not Path(row["storage_path"]).is_file():
        raise HTTPException(400, "Stored original is unavailable")
    try:
        return _accepted(IngestionRegistrar().enqueue_existing(source_id, priority=priority))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/sources/{source_id}/reprocess")
def reprocess_source(source_id: str):
    return _requeue(source_id, 15)


@router.post("/sources/{source_id}/retry")
def retry_failed_source(source_id: str):
    return _requeue(source_id, 12)


@router.delete("/sources/{source_id}")
def delete_source(source_id: str):
    """Delete only while the production ingestion writer lock is available."""
    lock_path = Path(os.environ.get(
        "BRAIN_INGESTION_WRITER_LOCK", str(DATA_DIR / ".ingestion-writer.lock")
    ))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409, "Knowledge writer is active; retry deletion later.")
        connection = get_connection()
        try:
            row = connection.execute("SELECT 1 FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone()
        finally:
            connection.close()
        if row is None:
            raise HTTPException(404, "Knowledge source not found")
        from src.brain.knowledge.factory import KnowledgeIngestionFactory
        KnowledgeIngestionFactory().delete_source(source_id)
    return {"status": "deleted", "source_id": source_id}


@router.get("/sources/{source_id}/status")
def get_source_status(source_id: str):
    connection = get_connection()
    try:
        row = connection.execute("SELECT job_id FROM ingestion_jobs WHERE source_id=? ORDER BY created_at DESC LIMIT 1", (source_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(404, "Source status not found")
    return job_status(row["job_id"])


@router.post("/search")
def hybrid_search(req: KnowledgeSearchRequest):
    from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
    hits = HybridSearchEngine().search(query=req.query, layer=req.layer, project_id=req.project, client_id=req.client, top_k=req.limit, min_score=req.min_score)
    return {"query": req.query, "layer": req.layer.value if req.layer else None, "total_hits": len(hits), "results": [{"chunk": chunk.model_dump(), "score": score, "source_trace": trace.model_dump()} for chunk, score, trace in hits]}


@router.get("/stats")
def get_knowledge_stats():
    connection = get_connection()
    try:
        total_sources = connection.execute("SELECT COUNT(*) FROM knowledge_sources").fetchone()[0]
        by_layer = dict(connection.execute("SELECT category, COUNT(*) FROM knowledge_sources GROUP BY category").fetchall())
        by_status = dict(connection.execute("SELECT ingestion_status, COUNT(*) FROM knowledge_sources GROUP BY ingestion_status").fetchall())
        total_chunks = connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
        queue_stats = dict(connection.execute("SELECT status, COUNT(*) FROM ingestion_jobs GROUP BY status").fetchall())
    finally:
        connection.close()
    return {"total_sources": total_sources, "by_layer": by_layer, "by_status": by_status, "total_chunks": total_chunks, "queue": queue_stats}


@router.post("/ingest")
def scan_and_register_directory(req: DirectoryIngestRequest):
    target = Path(req.directory_path)
    if not target.is_dir():
        raise HTTPException(400, f"Directory '{target}' does not exist or is not a directory.")
    pattern = "**/*" if req.recursive else "*"
    registrar = IngestionRegistrar()
    jobs = []
    for path in target.glob(pattern):
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS and not path.name.startswith("."):
            result = registrar.register_file(path, original_filename=path.name, layer=req.default_layer or KnowledgeLayer.GLOBAL)
            jobs.append({"job_id": result.job.job_id, "source_id": result.source_id, "status": result.job.status.value})
    return JSONResponse({"directory": str(target.resolve()), "registered": len(jobs), "jobs": jobs}, status_code=status.HTTP_202_ACCEPTED)
