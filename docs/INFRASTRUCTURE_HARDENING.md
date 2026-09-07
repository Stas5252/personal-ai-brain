# Infrastructure Hardening Architecture & Reference

This document describes the architectural improvements, security hardening, and worker infrastructure implemented in Stage 5 of the Personal AI Brain project.

---

## 1. Job Leasing State Machine & Worker Architecture

### 1.1 Concurrency & Distributed Leasing Model
To prevent race conditions, duplicate processing, and worker conflicts, the ingestion queue uses an atomic database-level leasing model with heartbeat renewals:

- **Atomic Claiming**: \IngestionQueue.claim_job(worker_id, lease_seconds)\ selects the highest priority queued job and transitions it to \PROCESSING\ with \worker_id\ and \lease_until = now() + lease_seconds\ in an immediate SQLite transaction.
- **Heartbeat Daemon**: Active workers spawn an asynchronous background thread executing \heartbeat(job_id, worker_id, extend_seconds)\ every interval (default: lease_duration / 2) to maintain active ownership.
- **Stale Job Reclamation**: If a worker crashes or loses network connectivity, its lease expires. The eclaim_stale_jobs(stale_threshold_seconds)\ routine detects expired leases where \lease_until < now()\, resets the job status to \QUEUED\, increments \ttempt_count\, and makes it available for peer workers.
- **Exponential Backoff & Max Retries**: Failed jobs undergo exponential retry backoff (\BASE_BACKOFF_SECONDS * 2^(attempt - 1)\). Jobs exceeding \MAX_INGESTION_RETRIES\ (default: 3) transition to \FAILED\ with detailed diagnostic error logs.
- **Graceful Shutdown**: The worker daemon captures \SIGINT\ and \SIGTERM\. When a termination signal is received, the worker finishes its in-flight chunk or checkpoint, safely releases claimed jobs back to \QUEUED\ without incrementing penalty counts, and exits cleanly.

### 1.2 Worker Daemon CLI
The ingestion worker is executable as a standalone background daemon:
\\ash
# Run standalone daemon with default settings (1 worker, 30s lease)
python -m src.brain.knowledge.queue.worker

# Run with custom lease duration, poll interval, and single-pass flag
python -m src.brain.knowledge.queue.worker --worker-id worker-alpha --lease 45 --interval 1.0 --once
\
---

## 2. Security Hardening & Safe Ingestion

### 2.1 Magic Bytes & Binary Validation
File extension validation alone is insufficient to prevent malicious payload uploads. The storage pipeline implements binary magic bytes inspection via \StorageManager.validate_file()\:

- **Executable Blocking**: Automatically rejects MS-DOS/PE executables (\MZ\ header) and Linux ELF binaries (\ELF\), even if renamed to \.jpg\ or \.pdf\.
- **MIME Header Verification**: Enforces valid magic byte signatures for all allowed media formats:
  - PDF: \%PDF-  - JPEG: \ÿ\xd8\xff  - PNG: \PNG\r\n\x1a\n  - RIFF/WAV: \RIFF....WAVE  - ZIP-based Office Open XML (DOCX, PPTX, XLSX): \PK\x03\x04- **Zero-Byte & Oversized Rejection**: Immediately rejects 0-byte empty files and files exceeding \MAX_FILE_SIZE_BYTES\ (100 MB).

### 2.2 Canonical Path Traversal Protection
Path traversal vulnerabilities (\../../etc/passwd\) are blocked at the storage layer:
- \StorageManager.is_safe_storage_path(base_dir, target_path)\ resolves canonical paths using \Path.resolve()\ and asserts that the canonical target resides strictly within the designated storage root.
- All stored files are renamed using their SHA-256 hash prefix and sanitized safe filenames (\sanitize_filename()\).

### 2.3 Elimination of \eval()All instances of dynamic evaluation (\eval()\) were purged from the knowledge pipeline. Metadata parsing, job checkpoints, and serialized JSON fields now strictly use standard \json.loads()\. Codebase integrity is enforced by an AST-level regression test in \	ests/knowledge/test_hardened_security.py\.

### 2.4 Mandatory Authentication
All Brain endpoints (\/brain/*\, \/knowledge/*\, \/v1/*\) mandate Bearer token authentication via \erify_brain_api_key\ (\src/brain/api/security.py\). Unauthenticated or improperly signed requests receive an immediate \HTTP 401 Unauthorized\. Constant-time comparison (\hmac.compare_digest\) prevents timing attacks.

---

## 3. Multimodal Extraction & Local OCR Pipeline

### 3.1 Real On-Device OCR Engine
Previously simulated heuristics have been replaced by a real, local ONNX runtime pipeline:
- \OCREngine\ (\src/brain/knowledge/extractors/ocr_engine.py\): Wraps \RapidOCR\ using apidocr-onnxruntime\. Performs local optical character recognition on scanned PDFs and images without transmitting user documents to third-party cloud APIs.
- Scanned PDF Fallback: \DocumentExtractor\ identifies pages with zero extractable text elements, renders them to high-resolution pixmaps, and executes \OCREngine\ to extract text and tables.
- Image OCR: \ImageExtractor\ processes raster images (JPG, PNG) with \OCREngine\, returning extracted text and bounding coordinates.

### 3.2 Vision Provider Contract
To prevent hallucinations and false certainty:
- \VisionProvider\ (\src/brain/knowledge/extractors/vision_provider.py\) defines an explicit contract for multimodal image description. When external vision models are unconfigured, it returns \VisionStatus.NOT_IMPLEMENTED\ with an honest fallback message rather than generating fictitious descriptions.

---

## 4. Strict Context Budget Enforcement

### 4.1 Token Quotas & Hard Truncation
\ContextEngine\ enforces hard character quotas across all 6 context sections to prevent prompt buffer overflow and context dilution:
- Section budgets (\BUDGET_QUOTAS\):
  - System Policy: 15%
  - User Profile: 15%
  - Project Context: 20%
  - Client Context: 15%
  - Relevant Memories: 15%
  - Knowledge Base: 20%
- Total prompt context is strictly bounded by \MAX_CONTEXT_CHARS\ (default: 16,000 characters).
- When a section exceeds its quota, it is deterministically truncated at word boundaries with an explicit truncation notice (\[...truncated to fit context budget quota...]\).
