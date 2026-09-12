"""Storage, validation, and deduplication for knowledge ingestion."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from src.brain.config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    DERIVED_DIR,
    MAX_FILE_SIZE_BYTES,
    ORIGINALS_DIR,
)
from src.brain.db import get_connection
from src.brain.models.file_metadata import FileValidationResult

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
        """Return a portable basename without traversal or hidden dot-runs."""
        base_name = re.split(r"[\\/]", str(filename or ""))[-1].strip()
        safe_name = re.sub(r"[^\w\s.-]", "_", base_name, flags=re.UNICODE)
        safe_name = re.sub(r"\.{2,}", ".", safe_name)
        safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")
        if not safe_name:
            safe_name = "unnamed_source"
        return safe_name[:240]

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as source:
            while chunk := source.read(65536):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def compute_image_phash(file_path: Path) -> Optional[str]:
        try:
            with Image.open(file_path) as image:
                image = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
                pixels = list(image.tobytes())
                average = sum(pixels) / len(pixels)
                bits = "".join("1" if pixel > average else "0" for pixel in pixels)
                return f"{int(bits, 2):016x}"
        except Exception:
            return None

    compute_phash = compute_image_phash

    @staticmethod
    def validate_magic_bytes(file_path: Path, ext: str) -> Tuple[bool, Optional[str]]:
        try:
            with open(file_path, "rb") as source:
                header = source.read(512)
        except Exception as exc:
            return False, f"Cannot read file header: {exc}"
        if not header:
            return False, "File is empty (0 bytes)."
        if header.startswith((b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe")):
            return False, "Dangerous executable payload disguised as document/media."

        extension = ext.lower()
        if extension == ".pdf" and not header.startswith(b"%PDF"):
            return False, "Invalid PDF magic bytes header (expected '%PDF')."
        if extension == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
            return False, "Invalid PNG magic bytes header."
        if extension in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
            return False, "Invalid JPEG magic bytes header."
        if extension == ".webp" and not (
            header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"
        ):
            return False, "Invalid WEBP magic bytes header."
        if extension in {".tiff", ".tif"} and not (
            header.startswith(b"II*\x00") or header.startswith(b"MM\x00*")
        ):
            return False, "Invalid TIFF magic bytes header."
        if extension in {".docx", ".pptx", ".xlsx"} and not header.startswith(b"PK\x03\x04"):
            return False, f"Invalid Office document archive magic bytes for {extension}."
        if extension == ".wav" and not (
            header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE"
        ):
            return False, "Invalid WAV magic bytes header."
        if extension == ".ogg" and not header.startswith(b"OggS"):
            return False, "Invalid OGG magic bytes header."
        if extension == ".flac" and not header.startswith(b"fLaC"):
            return False, "Invalid FLAC magic bytes header."
        if extension in {".mp4", ".mov"} and b"ftyp" not in header[:64] and not header.startswith(b"\x00\x00\x00"):
            return False, "Invalid MP4/MOV container magic bytes."
        if extension in {".mkv", ".webm"} and not header.startswith(b"\x1a\x45\xdf\xa3"):
            return False, "Invalid Matroska/WebM container magic bytes."
        if extension in {".txt", ".md", ".html", ".htm"} and b"\x00" in header:
            return False, f"Binary null bytes detected in text file ({extension})."
        return True, None

    def validate_file(self, file_path: Path, original_filename: Optional[str] = None) -> FileValidationResult:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return FileValidationResult(is_valid=False, error_message=f"File not found: {path}")
        original_name = original_filename or path.name
        safe_name = self.sanitize_filename(original_name)
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            return FileValidationResult(
                is_valid=False,
                error_message=f"Unsupported file extension '{extension}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
            )
        lowered = original_name.lower()
        for marker in (".crdownload", ".part", ".tmp", ".downloading", ".incomplete"):
            if lowered.endswith(marker):
                return FileValidationResult(
                    is_valid=False,
                    error_message=f"File is currently downloading or incomplete ({marker}).",
                )
        try:
            with open(path, "rb") as source:
                source.read(1024)
        except PermissionError as exc:
            return FileValidationResult(
                is_valid=False, error_message=f"File is locked by another process: {exc}"
            )
        except OSError as exc:
            return FileValidationResult(is_valid=False, error_message=f"File access failed: {exc}")
        size = path.stat().st_size
        if size <= 0:
            return FileValidationResult(is_valid=False, error_message="File is empty (0 bytes).")
        if size > self.max_file_size_bytes:
            return FileValidationResult(
                is_valid=False,
                error_message=(
                    f"File size ({size} bytes) exceeds maximum allowed size "
                    f"({self.max_file_size_bytes} bytes)."
                ),
            )
        valid, error = self.validate_magic_bytes(path, extension)
        if not valid:
            return FileValidationResult(is_valid=False, error_message=f"File validation failed: {error}")
        sha256 = self.compute_sha256(path)
        perceptual_hash = self.compute_image_phash(path) if extension in ALLOWED_IMAGE_EXTENSIONS else None
        return FileValidationResult(
            is_valid=True,
            mime_type=MIME_MAP.get(extension, "application/octet-stream"),
            extension=extension,
            file_size=size,
            sha256=sha256,
            p_hash=perceptual_hash,
            safe_filename=safe_name,
        )

    def check_duplicate(self, sha256: str, exclude_source_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        connection = get_connection()
        try:
            if exclude_source_id:
                row = connection.execute(
                    "SELECT * FROM knowledge_sources WHERE sha256 = ? "
                    "AND ingestion_status IN ('COMPLETED', 'DUPLICATE') AND source_id != ?",
                    (sha256, exclude_source_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM knowledge_sources WHERE sha256 = ? "
                    "AND ingestion_status IN ('COMPLETED', 'DUPLICATE')",
                    (sha256,),
                ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def record_duplicate_encounter(self, source_id: str):
        connection = get_connection()
        try:
            connection.execute(
                "UPDATE knowledge_sources SET seen_count = seen_count + 1 WHERE source_id = ?",
                (source_id,),
            )
            connection.commit()
        finally:
            connection.close()

    def store_original(self, file_path: Path, sha256: str, safe_name: str) -> Path:
        prefix = self.originals_dir / sha256[:2] / sha256[2:4]
        prefix.mkdir(parents=True, exist_ok=True)
        destination = prefix / f"{sha256}_{safe_name}"
        if not destination.exists():
            try:
                os.link(file_path, destination)
            except Exception:
                shutil.copy2(file_path, destination)
        stem = Path(file_path).stem
        for sidecar in Path(file_path).parent.glob(f"{stem}*.json"):
            target = prefix / self.sanitize_filename(sidecar.name)
            try:
                if not target.exists():
                    try:
                        os.link(sidecar, target)
                    except Exception:
                        shutil.copy2(sidecar, target)
            except Exception:
                continue
        return destination

    def get_derived_dir(self, source_id: str) -> Path:
        directory = self.derived_dir / source_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def delete_source_files(self, source_id: str):
        directory = self.derived_dir / source_id
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)

    def is_safe_storage_path(self, target_path: Path, base_dir: Optional[Path] = None) -> bool:
        return is_safe_storage_path(target_path, base_dir or self.originals_dir.parent)


def is_safe_storage_path(target_path: Path, base_dir: Optional[Path] = None) -> bool:
    try:
        resolved = Path(target_path).resolve()
        if base_dir is None:
            from src.brain.config import DATA_DIR

            base = Path(DATA_DIR).resolve()
        else:
            base = Path(base_dir).resolve()
        return resolved == base or base in resolved.parents
    except Exception:
        return False


def validate_magic_bytes(file_path: Path, ext: str) -> Tuple[bool, Optional[str]]:
    return StorageManager.validate_magic_bytes(file_path, ext)
