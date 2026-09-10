#!/usr/bin/env python3
"""Index only the reviewed, original built-in knowledge corpus.

User uploads still use the regular ingestion API. This script is intentionally
separate so legacy/course-derived drafts cannot silently become authoritative
production knowledge on a fresh deployment.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "src" / "brain" / "knowledge"
VETTED_FILES = (
    "00_verified_core.md",
    "32_photographer_business_os.md",
    "33_visual_production_playbook.md",
    "34_client_experience_and_ethics.md",
    "35_content_and_promotion_playbooks.md",
)


def validate_corpus() -> list[Path]:
    paths = [KNOWLEDGE_DIR / name for name in VETTED_FILES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing vetted knowledge files: {', '.join(missing)}")
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        if len(text) < 1_500 or not text.startswith("# "):
            raise RuntimeError(f"Knowledge file is incomplete: {path.name}")
    return paths


def main() -> int:
    from src.brain.knowledge.factory import KnowledgeIngestionFactory
    from src.brain.models.knowledge import KnowledgeLayer

    factory = KnowledgeIngestionFactory(strict_mode=True)
    paths = validate_corpus()
    for path in paths:
        title = path.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ").strip()
        source, chunks = factory.ingest_file(
            file_path=path,
            title=title,
            layer=KnowledgeLayer.PROFESSIONAL,
            author="Personal AI Brain editorial core",
            tags=["verified_core", "photographer_business", path.stem],
        )
        status = getattr(source.ingestion_status, "value", source.ingestion_status)
        print(f"{path.name}: {status}, chunks={len(chunks)}")
    print(f"Vetted knowledge core ready: {len(paths)} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
