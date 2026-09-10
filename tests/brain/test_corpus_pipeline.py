"""Regression tests for the course-corpus knowledge pipeline.

These tests intentionally cover the parts that actually broke:

* the 20 MB upload ceiling silently rejected six of the shipped course PDFs;
* browser-downloaded ``name (1).pdf`` copies would have been OCR'd twice;
* nothing routed corpus files to a topic, so retrieval could not be filtered;
* the API had no request ceiling at all.

They use only the standard library plus pytest, so they run in CI without
ChromaDB, ONNX or any extractor being importable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.brain.api.ratelimit import RateLimiter, client_key
from src.brain.knowledge.corpus import (
    CORPUS_DIR_NAME,
    TOPIC_LABELS,
    CorpusLedger,
    classify_topic,
    clean_title,
    drop_numbered_duplicates,
    iter_corpus_files,
    slugify,
)

#: The largest file actually shipped in the corpus, in bytes.
LARGEST_CORPUS_FILE = 36_807_319


# --------------------------------------------------------------------------
# Topic routing
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        # Straightforward cases
        ("ТОП-25 возражений.pdf", "sales"),
        ("ТОП_идей_для_сторис_на_каждый_день.pdf", "content"),
        ("Урок_2_Платные_и_бесплатные_методы_продвижения.pdf", "promotion"),
        ("Урок_9_WOW_Сервис_в_работе_фотографа.pdf", "clients"),
        ("Урок 1. Антикризисное мышление.pdf", "mindset"),
        ("Типы личного бренда.pptx.pdf", "branding"),
        ("ОБУЧЕНИЕ ДЛЯ CHATGPT.pdf", "tools"),
        ("30 проф промтов.pdf", "tools"),
        # Ambiguous names where an override must win over a keyword rule
        ("Урок_2_Как_организовать_фотодень,_который_точно_продастся_.pdf", "business"),
        ("Урок_1_Где_взять_клиентов,_которые_запустят_сарафанное_радио.pdf", "promotion"),
        ("Чек_лист_по_базовому_оформлению_профиля.pdf", "branding"),
        ("Что закреплять в Hightlights.pptx.pdf", "content"),
        ("Урок_3_Как_продавать_разным_категориям_клиентов.pdf", "sales"),
        ("Урок_3_Контент,_который_продает_за_вас.pdf", "content"),
        ("Урок 1. Как создать проект.pdf", "business"),
        ("Шаблоны для продающих постов.pdf", "content"),
        # Nothing matches -> general, never a crash
        ("Секрет.pdf", "tools"),
        ("zzz-unknown-file.pdf", "general"),
    ],
)
def test_classify_topic(filename: str, expected: str) -> None:
    assert classify_topic(filename) == expected


def test_every_topic_has_a_human_label() -> None:
    names = [
        "ТОП-25 возражений.pdf",
        "Урок 1. Антикризисное мышление.pdf",
        "zzz-unknown-file.pdf",
    ]
    for name in names:
        assert classify_topic(name) in TOPIC_LABELS


# --------------------------------------------------------------------------
# Title and slug normalisation
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Урок_2_Наши_клиенты_кто_они_pptx.pdf", "Урок 2 Наши клиенты кто они"),
        ("Типы личного бренда.pptx.pdf", "Типы личного бренда"),
        ("Топ приложений (1).pdf", "Топ приложений"),
        ("шпаргалка.pdf", "Шпаргалка"),
    ],
)
def test_clean_title(filename: str, expected: str) -> None:
    assert clean_title(filename) == expected


def test_slugify_is_stable_and_bounded() -> None:
    slug = slugify("Урок_3_Как_писать_посты,_которые_увеличат_выручку_в_2_раза.pdf")
    assert slug == slugify("Урок_3_Как_писать_посты,_которые_увеличат_выручку_в_2_раза.pdf")
    assert 0 < len(slug) <= 80
    assert " " not in slug


# --------------------------------------------------------------------------
# Duplicate handling and discovery
# --------------------------------------------------------------------------

def test_identical_numbered_copy_is_dropped(tmp_path: Path) -> None:
    original = tmp_path / "Топ приложений.pdf"
    copy = tmp_path / "Топ приложений (1).pdf"
    original.write_bytes(b"same-bytes")
    copy.write_bytes(b"same-bytes")

    kept = drop_numbered_duplicates([original, copy])

    assert kept == [original]


def test_differing_numbered_copy_is_kept(tmp_path: Path) -> None:
    original = tmp_path / "Урок 2.pdf"
    copy = tmp_path / "Урок 2 (1).pdf"
    original.write_bytes(b"short")
    copy.write_bytes(b"a genuinely different revision")

    kept = drop_numbered_duplicates([original, copy])

    assert set(kept) == {original, copy}


def test_iter_corpus_files_filters_unsupported(tmp_path: Path) -> None:
    (tmp_path / "lesson.pdf").write_bytes(b"pdf")
    (tmp_path / "notes.md").write_text("notes", encoding="utf-8")
    (tmp_path / "cover.jpg").write_bytes(b"jpg")
    (tmp_path / ".hidden.pdf").write_bytes(b"pdf")
    (tmp_path / "archive.zip").write_bytes(b"zip")

    names = sorted(p.name for p in iter_corpus_files(tmp_path))

    assert names == ["lesson.pdf", "notes.md"]


def test_iter_corpus_files_on_missing_dir_is_empty(tmp_path: Path) -> None:
    assert list(iter_corpus_files(tmp_path / "nope")) == []


# --------------------------------------------------------------------------
# Ledger: idempotency and resumability
# --------------------------------------------------------------------------

def test_ledger_roundtrip_and_skip(tmp_path: Path) -> None:
    pdf = tmp_path / "Урок 1 Цена и ценность.pdf"
    pdf.write_bytes(b"x" * 128)
    ledger_path = tmp_path / "ledger.json"

    ledger = CorpusLedger(ledger_path)
    assert ledger.should_skip(pdf) is False

    ledger.record(pdf, "indexed", sha256="abc", source_id="sid", chunks=12)
    ledger.save()

    reloaded = CorpusLedger(ledger_path)
    assert reloaded.should_skip(pdf) is True
    assert reloaded.total_chunks() == 12
    assert reloaded.counts() == {"indexed": 1}
    assert reloaded.topic_counts() == {"sales": 1}
    assert reloaded.entries[pdf.name].title == "Урок 1 Цена и ценность"


def test_ledger_reprocesses_changed_file(tmp_path: Path) -> None:
    pdf = tmp_path / "lesson.pdf"
    pdf.write_bytes(b"x" * 100)
    ledger = CorpusLedger(tmp_path / "ledger.json")
    ledger.record(pdf, "indexed", chunks=3)

    pdf.write_bytes(b"x" * 200)  # file replaced with a new revision

    assert ledger.should_skip(pdf) is False


def test_ledger_failure_is_retried_and_reported(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"x")
    ledger = CorpusLedger(tmp_path / "ledger.json")
    ledger.record(pdf, "failed", error="Extraction failed")

    assert ledger.should_skip(pdf) is False
    assert [e.name for e in ledger.failures()] == ["broken.pdf"]


def test_ledger_survives_corrupt_file(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text("{not json", encoding="utf-8")

    ledger = CorpusLedger(ledger_path)

    assert ledger.entries == {}


def test_ledger_is_written_atomically(tmp_path: Path) -> None:
    pdf = tmp_path / "lesson.pdf"
    pdf.write_bytes(b"x")
    ledger_path = tmp_path / "nested" / "ledger.json"

    ledger = CorpusLedger(ledger_path)
    ledger.record(pdf, "indexed", chunks=1)
    ledger.save()

    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert payload["version"] == CorpusLedger.VERSION
    assert "lesson.pdf" in payload["entries"]
    assert not list(ledger_path.parent.glob("*.tmp"))


# --------------------------------------------------------------------------
# The actual production blocker: the size ceiling
# --------------------------------------------------------------------------

def test_corpus_ceiling_admits_the_largest_shipped_pdf() -> None:
    """Six shipped PDFs exceed the 20 MB upload ceiling.

    Before this change ``StorageManager.validate_file`` rejected them outright,
    so those lessons could never enter the knowledge base.
    """
    from src.brain.config import CORPUS_MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_BYTES

    assert CORPUS_MAX_FILE_SIZE_BYTES > MAX_FILE_SIZE_BYTES
    assert CORPUS_MAX_FILE_SIZE_BYTES >= LARGEST_CORPUS_FILE


def test_corpus_dir_points_at_the_shipped_folder() -> None:
    from src.brain.config import CORPUS_DIR

    assert Path(CORPUS_DIR).name == CORPUS_DIR_NAME


# --------------------------------------------------------------------------
# API rate limiting
# --------------------------------------------------------------------------

def test_rate_limiter_allows_burst_then_rejects() -> None:
    limiter = RateLimiter(capacity=3, window_seconds=60)

    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, True]

    allowed, retry_after = limiter.check("a")
    assert allowed is False
    assert retry_after >= 1


def test_rate_limiter_isolates_callers() -> None:
    limiter = RateLimiter(capacity=1, window_seconds=60)

    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is False
    assert limiter.check("b")[0] is True


def test_rate_limiter_refills_over_time() -> None:
    limiter = RateLimiter(capacity=2, window_seconds=2)
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is False

    # Rewind the bucket instead of sleeping, so the test stays fast.
    limiter._buckets["a"].updated_at -= 2.0

    assert limiter.check("a")[0] is True


def test_rate_limiter_rejects_bad_configuration() -> None:
    with pytest.raises(ValueError):
        RateLimiter(capacity=0, window_seconds=60)
    with pytest.raises(ValueError):
        RateLimiter(capacity=1, window_seconds=0)


def test_client_key_never_contains_the_secret() -> None:
    secret = "Bearer super-secret-token"

    key = client_key(secret, None, "127.0.0.1")

    assert secret not in key
    assert "super-secret-token" not in key
    assert key.startswith("key:")
    assert key == client_key(secret, None, "10.0.0.9"), "key identity must not depend on IP"


def test_client_key_falls_back_to_ip() -> None:
    assert client_key(None, None, "127.0.0.1") == "ip:127.0.0.1"
    assert client_key(None, None, None) == "ip:unknown"
