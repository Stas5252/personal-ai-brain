#!/usr/bin/env python3
"""Register repository course-corpus files for worker-only ingestion."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.brain.knowledge.corpus import CORPUS_DIR_NAME, classify_topic, clean_title, iter_corpus_files, slugify

log = logging.getLogger("corpus")


def _paths():
    from src.brain.config import CORPUS_DIR, CORPUS_MAX_FILE_SIZE_BYTES
    return Path(CORPUS_DIR), CORPUS_MAX_FILE_SIZE_BYTES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--corpus-dir", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    default_dir, ceiling = _paths()
    corpus_dir = Path(args.corpus_dir).expanduser().resolve() if args.corpus_dir else default_dir
    if not corpus_dir.is_dir():
        log.error("Корпус не найден: %s (ожидалась папка %r)", corpus_dir, CORPUS_DIR_NAME)
        return 2
    files = list(iter_corpus_files(corpus_dir))
    if args.only:
        files = [path for path in files if args.only.casefold() in path.name.casefold()]
    if args.limit > 0:
        files = files[:args.limit]
    if args.report or args.dry_run:
        for path in files:
            print(f"{classify_topic(path.name):<12} {clean_title(path.name)}")
        print(f"files={len(files)} mode={'report' if args.report else 'dry-run'}")
        return 0

    from src.brain.knowledge.registration import IngestionRegistrar
    from src.brain.knowledge.storage import StorageManager
    from src.brain.models.knowledge import KnowledgeLayer
    storage = StorageManager()
    storage.max_file_size_bytes = max(storage.max_file_size_bytes, int(ceiling))
    registrar = IngestionRegistrar(storage)
    queued = duplicates = failed = 0
    for index, path in enumerate(files, 1):
        topic = classify_topic(path.name)
        try:
            result = registrar.register_file(
                path, original_filename=path.name, title=clean_title(path.name),
                layer=KnowledgeLayer.PROFESSIONAL, author="Курсовые материалы владельца",
                subcategory=topic, tags=["course_corpus", topic, slugify(path.name)],
                priority=5, force=args.force,
                metadata={"bootstrap": True, "course_corpus": True, "corpus_name": path.name},
            )
            duplicates += int(result.duplicate)
            queued += int(not result.duplicate)
            log.info("[%d/%d] %s: %s", index, len(files), path.name, result.job.status.value)
        except Exception as exc:
            failed += 1
            log.warning("[%d/%d] %s: %s", index, len(files), path.name, exc)
    log.info("Registered: queued=%d existing=%d failed=%d", queued, duplicates, failed)
    return 1 if failed and not (queued or duplicates) else 0


if __name__ == "__main__":
    raise SystemExit(main())
