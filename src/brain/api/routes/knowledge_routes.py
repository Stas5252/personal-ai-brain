"""
REST API Routes for Knowledge Ingestion Factory.
Provides comprehensive endpoints for source ingestion, file upload, status,
reprocessing, deletion, stats, batch directory scanning, and hybrid retrieval.
"""
import os
import shutil
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.brain.config import ORIGINALS_DIR, MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS
from src.brain.db import get_connection
from src.brain.api.security import verify_brain_api_key
from src.brain.models.knowledge import (
    KnowledgeLayer, KnowledgeMetadata, KnowledgeChunk, SourceTrace,
    IngestionStatus, ContentType
)
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(verify_brain_api_key)]
)

factory = KnowledgeIngestionFactory()
search_engine = HybridSearchEngine()
queue = IngestionQueue()


# --- Request & Response Models ---

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


class ReprocessResponse(BaseModel):
    status: str
    source_id: str
    chunks_count: int


# --- Endpoints ---

@router.post("/sources")
async def create_or_upload_source(
    file: Optional[UploadFile] = File(None),
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    layer: Optional[str] = Form(None),
    subcategory: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    client: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    force: bool = Form(False)
):
    """
    Ingests a knowledge source either via multipart file upload or text content.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    layer_enum = None
    if layer:
        try:
            layer_enum = KnowledgeLayer(layer.upper())
        except ValueError:
            layer_enum = KnowledgeLayer.GLOBAL

    if file and file.filename:
        # File upload branch - fully asynchronous ingestion
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{suffix}'. Allowed: {sorted(list(ALLOWED_EXTENSIONS))}"
            )

        temp_dir = Path("data/storage/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file_path = temp_dir / f"upload_{uuid.uuid4().hex[:8]}_{file.filename}"

        try:
            with open(temp_file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)

            file_size = temp_file_path.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES} bytes."
                )

            # Deep magic bytes and format validation
            val = factory.storage.validate_file(temp_file_path)
            if not val.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File validation failed: {val.error_message}"
                )

            # Duplicate detection
            existing = factory.storage.check_duplicate(val.sha256)
            if existing and not force:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "DUPLICATE",
                        "source_id": existing["source_id"],
                        "message": "Source already exists in knowledge store"
                    }
                )

            # Store original file permanently in originals storage
            orig_dest = factory.storage.store_original(temp_file_path, val.sha256, val.safe_filename)
            source_id = str(uuid.uuid4())
            derived_dir = factory.storage.get_derived_dir(source_id)
            now_str = datetime.now(timezone.utc).isoformat()
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            source_title = title or Path(file.filename).stem.replace("_", " ").title()

            meta = {
                "author": author or "User",
                "subcategory": subcategory,
                "tags": tag_list,
                "project": project,
                "client": client,
                "layer": (layer_enum.value if layer_enum else KnowledgeLayer.GLOBAL.value)
            }

            conn = get_connection()
            c = conn.cursor()
            c.execute("""
            INSERT INTO knowledge_sources (
                source_id, title, author, date, type, category, subcategory,
                tags_json, project, client, language, source_path, timestamp,
                confidence, original_filename, mime_type, file_size, sha256,
                p_hash, storage_path, derived_dir, ingestion_status,
                processing_version, classification_method, seen_count,
                checkpoint_stage, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_id, source_title, author or "User", date_str, "document",
                (layer_enum.value if layer_enum else KnowledgeLayer.GLOBAL.value), subcategory,
                json.dumps(tag_list), project, client,
                "ru", str(orig_dest), now_str, 1.0,
                val.safe_filename, val.mime_type, val.file_size, val.sha256,
                val.p_hash, str(orig_dest), str(derived_dir), "QUEUED",
                "v1.0", "rules", 1, "QUEUED", json.dumps(meta)
            ))
            conn.commit()
            conn.close()

            # Enqueue asynchronous ingestion job
            job = queue.enqueue_job(source_id=source_id, priority=10)

            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "QUEUED",
                    "source_id": source_id,
                    "job_id": job.job_id,
                    "message": "File accepted and queued for background ingestion."
                }
            )
        finally:
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass

    elif content:
        # Direct text ingestion branch
        from src.brain.engines.knowledge_engine import KnowledgeEngine
        ke = KnowledgeEngine()
        target_layer = layer_enum or KnowledgeLayer.PROFESSIONAL
        source_title = title or "User Text Source"
        meta, chunks = ke.add_source(
            title=source_title,
            content=content,
            layer=target_layer,
            author=author or "User",
            subcategory=subcategory,
            tags=tag_list,
            project=project,
            client=client
        )
        return {
            "status": IngestionStatus.COMPLETED.value,
            "source": meta.model_dump(),
            "chunks_count": len(chunks)
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'file' or 'content' must be provided."
        )


