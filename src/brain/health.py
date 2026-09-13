"""Offline-safe liveness details and metrics for production probes."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.brain import config
from src.brain.db import get_connection
from src.brain.knowledge.indexing.vector_index import (
    COLLECTION_NAME,
    SPEC_FILENAME,
    SPEC_SCHEMA_VERSION,
)

CORE_SOURCE_MINIMUM = 5
WORKER_HEARTBEAT_FILENAME = ".knowledge-worker-heartbeat.json"


def _expected_embedding_spec() -> dict[str, Any]:
    provider = config.EMBEDDING_PROVIDER_TYPE.strip().lower()
    if provider in {"chroma_onnx", "onnx"}:
        name, dimension = "chroma_onnx_all_MiniLM_L6_v2", 384
    elif provider == "hash_fallback":
        name, dimension = "hash_deterministic_128d", 128
    elif provider == "gemini":
        model = os.environ.get("GEMINI_EMBEDDING_MODEL", "text-embedding-004").strip()
        name, dimension = f"gemini_{model}", 768
    else:
        raise RuntimeError(f"Unsupported embedding provider: {provider!r}")
    return {"schema_version": SPEC_SCHEMA_VERSION, "provider": name, "dimension": dimension}


def check_database() -> dict[str, Any]:
    connection = get_connection()
    try:
        connection.execute("SELECT 1").fetchone()
        result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if str(result).lower() != "ok":
            raise RuntimeError(f"SQLite quick_check failed: {result}")
        return {"ok": True}
    finally:
        connection.close()


def check_storage() -> dict[str, Any]:
    required = (config.DATA_DIR, config.STORAGE_DIR, config.VECTOR_DB_DIR)
    missing = [str(path) for path in required if not Path(path).is_dir()]
    if missing:
        raise RuntimeError("Required storage directories are missing")
    return {"ok": True}


def check_vector_store() -> dict[str, Any]:
    vector_dir = Path(config.VECTOR_DB_DIR)
    spec_path = vector_dir / SPEC_FILENAME
    if not spec_path.is_file():
        raise RuntimeError("Embedding spec is missing; vector index is not initialized")
    try:
        actual = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Embedding spec is unreadable") from exc
    expected = _expected_embedding_spec()
    if actual != expected:
        raise RuntimeError("Embedding spec does not match configured provider")

    import chromadb

    client = chromadb.PersistentClient(path=str(vector_dir))
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError("Chroma collection is unavailable") from exc
    count = int(collection.count())
    if count <= 0:
        raise RuntimeError("Chroma collection is empty")
    return {"ok": True, "vectors": count, "spec": actual}


def check_core_knowledge() -> dict[str, Any]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT s.source_id, s.ingestion_status,
                   (SELECT count(*) FROM knowledge_chunks c WHERE c.source_id = s.source_id) AS chunk_count,
                   (SELECT count(*) FROM ingestion_jobs j WHERE j.source_id = s.source_id
                    AND j.status NOT IN ('COMPLETED','FAILED','SKIPPED','DUPLICATE')) AS active_jobs,
                   (SELECT count(*) FROM ingestion_jobs j WHERE j.source_id = s.source_id
                    AND j.status = 'FAILED') AS failed_jobs
            FROM knowledge_sources s
            WHERE json_valid(s.metadata_json)
              AND json_extract(s.metadata_json, '$.authority_tier') = 'core'
            """
        ).fetchall()
    finally:
        connection.close()
    if len(rows) < CORE_SOURCE_MINIMUM:
        raise RuntimeError("Verified core knowledge is incomplete")
    unhealthy = [row["source_id"] for row in rows if row["ingestion_status"] != "COMPLETED"
                 or int(row["chunk_count"]) <= 0 or int(row["active_jobs"]) > 0
                 or int(row["failed_jobs"]) > 0]
    if unhealthy:
        raise RuntimeError("Verified core knowledge has unsettled or failed jobs")
    return {"ok": True, "sources": len(rows), "chunks": sum(int(row["chunk_count"]) for row in rows)}


def check_worker_heartbeat(now: datetime | None = None) -> dict[str, Any]:
    path = Path(config.DATA_DIR) / WORKER_HEARTBEAT_FILENAME
    if not path.is_file():
        raise RuntimeError("Knowledge worker heartbeat is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        pid = int(payload["pid"])
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise RuntimeError("Knowledge worker heartbeat is invalid") from exc
    if updated_at.tzinfo is None or pid <= 0:
        raise RuntimeError("Knowledge worker heartbeat is invalid")
    current = now or datetime.now(timezone.utc)
    age_seconds = max(0.0, (current - updated_at.astimezone(timezone.utc)).total_seconds())
    try:
        max_age = max(5, int(os.environ.get("BRAIN_WORKER_HEARTBEAT_MAX_AGE_SECONDS", "30")))
    except ValueError as exc:
        raise RuntimeError("BRAIN_WORKER_HEARTBEAT_MAX_AGE_SECONDS must be an integer") from exc
    if age_seconds > max_age:
        raise RuntimeError("Knowledge worker heartbeat is stale")
    return {"ok": True, "age_seconds": round(age_seconds, 3)}


def readiness_report() -> tuple[dict[str, Any], bool]:
    checks = {"database": check_database, "storage": check_storage,
              "vector_store": check_vector_store, "core_knowledge": check_core_knowledge,
              "worker": check_worker_heartbeat}
    components: dict[str, Any] = {}
    ready = bool(config.GEMINI_API_KEY)
    for name, check in checks.items():
        try:
            components[name] = check()
        except Exception as exc:
            components[name] = {"ok": False, "error": str(exc)}
            ready = False
    return {"status": "ready" if ready else "degraded", "components": components,
            "model_key_configured": bool(config.GEMINI_API_KEY), "model_live_check": "not_run"}, ready


def metrics_text() -> str:
    """Return low-cardinality Prometheus metrics without external provider calls."""
    from src.brain.knowledge.queue.ingestion_queue import IngestionQueue

    report, ready = readiness_report()
    components = report["components"]
    lines = [
        "# HELP brain_ready Whether all offline readiness checks pass.",
        "# TYPE brain_ready gauge",
        f"brain_ready {int(ready)}",
    ]
    for name in ("database", "storage", "vector_store", "core_knowledge", "worker"):
        lines.extend([
            f"# HELP brain_component_up Offline readiness for {name}.",
            "# TYPE brain_component_up gauge",
            f'brain_component_up{{component="{name}"}} {int(bool(components.get(name, {}).get("ok")))}',
        ])
    vector_count = int(components.get("vector_store", {}).get("vectors", 0) or 0)
    core_sources = int(components.get("core_knowledge", {}).get("sources", 0) or 0)
    core_chunks = int(components.get("core_knowledge", {}).get("chunks", 0) or 0)
    lines.extend([
        "# TYPE brain_knowledge_vectors gauge", f"brain_knowledge_vectors {vector_count}",
        "# TYPE brain_core_sources gauge", f"brain_core_sources {core_sources}",
        "# TYPE brain_core_chunks gauge", f"brain_core_chunks {core_chunks}",
    ])
    try:
        queue_stats = IngestionQueue().get_stats()
    except Exception:
        queue_stats = {}
    for key in sorted(queue_stats):
        value = queue_stats[key]
        if isinstance(value, (int, float)):
            lines.append(f"brain_ingestion_{key} {value}")
    return "\n".join(lines) + "\n"
