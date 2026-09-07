"""
Test Suite: Hardened Security, Magic Bytes, Traversal Prevention, and Eval Regression.
"""
import ast
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.brain.api.app import app
from src.brain.knowledge.storage import StorageManager, validate_magic_bytes, is_safe_storage_path


def test_401_on_missing_bearer_token():
    """Verifies that all protected endpoints return HTTP 401 when unauthenticated."""
    unauthed_client = TestClient(app)

    # 1. /brain/*
    r1 = unauthed_client.post("/brain/chat", json={"query": "Привет"})
    assert r1.status_code == 401
    assert "WWW-Authenticate" in r1.headers

    # 2. /knowledge/*
    r2 = unauthed_client.get("/knowledge/sources")
    assert r2.status_code == 401
    assert "WWW-Authenticate" in r2.headers

    # 3. /v1/models
    r3 = unauthed_client.get("/v1/models")
    assert r3.status_code == 401

    # 4. /v1/chat/completions
    r4 = unauthed_client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "Hi"}]})
    assert r4.status_code == 401


def test_401_on_invalid_bearer_token():
    """Verifies that requests with invalid bearer token are rejected."""
    bad_client = TestClient(app, headers={"Authorization": "Bearer totally-fake-token-12345"})

    r = bad_client.get("/v1/models")
    assert r.status_code == 401


def test_magic_bytes_blocks_disguised_executable(tmp_path):
    """Verifies that an executable (MZ header) disguised as .pdf is rejected."""
    storage = StorageManager(originals_dir=tmp_path / "orig", derived_dir=tmp_path / "der")
    fake_pdf = tmp_path / "invoice.pdf"
    # Write Windows PE/MZ header
    fake_pdf.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00")

    val = storage.validate_file(fake_pdf)
    assert val.is_valid is False
    assert "executable" in val.error_message.lower() or "magic" in val.error_message.lower()


def test_magic_bytes_blocks_mismatched_image(tmp_path):
    """Verifies that random binary or text disguised as a PNG is rejected."""
    storage = StorageManager(originals_dir=tmp_path / "orig", derived_dir=tmp_path / "der")
    fake_png = tmp_path / "photo.png"
    fake_png.write_text("This is plain text pretending to be PNG image data")

    val = storage.validate_file(fake_png)
    assert val.is_valid is False
    assert "magic" in val.error_message.lower()


def test_canonical_path_traversal_rejection(tmp_path):
    """Verifies that is_safe_storage_path rejects paths outside the allowed root."""
    root_dir = tmp_path / "storage"
    root_dir.mkdir()

    # Safe path
    safe_path = root_dir / "originals" / "file.pdf"
    assert is_safe_storage_path(safe_path, root_dir) is True

    # Traversal escaping root
    escape_path = root_dir / ".." / ".." / "etc" / "passwd"
    assert is_safe_storage_path(escape_path, root_dir) is False


def test_eval_eliminated_from_knowledge_codebase():
    """
    AST-based regression test: Ensures no call to eval() exists anywhere
    in src/brain/knowledge to prevent remote code execution vulnerabilities.
    """
    knowledge_dir = Path("src/brain/knowledge")
    assert knowledge_dir.exists()

    found_evals = []
    for py_file in knowledge_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "eval":
                        found_evals.append((str(py_file), node.lineno))
        except Exception:
            pass

    assert len(found_evals) == 0, f"Dangerous eval() calls detected: {found_evals}"