@router.get("/sources")
def list_sources(
    layer: Optional[KnowledgeLayer] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    query: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Lists knowledge sources with optional filtering by layer, status, and search term.
    """
    conn = get_connection()
    c = conn.cursor()

    sql = "SELECT * FROM knowledge_sources WHERE 1=1"
    params = []

    if layer:
        sql += " AND category = ?"
        params.append(layer.value)

    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)

    if query:
        sql += " AND (title LIKE ? OR subcategory LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    c.execute(sql, params)
    rows = c.fetchall()

    sources = []
    for r in rows:
        tags = []
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except Exception:
            pass

        sources.append({
            "source_id": r["source_id"],
            "title": r["title"],
            "author": r["author"],
            "date": r["date"],
            "type": r["type"],
            "layer": r["category"],
            "subcategory": r["subcategory"],
            "tags": tags,
            "project": r["project"],
            "client": r["client"],
            "language": r["language"],
            "status": r["status"] if "status" in r.keys() else "COMPLETED",
            "content_hash": r["content_hash"] if "content_hash" in r.keys() else None,
            "timestamp": r["timestamp"]
        })

    # Total count query
    count_sql = "SELECT COUNT(*) FROM knowledge_sources WHERE 1=1"
    count_params = []
    if layer:
        count_sql += " AND category = ?"
        count_params.append(layer.value)
    if status_filter:
        count_sql += " AND status = ?"
        count_params.append(status_filter)
    if query:
        count_sql += " AND (title LIKE ? OR subcategory LIKE ?)"
        count_params.extend([f"%{query}%", f"%{query}%"])

    c.execute(count_sql, count_params)
    total = c.fetchone()[0]
    conn.close()

    return {"sources": sources, "total": total, "limit": limit, "offset": offset}


@router.get("/sources/{source_id}")
def get_source_detail(source_id: str):
    """
    Returns full details of a knowledge source including all extracted chunks.
    """
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,))
    source_row = c.fetchone()
    if not source_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    c.execute("SELECT * FROM knowledge_chunks WHERE source_id = ? ORDER BY id ASC", (source_id,))
    chunk_rows = c.fetchall()
    conn.close()

    tags = []
    try:
        tags = json.loads(source_row["tags_json"] or "[]")
    except Exception:
        pass

    chunks = []
    for cr in chunk_rows:
        chunks.append({
            "id": cr["id"],
            "layer": cr["layer"],
            "content": cr["content"],
            "content_type": cr["content_type"] if "content_type" in cr.keys() else "text",
            "page_number": cr["page_number"] if "page_number" in cr.keys() else None,
            "slide_number": cr["slide_number"] if "slide_number" in cr.keys() else None,
            "sheet_name": cr["sheet_name"] if "sheet_name" in cr.keys() else None,
            "start_time": cr["start_time"] if "start_time" in cr.keys() else None,
            "end_time": cr["end_time"] if "end_time" in cr.keys() else None,
            "heading_path": cr["heading_path"] if "heading_path" in cr.keys() else None,
            "created_at": cr["created_at"]
        })

    return {
        "source": {
            "source_id": source_row["source_id"],
            "title": source_row["title"],
            "author": source_row["author"],
            "date": source_row["date"],
            "type": source_row["type"],
            "layer": source_row["category"],
            "subcategory": source_row["subcategory"],
            "tags": tags,
            "project": source_row["project"],
            "client": source_row["client"],
            "language": source_row["language"],
            "status": source_row["status"] if "status" in source_row.keys() else "COMPLETED",
            "source_path": source_row["source_path"],
            "visual_description": source_row["visual_description"],
            "ocr_text": source_row["ocr_text"],
            "timestamp": source_row["timestamp"]
        },
        "chunks": chunks,
        "chunks_count": len(chunks)
    }


@router.post("/sources/{source_id}/reprocess")
def reprocess_source(source_id: str):
    """
    Asynchronously re-queues an existing source for full re-extraction and indexing.
    Returns HTTP 202 Accepted.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    source_path = row["source_path"] or row["storage_path"]
    if not source_path or not Path(source_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Original source file not found at '{source_path}'. Cannot reprocess."
        )

    # Queue reprocess job with high priority
    job = queue.enqueue_job(source_id=source_id, priority=15)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "QUEUED",
            "source_id": source_id,
            "job_id": job.job_id,
            "message": "Source queued for background reprocessing."
        }
    )


