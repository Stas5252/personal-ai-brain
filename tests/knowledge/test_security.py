"""
Tests for Security, Path Traversal Prevention, Size Limits, and Sanitization.
"""
import pytest
from pathlib import Path
from src.brain.knowledge.storage import StorageManager
from src.brain.knowledge.factory import KnowledgeIngestionFactory

@pytest.fixture
def storage():
    return StorageManager()

@pytest.fixture
def factory():
    return KnowledgeIngestionFactory()


def test_path_traversal_prevention(storage, tmp_path):
    traversal_attacks = [
        "../../../../Windows/System32/calc.exe",
        "..\\..\\..\\boot.ini",
        "nested/../../secret.pdf",
        "/etc/shadow",
        "file:///etc/hosts"
    ]
    for attack in traversal_attacks:
        sanitized = storage.sanitize_filename(attack)
        assert "/" not in sanitized
        assert "\\" not in sanitized
        assert ".." not in sanitized


def test_dangerous_extensions_rejected(storage, tmp_path):
    dangerous = ["script.sh", "payload.bat", "trojan.exe", "library.dll", "code.py", "macro.xlsm"]
    for d in dangerous:
        f = tmp_path / d
        f.write_text("malicious content")
        val = storage.validate_file(f)
        assert not val.is_valid
        assert "Unsupported file extension" in val.error_message


def test_zero_byte_empty_file_rejected(storage, tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.touch()
    val = storage.validate_file(empty)
    assert not val.is_valid
    assert "empty" in val.error_message.lower()


def test_factory_rejects_invalid_file_gracefully(factory, tmp_path):
    bad_file = tmp_path / "danger.exe"
    bad_file.write_bytes(b"\x00\x01\x02\x03")
    with pytest.raises(ValueError) as exc:
        factory.ingest_file(bad_file)
    assert "validation failed" in str(exc.value).lower()
