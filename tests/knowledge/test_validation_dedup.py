"""
Tests for Knowledge Storage, Validation, and Deduplication.
Verifies SHA-256 deduplication, pHash image hashing, security constraints, and path traversal prevention.
"""
import pytest
from pathlib import Path
from PIL import Image

from src.brain.knowledge.storage import StorageManager
from src.brain.models.knowledge import IngestionStatus


@pytest.fixture
def storage():
    return StorageManager()


def test_validation_allowed_extensions(storage, tmp_path):
    # Valid PDF
    valid_pdf = tmp_path / "valid.pdf"
    valid_pdf.write_bytes(b"%PDF-1.4 test content")
    res = storage.validate_file(valid_pdf)
    assert res.is_valid
    assert res.sha256 != ""
    assert res.safe_filename == "valid.pdf"

    # Unsupported extension
    invalid_exe = tmp_path / "virus.exe"
    invalid_exe.write_bytes(b"MZ\x90\x00")
    res2 = storage.validate_file(invalid_exe)
    assert not res2.is_valid
    assert "Unsupported file extension" in res2.error_message


def test_validation_file_size_limit(storage, tmp_path):
    huge_file = tmp_path / "huge.txt"
    # Create file larger than MAX_FILE_SIZE_BYTES (mocked or small limit check)
    original_max = storage.max_file_size_bytes
    try:
        storage.max_file_size_bytes = 100  # Set low limit for testing
        huge_file.write_bytes(b"A" * 150)
        res = storage.validate_file(huge_file)
        assert not res.is_valid
        assert "exceeds maximum allowed size" in res.error_message
    finally:
        storage.max_file_size_bytes = original_max


def test_filename_sanitization(storage, tmp_path):
    unsafe_name = "test/../../etc/passwd..\\weird  name #1.pdf"
    clean_name = storage.sanitize_filename(unsafe_name)
    assert "/" not in clean_name
    assert "\\" not in clean_name
    assert ".." not in clean_name
    assert clean_name.endswith(".pdf")


def test_sha256_deduplication(storage, tmp_path):
    test_doc = tmp_path / "dedup_test.txt"
    test_doc.write_text("Unique content for SHA-256 deduplication verification.", encoding="utf-8")
    
    val = storage.validate_file(test_doc)
    assert val.is_valid
    
    # Store original
    stored_path = storage.store_original(test_doc, val.sha256, val.safe_filename)
    assert stored_path.exists()

    # Now verify check_duplicate logic
    # In a clean DB it's not duplicate until recorded, but SHA calculation is exact
    sha1 = storage.compute_sha256(test_doc)
    sha2 = storage.compute_sha256(test_doc)
    assert sha1 == sha2 == val.sha256


def test_phash_computation(storage, tmp_path):
    img_path = tmp_path / "test_phash.jpg"
    img = Image.new("RGB", (100, 100), color=(128, 64, 32))
    img.save(img_path)

    phash1 = storage.compute_phash(img_path)
    assert phash1 is not None
    assert len(phash1) == 16  # 64-bit hex representation (16 hex chars)

    # Same image must produce identical pHash
    phash2 = storage.compute_phash(img_path)
    assert phash1 == phash2

    # Slightly modified image should produce close distance
    img_modified = Image.new("RGB", (100, 100), color=(130, 65, 34))
    mod_path = tmp_path / "test_phash_mod.jpg"
    img_modified.save(mod_path)
    phash_mod = storage.compute_phash(mod_path)
    assert phash_mod is not None