@router.post("/sources/{source_id}/retry")
def retry_failed_source(source_id: str):
    """
    Asynchronously retries ingestion for a failed source. Returns HTTP 202 Accepted.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    source_path = row["source_path"] or row["storage_path"]
    if not source_path or not Path(source_path).exists():
        raise HTTPException(status_code=400, detail="Source file unavailable for retry")

    job = queue.enqueue_job(source_id=source_id, priority=12)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "QUEUED",
            "source_id": source_id,
            "job_id": job.job_id,
            "message": "Source queued for retry."
        }
    )


@router.delete("/sources/{source_id}")
def delete_source(source_id: str):
    """
    Completely purges a source and its chunks from SQLite, FTS5, and ChromaDB vector store.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    # Get chunk IDs to purge from vector index
    c.execute("SELECT id FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    chunk_ids = [r[0] for r in c.fetchall()]

    # Delete from ChromaDB
    if chunk_ids:
        try:
            from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
            from src.brain.knowledge.embeddings.implementations import get_embedding_provider
            v_index = ChromaVectorIndex(embedding_provider=get_embedding_provider())
            v_index.delete_chunks(chunk_ids)
        except Exception:
            pass

    # Delete from FTS5
    try:
        c.execute("DELETE FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,))
    except Exception:
        pass
    if chunk_ids:
        placeholders = ",".join("?" for _ in chunk_ids)
        try:
            c.execute(f"DELETE FROM knowledge_chunks_fts WHERE chunk_id IN ({placeholders})", chunk_ids)
        except Exception:
            pass

    # Delete from SQLite
    c.execute("DELETE FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    c.execute("DELETE FROM knowledge_sources WHERE source_id = ?", (source_id,))
    c.execute("DELETE FROM ingestion_jobs WHERE source_id = ?", (source_id,))
    conn.commit()
    conn.close()

    return {
        "status": "deleted",
        "source_id": source_id,
        "purged_chunks": len(chunk_ids)
    }


@router.get("/sources/{source_id}/status")
def get_source_status(source_id: str):
    """
    Returns rich live ingestion status, lease details, and step for a source.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,))
    row = c.fetchone()

    # Check latest queue job
    c.execute("SELECT * FROM ingestion_jobs WHERE source_id = ? ORDER BY created_at DESC LIMIT 1", (source_id,))
    job_row = c.fetchone()
    conn.close()

    if not row and not job_row:
        raise HTTPException(status_code=404, detail="Source status not found")

    j_keys = job_row.keys() if (job_row and hasattr(job_row, "keys")) else []
    r_keys = row.keys() if (row and hasattr(row, "keys")) else []

    job_info = None
    if job_row:
        job_info = {
            "job_id": job_row["job_id"],
            "job_status": job_row["status"],
            "current_step": job_row["stage"],
            "retry_count": job_row["attempts"],
            "worker_id": job_row["worker_id"] if "worker_id" in j_keys else None,
            "lease_until": job_row["lease_until"] if "lease_until" in j_keys else None,
            "progress": job_row["progress"],
            "error": job_row["error_message"]
        }

    status_val = row["ingestion_status"] if row and row["ingestion_status"] else (job_row["status"] if job_row else "UNKNOWN")

    return {
        "source_id": source_id,
        "status": status_val,
        "stage": job_row["stage"] if job_row else (row["checkpoint_stage"] if "checkpoint_stage" in r_keys else "UNKNOWN"),
        "progress": job_row["progress"] if job_row else (1.0 if status_val == "COMPLETED" else 0.0),
        "attempt": job_row["attempts"] if job_row else 0,
        "max_attempts": job_row["max_attempts"] if job_row else 3,
        "worker_id": job_row["worker_id"] if job_row and "worker_id" in j_keys else None,
        "lease_until": job_row["lease_until"] if job_row and "lease_until" in j_keys else None,
        "started_at": job_row["created_at"] if job_row else (row["timestamp"] if "timestamp" in r_keys else None),
        "updated_at": job_row["updated_at"] if job_row else (row["timestamp"] if "timestamp" in r_keys else None),
        "error": job_row["error_message"] if job_row else (row["error_message"] if "error_message" in r_keys else None),
        "error_message": row["error_message"] if row and "error_message" in r_keys else None,
        "job": job_info
    }


@router.post("/search")
def hybrid_search(req: KnowledgeSearchRequest):
    """
    Performs hybrid dense vector + FTS5 full-text search across knowledge chunks.
    """
    hits = search_engine.search(
        query=req.query,
        layer=req.layer,
        project_id=req.project,
        client_id=req.client,
        top_k=req.limit,
        min_score=req.min_score
    )

    results = []
    for chunk, score, trace in hits:
        results.append({
            "chunk": chunk.model_dump(),
            "score": score,
            "source_trace": trace.model_dump()
        })

    return {
        "query": req.query,
        "layer": req.layer.value if req.layer else None,
        "total_hits": len(results),
        "results": results
    }


@router.get("/stats")
def get_knowledge_stats():
    """
    Returns global statistics on sources, layers, chunks, vector index, and queue.
    """
    conn = get_connection()
    c = conn.cursor()

    # Total sources
    c.execute("SELECT COUNT(*) FROM knowledge_sources")
    total_sources = c.fetchone()[0]

    # Sources by layer
    c.execute("SELECT category, COUNT(*) FROM knowledge_sources GROUP BY category")
    by_layer = {r[0]: r[1] for r in c.fetchall()}

    # Sources by status
    by_status = {}
    try:
        c.execute("SELECT status, COUNT(*) FROM knowledge_sources GROUP BY status")
        by_status = {r[0]: r[1] for r in c.fetchall()}
    except Exception:
        pass

    # Total chunks
    c.execute("SELECT COUNT(*) FROM knowledge_chunks")
    total_chunks = c.fetchone()[0]

    # Queue stats
    c.execute("SELECT status, COUNT(*) FROM ingestion_jobs GROUP BY status")
    queue_stats = {r[0]: r[1] for r in c.fetchall()}

    conn.close()

    # Vector index count
    vector_count = 0
    try:
        from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
        from src.brain.knowledge.embeddings.implementations import get_embedding_provider
        v_index = ChromaVectorIndex(embedding_provider=get_embedding_provider())
        vector_count = v_index.collection.count()
    except Exception:
        pass

    return {
        "total_sources": total_sources,
        "by_layer": by_layer,
        "by_status": by_status,
        "total_chunks": total_chunks,
        "vector_index_count": vector_count,
        "queue": queue_stats
    }


@router.post("/ingest")
def scan_and_ingest_directory(req: DirectoryIngestRequest):
    """
    Scans a local directory and ingests all supported files.
    """
    target_path = Path(req.directory_path)
    if not target_path.exists() or not target_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Directory '{req.directory_path}' does not exist or is not a directory."
        )

    sources = factory.scan_directory(
        dir_path=target_path,
        recursive=req.recursive,
        default_layer=req.default_layer
    )

    return {
        "directory": str(target_path.resolve()),
        "total_ingested": len(sources),
        "sources": [s.model_dump() for s in sources]
    }
