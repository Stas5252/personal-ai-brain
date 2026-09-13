"""Architecture and atomic-registration regressions for production ingestion."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.brain.db import get_connection
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.registration import IngestionRegistrar, job_status

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated_queue():
    IngestionQueue().clear()
    yield
    IngestionQueue().clear()


def test_atomic_registration_creates_one_source_and_one_active_job(tmp_path):
    document = tmp_path / "atomic.md"
    document.write_text("# Atomic\n\nOne durable source and one durable job.", encoding="utf-8")
    registrar = IngestionRegistrar()
    first = registrar.register_file(document, original_filename=document.name)
    second = registrar.register_file(document, original_filename=document.name)
    assert second.source_id == first.source_id
    assert second.job.job_id == first.job.job_id
    assert second.duplicate is True
    connection = get_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_id=?", (first.source_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM ingestion_jobs WHERE source_id=? AND status NOT IN ('COMPLETED','FAILED','SKIPPED','DUPLICATE')", (first.source_id,)).fetchone()[0] == 1
    finally:
        connection.close()


def test_registration_rolls_back_source_when_job_insert_fails(tmp_path, monkeypatch):
    document = tmp_path / "rollback.md"
    document.write_text("# Rollback\n\nThe database operation is indivisible.", encoding="utf-8")
    registrar = IngestionRegistrar()
    monkeypatch.setattr(registrar, "_insert_job", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        registrar.register_file(document, original_filename=document.name)
    connection = get_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM knowledge_sources WHERE title='Rollback'").fetchone()[0] == 0
    finally:
        connection.close()


def test_job_status_is_single_synchronous_contract(tmp_path):
    document = tmp_path / "status.md"
    document.write_text("# Status\n\nCanonical job state.", encoding="utf-8")
    result = IngestionRegistrar().register_file(document, original_filename=document.name)
    payload = job_status(result.job.job_id)
    assert payload == {
        "job_id": result.job.job_id, "source_id": result.source_id,
        "status": "DISCOVERED", "stage": "DISCOVERED", "progress": 0.0,
        "attempts": 0, "max_attempts": 3, "error": None,
        "created_at": result.job.created_at, "updated_at": result.job.updated_at,
        "terminal": False,
    }


def _calls_named(path: Path, attribute: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attribute]


def test_production_producers_never_call_ingest_file():
    producers = [
        ROOT / "src/brain/api/app.py", ROOT / "src/brain/api/routes/knowledge_routes.py",
        ROOT / "src/brain/channels/telegram_production_ingestion.py",
        ROOT / "scripts/seed_vetted_knowledge.py", ROOT / "scripts/ingest_course_corpus.py",
    ]
    offenders = [str(path.relative_to(ROOT)) for path in producers if _calls_named(path, "ingest_file")]
    assert offenders == []


def test_compose_has_one_locked_writer_and_no_background_ingestion():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts/docker_entrypoint.sh").read_text(encoding="utf-8")
    assert compose.count("run_knowledge_worker.py") == 1
    assert "knowledge_bootstrap:" in compose and "db_migrate:" in compose
    assert "telegram_production_ingestion" in compose
    assert "nohup" not in entrypoint
    assert "seed_vetted_knowledge.py" not in entrypoint
    assert "ingest_course_corpus.py" not in entrypoint
