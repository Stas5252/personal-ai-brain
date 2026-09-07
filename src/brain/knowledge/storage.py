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
                pixels = list(img.tobytes())
                avg = sum(pixels) / len(pixels)
                bits = "".join("1" if p > avg else "0" for p in pixels)
                # Convert 64 bits to 16 hex digits
                return f"{int(bits, 2):016x}"
        except Exception:
            return None

    # Alias for test compatibility
    compute_phash = compute_image_phash

    @staticmethod
    def validate_magic_bytes(file_path: Path, ext: str) -> Tuple[bool, Optional[str]]:
        """Validates file magic signature bytes against declared extension and rejects malicious payloads."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(512)
        except Exception as e:
            return False, f"Cannot read file header: {str(e)}"

        if not header:
            return False, "File is empty (0 bytes)."

        # Reject executable / binary payloads disguised as documents
        if header.startswith(b"MZ") or header.startswith(b"\x7fELF") or header.startswith(b"\xca\xfe\xba\xbe"):
            return False, "Dangerous executable payload disguised as document/media."

        ext_lower = ext.lower()
        if ext_lower == ".pdf":
            if not header.startswith(b"%PDF"):
                return False, "Invalid PDF magic bytes header (expected '%PDF')."
        elif ext_lower == ".png":
            if not header.startswith(b"\x89PNG\r\n\x1a\n"):
                return False, "Invalid PNG magic bytes header."
        elif ext_lower in [".jpg", ".jpeg"]:
            if not header.startswith(b"\xff\xd8\xff"):
                return False, "Invalid JPEG magic bytes header."
        elif ext_lower == ".webp":
            if not (header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"):
                return False, "Invalid WEBP magic bytes header."
        elif ext_lower in [".tiff", ".tif"]:
            if not (header.startswith(b"II*\x00") or header.startswith(b"MM\x00*")):
                return False, "Invalid TIFF magic bytes header."
        elif ext_lower in [".docx", ".pptx", ".xlsx"]:
            if not header.startswith(b"PK\x03\x04"):
                return False, f"Invalid Office document archive magic bytes (expected ZIP PK header for {ext})."
        elif ext_lower == ".wav":
            if not (header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE"):
                return False, "Invalid WAV magic bytes header."
        elif ext_lower == ".ogg":
            if not header.startswith(b"OggS"):
                return False, "Invalid OGG magic bytes header."
        elif ext_lower == ".flac":
            if not header.startswith(b"fLaC"):
                return False, "Invalid FLAC magic bytes header."
        elif ext_lower in [".mp4", ".mov", ".mkv", ".webm"]:
            if ext_lower in [".mp4", ".mov"] and b"ftyp" not in header[:64] and not header.startswith(b"\x00\x00\x00"):
                return False, "Invalid MP4/MOV container magic bytes."
            elif ext_lower in [".mkv", ".webm"] and not header.startswith(b"\x1a\x45\xdf\xa3"):
                return False, "Invalid Matroska/WebM container magic bytes."
        elif ext_lower in [".txt", ".md", ".html", ".htm"]:
            if b"\x00" in header:
                return False, f"Binary null bytes detected in text file ({ext})."

        return True, None

    def validate_file(self, file_path: Path, original_filename: Optional[str] = None) -> FileValidationResult:
        """Validates file existence, size, extension, magic signature bytes, and safe path."""
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

        # Check for in-progress downloads or incomplete files
        name_lower = (original_filename or p.name).lower()
        for marker in [".crdownload", ".part", ".tmp", ".downloading", ".incomplete"]:
            if name_lower.endswith(marker):
                return FileValidationResult(
                    is_valid=False,
                    error_message=f"File is currently downloading or incomplete ({marker})."
                )

        # Handle active file leasing or exclusive locks from downloading processes
        try:
            with open(p, "rb") as f_check:
                f_check.read(1024)
        except PermissionError as pe:
            return FileValidationResult(
                is_valid=False,
                error_message=f"File is currently locked by another process (in-progress download or lease): {pe}"
            )
        except OSError as oe:
            return FileValidationResult(
                is_valid=False,
                error_message=f"File access failed (possibly active download write): {oe}"
            )

        file_size = p.stat().st_size
        if file_size <= 0:
            return FileValidationResult(is_valid=False, error_message="File is empty (0 bytes).")

        if file_size > self.max_file_size_bytes:
            return FileValidationResult(
                is_valid=False,
                error_message=f"File size ({file_size} bytes) exceeds maximum allowed size ({self.max_file_size_bytes} bytes)."
            )

        # Magic bytes signature validation
        magic_ok, magic_err = self.validate_magic_bytes(p, ext)
        if not magic_ok:
            return FileValidationResult(is_valid=False, error_message=f"File validation failed: {magic_err}")

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

    def check_duplicate(self, sha256: str, exclude_source_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Checks if a completed source with identical SHA-256 already exists in database."""
        conn = get_connection()
        c = conn.cursor()
        if exclude_source_id:
            c.execute("""
            SELECT * FROM knowledge_sources
            WHERE sha256 = ? AND ingestion_status IN ('COMPLETED', 'DUPLICATE') AND source_id != ?
            """, (sha256, exclude_source_id))
        else:
            c.execute("""
            SELECT * FROM knowledge_sources
            WHERE sha256 = ? AND ingestion_status IN ('COMPLETED', 'DUPLICATE')
            """, (sha256,))
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
            try:
                os.link(file_path, dest_path)
            except Exception:
                shutil.copy2(file_path, dest_path)

        # Copy any companion sidecar files (.json) from source directory
        stem = file_path.stem
        for sc in file_path.parent.glob(f"{stem}*.json"):
            dest_sc = prefix_dir / sc.name
            try:
                if not dest_sc.exists():
                    try:
                        os.link(sc, dest_sc)
                    except Exception:
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

    def is_safe_storage_path(self, target_path: Path, base_dir: Optional[Path] = None) -> bool:
        """Verifies that target_path strictly resolves within STORAGE_DIR/DATA_DIR and not outside."""
        return is_safe_storage_path(target_path, base_dir or self.originals_dir.parent)

def is_safe_storage_path(target_path: Path, base_dir: Optional[Path] = None) -> bool:
    """Verifies that target_path strictly resolves within base_dir (or DATA_DIR) and not outside."""
    try:
        resolved = Path(target_path).resolve()
        if base_dir is None:
            from src.brain.config import DATA_DIR
            base_dir = Path(DATA_DIR).resolve()
        else:
            base_dir = Path(base_dir).resolve()
        return base_dir in resolved.parents or resolved == base_dir
    except Exception:
        return False

def validate_magic_bytes(file_path: Path, ext: str) -> Tuple[bool, Optional[str]]:
    """Module-level helper for magic bytes validation."""
    return StorageManager.validate_magic_bytes(file_path, ext)

