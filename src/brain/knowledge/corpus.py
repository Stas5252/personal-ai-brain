"""Repository course corpus: discovery, topic routing and an ingest ledger.

This module is deliberately dependency-free (standard library only) so the
corpus contract can be unit tested without ChromaDB, FastAPI, or any extractor
being installed. All heavy lifting lives in ``scripts/ingest_course_corpus.py``.

The corpus is the substantive knowledge of this assistant: PDF exports of the
photography-business course materials that ship in the repository under
``материалы для ии/``.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

#: Folder name, relative to the repository root, that holds the source corpus.
CORPUS_DIR_NAME = "материалы для ии"

#: Extensions the document extractor can actually read.
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".html"})

TOPIC_GENERAL = "general"

#: Human labels used in bot output and status reports.
TOPIC_LABELS = {
    "content": "Контент и соцсети",
    "sales": "Продажи и возражения",
    "promotion": "Продвижение",
    "clients": "Клиенты и сервис",
    "mindset": "Психология и деньги",
    "branding": "Личный бренд и упаковка",
    "business": "Бизнес и продукты",
    "tools": "Инструменты и ПО",
    TOPIC_GENERAL: "Общее",
}

# Distinctive tokens win over the ordered keyword rules below, because several
# filenames legitimately contain words from two topics (for example
# "Как организовать фотодень, который точно продастся").
_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("фотодень", "business"),
    ("линейк", "business"),
    ("создать проект", "business"),
    ("монетиз", "business"),
    ("сарафан", "promotion"),
    ("лидер", "promotion"),
    ("chatgpt", "tools"),
    ("промт", "tools"),
    ("промпт", "tools"),
    ("приложен", "tools"),
    ("шпаргалк", "tools"),
    ("wow", "clients"),
    ("рассылк", "clients"),
    ("клиентской базой", "clients"),
    ("hightlights", "content"),
    ("highlights", "content"),
    ("антикризис", "mindset"),
    ("психолог", "mindset"),
    ("риск", "mindset"),
    ("доход", "mindset"),
    ("распаковк", "branding"),
    ("упаковк", "branding"),
    ("бренд", "branding"),
    ("профил", "branding"),
)

# Checked in order; the first topic with a matching stem wins.
_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "content",
        (
            "сторис", "stories", "reels", "рилс", "пост", "контент", "заголовк",
            "триггер", "хук", "текст", "telegram", "канал", "шаблон",
        ),
    ),
    (
        "sales",
        (
            "прода", "возражен", "дорого", "убедить", "купить", "цена",
            "ценност", "ценообразован", "прайс", "оффер", "скидк", "маркер",
        ),
    ),
    ("promotion", ("продвижен", "трафик", "коллаб", "мнени", "метод")),
    ("clients", ("клиент", "сервис", "база", "базой", "чат", "поведен", "категори")),
    ("mindset", ("мышлен", "деньг", "прогноз", "экологичн", "минимизац")),
    ("branding", ("позиционирован", "блог", "личност")),
    ("business", ("проект", "товарн", "обуча", "обучен", "кейс")),
    ("tools", ("инструмент", "секрет")),
)

_NUMBERED_COPY = re.compile(r"\s*\((\d+)\)$")
_PSEUDO_EXT = re.compile(r"[._](pptx|docx|pdf|ppt|doc)$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def classify_topic(name: str) -> str:
    """Route a corpus filename to one knowledge topic.

    Routing is filename-based on purpose: it is deterministic, auditable and
    costs nothing, unlike classifying 680 MB of slide scans with an LLM.
    """
    haystack = name.casefold()
    for token, topic in _OVERRIDES:
        if token in haystack:
            return topic
    for topic, stems in _TOPIC_RULES:
        if any(stem in haystack for stem in stems):
            return topic
    return TOPIC_GENERAL


def clean_title(name: str) -> str:
    """Turn ``Урок_2_Наши_клиенты_pptx.pdf`` into ``Урок 2 Наши клиенты``."""
    stem = Path(name).stem
    stem = _NUMBERED_COPY.sub("", stem)
    stem = _PSEUDO_EXT.sub("", stem)
    stem = stem.replace("_", " ").replace("  ", " ")
    stem = _WHITESPACE.sub(" ", stem).strip(" .-–—")
    if not stem:
        return "Без названия"
    return stem[0].upper() + stem[1:]


def slugify(name: str) -> str:
    """Stable ASCII-safe tag derived from a filename."""
    stem = Path(name).stem.casefold()
    slug = re.sub(r"[^\w]+", "-", stem, flags=re.UNICODE).strip("-")
    return slug[:80] or "source"


def drop_numbered_duplicates(paths: Iterable[Path]) -> list[Path]:
    """Drop ``name (1).pdf`` when ``name.pdf`` exists with an identical size.

    Browser downloads of the same lesson produced byte-identical copies. The
    factory would deduplicate them by SHA-256 anyway, but skipping them here
    avoids paying for OCR twice.
    """
    by_name = {p.name: p for p in paths}
    kept: list[Path] = []
    for path in sorted(by_name.values(), key=lambda p: p.name):
        match = _NUMBERED_COPY.search(path.stem)
        if not match:
            kept.append(path)
            continue
        original_name = _NUMBERED_COPY.sub("", path.stem) + path.suffix
        original = by_name.get(original_name)
        if original is None:
            kept.append(path)
            continue
        try:
            if original.stat().st_size != path.stat().st_size:
                kept.append(path)
        except OSError:
            kept.append(path)
    return kept


def iter_corpus_files(corpus_dir: Path) -> Iterator[Path]:
    """Yield ingestable corpus files in a stable order."""
    root = Path(corpus_dir)
    if not root.is_dir():
        return
    candidates = [
        item
        for item in sorted(root.rglob("*"))
        if item.is_file()
        and not item.name.startswith(".")
        and item.suffix.casefold() in SUPPORTED_SUFFIXES
    ]
    yield from drop_numbered_duplicates(candidates)


@dataclass
class LedgerEntry:
    """One corpus file's ingestion outcome."""

    name: str
    title: str
    topic: str
    status: str = "pending"
    size: int = 0
    sha256: str | None = None
    source_id: str | None = None
    chunks: int = 0
    error: str | None = None
    updated_at: str | None = None

    @property
    def is_settled(self) -> bool:
        return self.status in {"indexed", "duplicate", "skipped"}


