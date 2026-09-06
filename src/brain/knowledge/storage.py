"""
Storage and Deduplication Manager for Knowledge Ingestion Factory.
Handles file validation, SHA-256 deduplication, perceptual hashing for images,
and organized original / derived storage.
"""
import os
import re
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from PIL import Image

from src.brain.config import (
    ORIGINALS_DIR, DERIVED_DIR, MAX_FILE_SIZE_BYTES,
    ALLOWED_EXTENSIONS, ALLOWED_DOCUMENT_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS, ALLOWED_AUDIO_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS
)
from src.brain.models.file_metadata import FileValidationResult
from src.brain.db import get_connection

MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}

class StorageManager:
    def __init__(self, originals_dir: Path = ORIGINALS_DIR, derived_dir: Path = DERIVED_DIR):
        self.originals_dir = Path(originals_dir)
        self.derived_dir = Path(derived_dir)
        self.max_file_size_bytes = MAX_FILE_SIZE_BYTES
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Strips path traversal components and unsafe characters."""
        base_name = os.path.basename(filename).strip()
        # Remove any path separators
        base_name = re.sub(r"[\\/]", "", base_name)
        # Allow alphanumeric, cyrillic, underscores, dots, hyphens, and spaces
        safe_name = re.sub(r"[^\w\s.-]", "_", base_name, flags=re.UNICODE).strip()
        if not safe_name or safe_name in [".", ".."]:
            safe_name = "unnamed_source"
        return safe_name

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Calculates SHA-256 hash of file contents in chunks."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def compute_image_phash(file_path: Path) -> Optional[str]:
        """Calculates 64-bit perceptual average hash for image deduplication."""
        try:
            with Image.open(file_path) as img:
                img = img.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
                pixels = list(img.getdata())
                avg = sum(pixels) / len(pixels)
                bits = "".join("1" if p > avg else "0" for p in pixels)
                # Convert 64 bits to 16 hex digits
                return f"{int(bits, 2):016x}"
        except Exception:
            return None

    # Alias for test compatibility
    compute_phash = compute_image_phash

    def validate_file(self, file_path: Path, original_filename: Optional[str] = None) -> FileValidationResult:
        """Validates file existence, size, extension, and safe path."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return FileValidationResult(is_valid=False, error_message=f"File not found: {p}")

        orig_name = original_filename or p.name
        safe_name = self.sanitize_filename(orig_name)
        ext = os.path.splitext(safe_name)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            return FileValidationResult(
                is_valid=False,
                error_message=f"Unsupported file extension '{ext}'. Allowed: {sorted(list(ALLOWED_EXTENSIONS))}"
            )

        file_size = p.stat().st_size
        if file_size <= 0:
            return FileValidationResult(is_valid=False, error_message="File is empty (0 bytes).")

        if file_size > self.max_file_size_bytes:
            return FileValidationResult(
                is_valid=False,
                error_message=f"File size ({file_size} bytes) exceeds maximum allowed size ({self.max_file_size_bytes} bytes)."
            )

        sha256 = self.compute_sha256(p)
        mime_type = MIME_MAP.get(ext, "application/octet-stream")

        p_hash = None
        if ext in ALLOWED_IMAGE_EXTENSIONS:
            p_hash = self.compute_image_phash(p)

        return FileValidationResult(
            is_valid=True,
            mime_type=mime_type,
            extension=ext,
            file_size=file_size,
            sha256=sha256,
            p_hash=p_hash,
            safe_filename=safe_name
        )

    def check_duplicate(self, sha256: str) -> Optional[Dict[str, Any]]:
        """Checks if a source with identical SHA-256 already exists in database."""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM knowledge_sources WHERE sha256 = ?", (sha256,))
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def record_duplicate_encounter(self, source_id: str):
        """Increments seen_count for an existing duplicate source."""
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE knowledge_sources SET seen_count = seen_count + 1 WHERE source_id = ?", (source_id,))
        conn.commit()
        conn.close()

    def store_original(self, file_path: Path, sha256: str, safe_name: str) -> Path:
        """Stores immutable copy of original file under structured sha256 directory."""
        prefix_dir = self.originals_dir / sha256[:2] / sha256[2:4]
        prefix_dir.mkdir(parents=True, exist_ok=True)
        dest_path = prefix_dir / f"{sha256}_{safe_name}"

        if not dest_path.exists():
            shutil.copy2(file_path, dest_path)

        # Copy any companion sidecar files (.json) from source directory
        stem = file_path.stem
        for sc in file_path.parent.glob(f"{stem}*.json"):
            dest_sc = prefix_dir / sc.name
            try:
                shutil.copy2(sc, dest_sc)
            except Exception:
                pass

        return dest_path

    def get_derived_dir(self, source_id: str) -> Path:
        """Returns dedicated directory for extracted keyframes, transcripts, and temporary artifacts."""
        d = self.derived_dir / source_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def delete_source_files(self, source_id: str):
        """Cleans up derived directory for the given source."""
        d = self.derived_dir / source_id
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
