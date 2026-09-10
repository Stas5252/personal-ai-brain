#!/usr/bin/env python3
"""Index the built-in Markdown knowledge corpus in two authority tiers.

Tier 1 — ``core``
    Editorially reviewed originals. Must be present and well formed; a problem
    here fails startup, because the assistant is useless without its core.

Tier 2 — ``notes``
    Course-derived working notes (files 01–31). Previously these were indexed
    nowhere, which meant 37 of 42 Markdown files were dead weight on disk. They
    are now indexed with a lower-authority tag so retrieval can prefer the core,
    and a malformed note is reported and skipped rather than aborting startup.

Usage
-----
    python scripts/seed_vetted_knowledge.py            # both tiers
    python scripts/seed_vetted_knowledge.py --tier core
    python scripts/seed_vetted_knowledge.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KNOWLEDGE_DIR = ROOT / "src" / "brain" / "knowledge"

#: Editorially reviewed core. Order is the retrieval priority order.
CORE_FILES = (
    "00_verified_core.md",
    "32_photographer_business_os.md",
    "33_visual_production_playbook.md",
    "34_client_experience_and_ethics.md",
    "35_content_and_promotion_playbooks.md",
)

#: Files that are not knowledge and must never be indexed.
EXCLUDED = frozenset({"yaishka_knowledge.md"})

MIN_CORE_CHARS = 1_500
MIN_NOTE_CHARS = 400


def _title_of(path: Path, text: str) -> str:
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    if first.startswith("# "):
        return first.removeprefix("# ").strip()
    return path.stem.replace("_", " ").strip().capitalize()


def core_paths() -> list[Path]:
    """Validate and return the core corpus. Raises when the core is broken."""
    paths = [KNOWLEDGE_DIR / name for name in CORE_FILES]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise RuntimeError(f"Missing core knowledge files: {', '.join(missing)}")
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        if len(text) < MIN_CORE_CHARS or not text.startswith("# "):
            raise RuntimeError(f"Core knowledge file is incomplete: {path.name}")
    return paths


def note_paths() -> list[Path]:
    """Return course-derived notes worth indexing, newest numbering last."""
    core = set(CORE_FILES)
    notes = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if path.name in core or path.name in EXCLUDED:
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if len(text) >= MIN_NOTE_CHARS:
            notes.append(path)
    return notes


def _ingest(paths: list[Path], tier: str, tags: list[str]) -> tuple[int, int, list[str]]:
    from src.brain.knowledge.factory import KnowledgeIngestionFactory
    from src.brain.models.knowledge import KnowledgeLayer

    factory = KnowledgeIngestionFactory(strict_mode=True)
    indexed = chunk_total = 0
    problems: list[str] = []

    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            source, chunks = factory.ingest_file(
                file_path=path,
                title=_title_of(path, text),
                layer=KnowledgeLayer.PROFESSIONAL,
                author="Personal AI Brain editorial core" if tier == "core" else "Курсовые конспекты",
                subcategory=tier,
                tags=tags + [path.stem],
            )
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path.name}: {exc}")
            if tier == "core":
                raise
            print(f"  ✗ {path.name}: {exc}")
            continue
        status = getattr(source.ingestion_status, "value", source.ingestion_status)
        indexed += 1
        chunk_total += len(chunks)
        print(f"  ✓ {path.name}: {status}, chunks={len(chunks)}")

    return indexed, chunk_total, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", choices=("core", "notes", "all"), default="all")
    parser.add_argument("--list", action="store_true", help="list what would be indexed and exit")
    args = parser.parse_args(argv)

    core = core_paths()
    notes = note_paths()

    if args.list:
        print(f"core ({len(core)}):")
        for path in core:
            print(f"  {path.name}")
        print(f"notes ({len(notes)}):")
        for path in notes:
            print(f"  {path.name}")
        return 0

    total_sources = total_chunks = 0

    if args.tier in ("core", "all"):
        print(f"📚 Core knowledge ({len(core)} files):")
        indexed, chunks, _ = _ingest(core, "core", ["verified_core", "photographer_business"])
        total_sources += indexed
        total_chunks += chunks

    if args.tier in ("notes", "all"):
        print(f"🗂️  Course notes ({len(notes)} files):")
        indexed, chunks, problems = _ingest(notes, "notes", ["course_notes", "secondary_authority"])
        total_sources += indexed
        total_chunks += chunks
        if problems:
            print(f"⚠️  Skipped {len(problems)} note(s); core remains authoritative.")

    print(f"✅ Knowledge ready: {total_sources} sources, {total_chunks} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