class CorpusLedger:
    """Durable, human-readable record of corpus ingestion progress.

    Ingesting ~680 MB of scanned slides takes far longer than a container
    start, so the run must be resumable and observable. The ledger is plain
    JSON on the data volume; deleting it forces a full re-check (the factory
    still deduplicates by content hash, so no chunk is ever duplicated).
    """

    VERSION = 1

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, LedgerEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("version") != self.VERSION:
            return
        for name, raw in (payload.get("entries") or {}).items():
            known = {f: raw.get(f) for f in LedgerEntry.__dataclass_fields__ if f in raw}
            known.setdefault("name", name)
            known.setdefault("title", clean_title(name))
            known.setdefault("topic", classify_topic(name))
            try:
                self.entries[name] = LedgerEntry(**known)
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": {name: asdict(entry) for name, entry in sorted(self.entries.items())},
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def should_skip(self, path: Path) -> bool:
        """True when this exact file was already settled at the same size."""
        entry = self.entries.get(path.name)
        if entry is None or not entry.is_settled:
            return False
        try:
            return entry.size == path.stat().st_size
        except OSError:
            return False

    def record(self, path: Path, status: str, **fields: object) -> LedgerEntry:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        entry = LedgerEntry(
            name=path.name,
            title=clean_title(path.name),
            topic=classify_topic(path.name),
            status=status,
            size=size,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        for key, value in fields.items():
            if key in LedgerEntry.__dataclass_fields__:
                setattr(entry, key, value)
        self.entries[path.name] = entry
        return entry

    def counts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for entry in self.entries.values():
            totals[entry.status] = totals.get(entry.status, 0) + 1
        return dict(sorted(totals.items()))

    def topic_counts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for entry in self.entries.values():
            if entry.status in {"indexed", "duplicate"}:
                totals[entry.topic] = totals.get(entry.topic, 0) + 1
        return dict(sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])))

    def total_chunks(self) -> int:
        return sum(entry.chunks for entry in self.entries.values())

    def failures(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.status == "failed"]
