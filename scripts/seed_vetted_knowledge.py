#!/usr/bin/env python3
"""Validate the built-in Markdown corpus and register ingestion jobs only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
KNOWLEDGE_DIR = ROOT / "src" / "brain" / "knowledge"
CORE_FILES = (
    "00_verified_core.md", "32_photographer_business_os.md",
    "33_visual_production_playbook.md", "34_client_experience_and_ethics.md",
    "35_content_and_promotion_playbooks.md",
)
EXCLUDED = frozenset({"yaishka_knowledge.md"})
MIN_CORE_CHARS = 1_500
MIN_NOTE_CHARS = 400


def _title_of(path: Path, text: str) -> str:
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    return first.removeprefix("# ").strip() if first.startswith("# ") else path.stem.replace("_", " ").capitalize()


def core_paths() -> list[Path]:
    paths = [KNOWLEDGE_DIR / name for name in CORE_FILES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing core knowledge files: {', '.join(missing)}")
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        if len(text) < MIN_CORE_CHARS or not text.startswith("# "):
            raise RuntimeError(f"Core knowledge file is incomplete: {path.name}")
    return paths


def note_paths() -> list[Path]:
    core = set(CORE_FILES)
    result = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if path.name in core or path.name in EXCLUDED:
            continue
        try:
            if len(path.read_text(encoding="utf-8").strip()) >= MIN_NOTE_CHARS:
                result.append(path)
        except OSError:
            continue
    return result


def _register(paths: list[Path], tier: str, tags: list[str]) -> tuple[int, int]:
    from src.brain.knowledge.registration import IngestionRegistrar
    from src.brain.models.knowledge import KnowledgeLayer
    registrar = IngestionRegistrar()
    queued = duplicates = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            result = registrar.register_file(
                path, original_filename=path.name, title=_title_of(path, text),
                layer=KnowledgeLayer.PROFESSIONAL,
                author="Personal AI Brain editorial core" if tier == "core" else "Курсовые конспекты",
                subcategory=tier, tags=tags + [path.stem], priority=20 if tier == "core" else 15,
                metadata={"bootstrap": True, "authority_tier": tier},
            )
        except Exception:
            if tier == "core":
                raise
            print(f"  ✗ {path.name}: registration failed")
            continue
        duplicates += int(result.duplicate)
        queued += int(not result.duplicate)
        print(f"  {'=' if result.duplicate else '✓'} {path.name}: {result.job.status.value}, job={result.job.job_id}")
    return queued, duplicates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("core", "notes", "all"), default="all")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    core, notes = core_paths(), note_paths()
    if args.list:
        for tier, paths in (("core", core), ("notes", notes)):
            print(f"{tier} ({len(paths)}):")
            for path in paths:
                print(f"  {path.name}")
        return 0
    queued = duplicates = 0
    if args.tier in ("core", "all"):
        q, d = _register(core, "core", ["verified_core", "photographer_business"]); queued += q; duplicates += d
    if args.tier in ("notes", "all"):
        q, d = _register(notes, "notes", ["course_notes", "secondary_authority"]); queued += q; duplicates += d
    print(f"Knowledge jobs registered: queued={queued}, existing={duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
