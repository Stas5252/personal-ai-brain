#!/usr/bin/env python3
"""Build and atomically swap a complete Chroma vector index.

The command must run with API and worker stopped. It acquires the same lifetime
writer lock as the worker, never mutates SQLite knowledge rows, and leaves the
previous vector directory as a rollback target.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.brain.services.file_lock import acquire_exclusive_lock

MANIFEST_FILENAME = ".vector-reindex-manifest.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _manifest_path(data_dir: Path) -> Path:
    return data_dir / MANIFEST_FILENAME


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def _writer_lock(data_dir: Path):
    lock_path = Path(os.environ.get("BRAIN_INGESTION_WRITER_LOCK", str(data_dir / ".ingestion-writer.lock")))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            acquire_exclusive_lock(handle)
        except BlockingIOError as exc:
            raise RuntimeError("Another ingestion writer owns the lock; stop it before reindex") from exc
        yield


def _assert_worker_stopped(data_dir: Path, max_age_seconds: int = 60) -> None:
    from src.brain.health import WORKER_HEARTBEAT_FILENAME

    heartbeat = data_dir / WORKER_HEARTBEAT_FILENAME
    if not heartbeat.exists():
        return
    try:
        payload = json.loads(heartbeat.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(str(payload["updated_at"]))
        age = (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Worker heartbeat exists but is invalid; inspect it before reindex") from exc
    if age <= max_age_seconds:
        raise RuntimeError("Knowledge worker heartbeat is active; stop the worker before reindex")


def _database_chunk_count() -> int:
    from src.brain.db import get_connection

    connection = get_connection()
    try:
        return int(connection.execute("SELECT count(*) FROM knowledge_chunks").fetchone()[0])
    finally:
        connection.close()


def _current_summary(vector_dir: Path) -> dict:
    from src.brain.knowledge.indexing.vector_index import COLLECTION_NAME, SPEC_FILENAME

    result = {"path": str(vector_dir), "exists": vector_dir.exists(), "vectors": 0, "spec": None}
    spec_path = vector_dir / SPEC_FILENAME
    if spec_path.is_file():
        result["spec"] = json.loads(spec_path.read_text(encoding="utf-8"))
    if vector_dir.is_dir():
        try:
            import chromadb

            result["vectors"] = int(chromadb.PersistentClient(path=str(vector_dir)).get_collection(COLLECTION_NAME).count())
        except Exception:
            result["vectors"] = 0
    return result


def plan() -> int:
    from src.brain.config import DATA_DIR, VECTOR_DB_DIR

    payload = {"database_chunks": _database_chunk_count(), "current": _current_summary(Path(VECTOR_DB_DIR)),
               "worker_heartbeat": str(Path(DATA_DIR) / ".knowledge-worker-heartbeat.json")}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _build_staging(staging: Path, batch_size: int) -> int:
    from src.brain.db import get_connection
    from src.brain.knowledge.embeddings.implementations import get_embedding_provider
    from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex

    provider = get_embedding_provider()
    index = ChromaVectorIndex(vector_dir=staging, embedding_provider=provider)
    connection = get_connection()
    offset = total = 0
    try:
        while True:
            rows = connection.execute(
                """SELECT id, source_id, layer, content, content_type, page_number,
                          slide_number, sheet_name, start_time, end_time, heading_path,
                          metadata_json, created_at
                   FROM knowledge_chunks ORDER BY id LIMIT ? OFFSET ?""",
                (batch_size, offset),
            ).fetchall()
            if not rows:
                break
            documents = [row["content"] for row in rows]
            embeddings = index._validate_embeddings(provider.embed_documents(documents), len(rows))
            metadatas = []
            for row in rows:
                try:
                    source_metadata = json.loads(row["metadata_json"] or "{}")
                except (TypeError, ValueError):
                    source_metadata = {}
                metadatas.append({
                    "source_id": row["source_id"], "layer": row["layer"],
                    "content_type": row["content_type"] or "text",
                    "page_number": row["page_number"] if row["page_number"] is not None else -1,
                    "slide_number": row["slide_number"] if row["slide_number"] is not None else -1,
                    "sheet_name": row["sheet_name"] or "",
                    "start_time": row["start_time"] if row["start_time"] is not None else -1.0,
                    "end_time": row["end_time"] if row["end_time"] is not None else -1.0,
                    "heading_path": row["heading_path"] or "",
                    "title": str(source_metadata.get("title") or row["source_id"]),
                    "created_at": row["created_at"],
                })
            index.collection.upsert(ids=[row["id"] for row in rows], documents=documents,
                                    embeddings=embeddings, metadatas=metadatas)
            total += len(rows)
            offset += len(rows)
            print(f"Indexed {total} chunks", file=sys.stderr)
    finally:
        connection.close()
    actual = int(index.count())
    if actual != total:
        raise RuntimeError(f"Staging Chroma count mismatch: expected {total}, got {actual}")
    del index
    gc.collect()
    return total


def _apply_locked(data_dir: Path, vector_dir: Path, batch_size: int) -> int:
    _assert_worker_stopped(data_dir)
    expected = _database_chunk_count()
    if expected <= 0:
        raise RuntimeError("Refusing to replace the vector index because SQLite has no chunks")
    stamp = _timestamp()
    staging = vector_dir.with_name(f"{vector_dir.name}.staging-{stamp}-{os.getpid()}")
    backup = vector_dir.with_name(f"{vector_dir.name}.backup-{stamp}")
    if staging.exists() or backup.exists():
        raise RuntimeError("Reindex staging or backup path already exists")
    manifest = {"operation": "vector_reindex", "status": "building",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "current_path": str(vector_dir), "staging_path": str(staging),
                "backup_path": str(backup), "database_chunks": expected}
    _write_json(_manifest_path(data_dir), manifest)
    try:
        actual = _build_staging(staging, batch_size)
        if actual != expected:
            raise RuntimeError(f"Source changed during reindex: expected {expected}, built {actual}")
        if vector_dir.exists():
            os.replace(vector_dir, backup)
        try:
            os.replace(staging, vector_dir)
        except Exception:
            if backup.exists() and not vector_dir.exists():
                os.replace(backup, vector_dir)
            raise
        manifest.update(status="completed", completed_at=datetime.now(timezone.utc).isoformat(),
                        vectors=actual, new=_current_summary(vector_dir))
        _write_json(_manifest_path(data_dir), manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception:
        manifest.update(status="failed", failed_at=datetime.now(timezone.utc).isoformat())
        _write_json(_manifest_path(data_dir), manifest)
        shutil.rmtree(staging, ignore_errors=True)
        raise


def apply(confirm: str, batch_size: int) -> int:
    if confirm != "REINDEX":
        raise RuntimeError("Refusing reindex without --confirm REINDEX")
    from src.brain.config import DATA_DIR, VECTOR_DB_DIR

    data_dir = Path(DATA_DIR)
    with _writer_lock(data_dir):
        return _apply_locked(data_dir, Path(VECTOR_DB_DIR), batch_size)


def _rollback_locked(data_dir: Path, vector_dir: Path) -> int:
    _assert_worker_stopped(data_dir)
    manifest_path = _manifest_path(data_dir)
    if not manifest_path.is_file():
        raise RuntimeError("No vector reindex manifest is available")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup = Path(str(manifest.get("backup_path", "")))
    if manifest.get("status") != "completed" or not backup.is_dir():
        raise RuntimeError("The last completed reindex has no usable backup")
    quarantine = vector_dir.with_name(f"{vector_dir.name}.rolled-back-{_timestamp()}")
    if quarantine.exists():
        raise RuntimeError("Rollback quarantine path already exists")
    if vector_dir.exists():
        os.replace(vector_dir, quarantine)
    try:
        os.replace(backup, vector_dir)
    except Exception:
        if quarantine.exists() and not vector_dir.exists():
            os.replace(quarantine, vector_dir)
        raise
    manifest.update(status="rolled_back", rolled_back_at=datetime.now(timezone.utc).isoformat(),
                    quarantined_path=str(quarantine), restored=_current_summary(vector_dir))
    _write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def rollback(confirm: str) -> int:
    if confirm != "ROLLBACK":
        raise RuntimeError("Refusing rollback without --confirm ROLLBACK")
    from src.brain.config import DATA_DIR, VECTOR_DB_DIR

    data_dir = Path(DATA_DIR)
    with _writer_lock(data_dir):
        return _rollback_locked(data_dir, Path(VECTOR_DB_DIR))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--confirm", required=True)
    apply_parser.add_argument("--batch-size", type=int, default=128)
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        return plan()
    if args.command == "apply":
        if args.batch_size <= 0:
            raise RuntimeError("--batch-size must be positive")
        return apply(args.confirm, args.batch_size)
    return rollback(args.confirm)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Vector reindex failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
