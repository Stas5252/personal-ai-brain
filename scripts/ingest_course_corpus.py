#!/usr/bin/env python3
"""Index the repository course corpus («материалы для ии») into the brain.

Why this script exists
----------------------
The course PDFs shipped in the repository are the substantive knowledge of this
assistant. They could not be indexed before, for two concrete reasons:

1. Nothing ever read that folder. ``seed_vetted_knowledge.py`` only indexed five
   hand-written Markdown files, so every course PDF was dead weight.
2. Six of the files are larger than ``MAX_FILE_SIZE_BYTES`` (20 MB), the ceiling
   that protects the public upload API. ``StorageManager.validate_file`` rejects
   anything above it, so those files could never be ingested at all.

This script fixes both. It walks the repository-local corpus with a separate,
higher ceiling (``CORPUS_MAX_FILE_SIZE_BYTES``) because that content is trusted
and version controlled, and it routes every file to a knowledge topic so
retrieval can be filtered later.

Operational properties
----------------------
* **Idempotent** — progress lives in a JSON ledger, and the ingestion factory
  deduplicates by SHA-256, so re-running never duplicates chunks.
* **Resumable** — interrupt at any point; settled files are skipped next run.
* **Fault isolated** — one unreadable PDF never aborts the run.
* **Observable** — ``--report`` prints per-file status, topic and chunk counts.

Usage
-----
    python scripts/ingest_course_corpus.py               # ingest everything pending
    python scripts/ingest_course_corpus.py --dry-run     # plan only, no writes
    python scripts/ingest_course_corpus.py --limit 5     # ingest the next 5 files
    python scripts/ingest_course_corpus.py --only возраж  # filter by filename
    python scripts/ingest_course_corpus.py --report       # show current state
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.brain.knowledge.corpus import (  # noqa: E402
    CORPUS_DIR_NAME,
    TOPIC_LABELS,
    CorpusLedger,
    classify_topic,
    clean_title,
    iter_corpus_files,
    slugify,
)

log = logging.getLogger("corpus")


def _human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _resolve_paths():
    """Import config lazily so ``--help`` works without a configured environment."""
    from src.brain.config import CORPUS_DIR, CORPUS_MAX_FILE_SIZE_BYTES, DATA_DIR

    return Path(CORPUS_DIR), Path(DATA_DIR) / ".corpus_ledger.json", CORPUS_MAX_FILE_SIZE_BYTES


def _build_factory(size_ceiling: int):
    """Build an ingestion factory whose storage accepts large trusted corpus files.

    ``MAX_FILE_SIZE_BYTES`` deliberately stays small for the upload API; raising
    it globally would widen the attack surface of an internet-facing endpoint.
    Instead we raise the ceiling only on this in-process StorageManager.
    """
    from src.brain.knowledge.extractors.document_extractor import DocumentExtractor
    from src.brain.knowledge.factory import KnowledgeIngestionFactory
    from src.brain.knowledge.storage import StorageManager

    storage = StorageManager()
    storage.max_file_size_bytes = max(storage.max_file_size_bytes, int(size_ceiling))

    # Slide exports are image-heavy, so OCR must run when a page has no text
    # layer, but skipping OCR on text pages keeps a 57-file run tractable.
    extractor = DocumentExtractor(strict_pages=False, skip_ocr_if_has_text=True)
    return KnowledgeIngestionFactory(
        storage_manager=storage,
        document_extractor=extractor,
        strict_mode=False,
    )


def report(ledger: CorpusLedger, corpus_dir: Path) -> int:
    files = list(iter_corpus_files(corpus_dir))
    print(f"Корпус: {corpus_dir}")
    print(f"Файлов на диске: {len(files)}")
    counts = ledger.counts()
    if not counts:
        print("Статус: ничего ещё не индексировано.")
        return 0
    print("Статусы: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"Всего фрагментов (chunks): {ledger.total_chunks()}")
    topics = ledger.topic_counts()
    if topics:
        print("\nПо темам:")
        for topic, count in topics.items():
            print(f"  {TOPIC_LABELS.get(topic, topic):<26} {count}")
    failures = ledger.failures()
    if failures:
        print(f"\nНе удалось обработать ({len(failures)}):")
        for entry in failures:
            print(f"  {entry.name}: {entry.error}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list planned work without writing")
    parser.add_argument("--force", action="store_true", help="re-ingest files already marked settled")
    parser.add_argument("--limit", type=int, default=0, help="stop after N files (0 = no limit)")
    parser.add_argument("--only", default="", help="only files whose name contains this substring")
    parser.add_argument("--report", action="store_true", help="print current ledger state and exit")
    parser.add_argument("--corpus-dir", default="", help="override the corpus directory")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    default_dir, ledger_path, size_ceiling = _resolve_paths()
    corpus_dir = Path(args.corpus_dir).expanduser().resolve() if args.corpus_dir else default_dir
    ledger = CorpusLedger(ledger_path)

    if args.report:
        return report(ledger, corpus_dir)

    if not corpus_dir.is_dir():
        log.error("Корпус не найден: %s (ожидалась папка %r в корне репозитория)", corpus_dir, CORPUS_DIR_NAME)
        return 2

    candidates = list(iter_corpus_files(corpus_dir))
    if args.only:
        needle = args.only.casefold()
        candidates = [p for p in candidates if needle in p.name.casefold()]

    pending = [p for p in candidates if args.force or not ledger.should_skip(p)]
    if args.limit > 0:
        pending = pending[: args.limit]

    total_bytes = sum(p.stat().st_size for p in pending)
    log.info(
        "Найдено %d файлов, к обработке %d (%s). Лимит размера: %s",
        len(candidates), len(pending), _human_size(total_bytes), _human_size(size_ceiling),
    )

    if args.dry_run:
        for path in pending:
            topic = classify_topic(path.name)
            print(f"{_human_size(path.stat().st_size):>9}  {topic:<10}  {clean_title(path.name)}")
        print(f"\nИтого к индексации: {len(pending)} файлов, {_human_size(total_bytes)}")
        return 0

    if not pending:
        log.info("Всё актуально — индексировать нечего.")
        return 0

    from src.brain.models.knowledge import KnowledgeLayer

    factory = _build_factory(size_ceiling)

    indexed = duplicates = failed = 0
    started = time.monotonic()

    for position, path in enumerate(pending, start=1):
        topic = classify_topic(path.name)
        title = clean_title(path.name)
        log.info("[%d/%d] %s (%s, %s)", position, len(pending), title, topic, _human_size(path.stat().st_size))
        try:
            source, chunks = factory.ingest_file(
                file_path=path,
                title=title,
                layer=KnowledgeLayer.PROFESSIONAL,
                author="Курсовые материалы владельца",
                subcategory=topic,
                tags=["course_corpus", topic, slugify(path.name)],
                force=args.force,
            )
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            failed += 1
            log.warning("  ✗ %s: %s", path.name, exc)
            ledger.record(path, "failed", error=str(exc)[:500])
            ledger.save()
            continue

        status = getattr(source.ingestion_status, "value", str(source.ingestion_status))
        if status.upper() == "DUPLICATE":
            duplicates += 1
            log.info("  = уже в базе (дубликат по SHA-256)")
            ledger.record(path, "duplicate", sha256=source.sha256, source_id=source.source_id, chunks=len(chunks))
        else:
            indexed += 1
            log.info("  ✓ проиндексировано, фрагментов: %d", len(chunks))
            ledger.record(path, "indexed", sha256=source.sha256, source_id=source.source_id, chunks=len(chunks))
        ledger.save()

    elapsed = time.monotonic() - started
    log.info(
        "Готово за %.1f мин: проиндексировано %d, дубликатов %d, ошибок %d, фрагментов всего %d",
        elapsed / 60, indexed, duplicates, failed, ledger.total_chunks(),
    )

    # A partially indexed corpus is still useful, so failures do not fail the
    # run unless nothing at all could be indexed.
    if indexed == 0 and duplicates == 0 and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
