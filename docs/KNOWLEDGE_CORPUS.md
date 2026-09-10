# Course corpus — how the knowledge base is actually built

This document describes what is indexed, how, and how to verify it. If a claim
here is not checkable with a command, it does not belong in this file.

## What exists

| Tier | Source | Count | Indexed by |
|---|---|---|---|
| Verified core | `00_verified_core.md` plus 4 curated playbooks | 5 files | `scripts/seed_vetted_knowledge.py --tier core` |
| Course notes | remaining `src/brain/knowledge/*.md` | ~36 files | `scripts/seed_vetted_knowledge.py --tier notes` |
| Course corpus | `материалы для ии/*.pdf` | 57 PDFs (~680 MB) | `scripts/ingest_course_corpus.py` |

Before this pipeline existed only the 5 core files reached the vector store.
The 57 PDFs and 36 of the Markdown files were dead weight in the repository.

## Why the corpus needs its own size ceiling

`MAX_FILE_SIZE_BYTES` (20 MB) guards the HTTP upload endpoint, which is
reachable by anyone holding the API key. Six shipped lesson PDFs are larger
than that, so `StorageManager.validate_file` rejected them outright:

| File | Size |
|---|---|
| `Урок_6_Экстренная_минимизация_рисков_pptx.pdf` | 36.8 MB |
| `Чек_лист_по_базовому_оформлению_профиля.pdf` | 36.1 MB |
| `Урок_3_Контент,_который_продает_за_вас.pdf` | 29.9 MB |
| `ТОП_идей_для_сторис_на_каждый_день.pdf` | 23.0 MB |
| `Урок_3_Психология_больших_денег_pptx.pdf` | 20.7 MB |
| `ТФ_11_0_Как_убедить_купить_у_вас_сейчас,_а_не_потом.pdf` | 20.3 MB |

The corpus is version-controlled content the owner added deliberately, so it
gets `CORPUS_MAX_FILE_SIZE_BYTES` (64 MB by default) while the upload ceiling
stays small. The ingester raises the limit only on its own `StorageManager`
instance, so the API ceiling is never widened at runtime.

## Topic routing

Every corpus file is classified by filename into one of nine topics:
`content`, `sales`, `promotion`, `clients`, `mindset`, `branding`, `business`,
`tools`, `general`. The topic becomes the chunk `subcategory` and a tag, so
retrieval can be filtered instead of relying on embedding luck alone.

Classification is deliberately filename-based: it runs before extraction, so a
file that later fails OCR is still correctly attributed in the ledger.

## Running it

```bash
# See what would happen, without touching the database
python scripts/ingest_course_corpus.py --dry-run

# Index everything (resumable; safe to re-run)
python scripts/ingest_course_corpus.py

# Index one topic, or a few files, while testing
python scripts/ingest_course_corpus.py --only sales --limit 3

# Show current state without indexing anything
python scripts/ingest_course_corpus.py --report
```

In Docker this runs automatically in the background on first API start, because
OCR over 680 MB takes far longer than a container is allowed to spend starting.
Progress goes to `data/corpus_ingest.log`. Set `BRAIN_INGEST_CORPUS=false` to
disable it.

## Idempotency and resumability

`data/.corpus_ledger.json` records, per file: size, SHA-256, topic, status,
chunk count and any error. On the next run a file is skipped only if it is
settled (`indexed` or `duplicate`) **and** its size and hash are unchanged.
Failures are retried automatically. The ledger is written atomically after each
file, so restarting mid-run loses at most one file's work.

Duplicate detection happens twice: browser-style `name (1).pdf` copies with
identical bytes are dropped before extraction, and `KnowledgeIngestionFactory`
deduplicates by SHA-256 against everything already stored.

## Verifying it worked

```bash
# Machine-readable status, including per-topic counts and failures
curl -s -H "Authorization: Bearer $BRAIN_API_KEY" localhost:8000/health/knowledge | jq

# Same information from the CLI
python scripts/ingest_course_corpus.py --report
```

`complete: true` means every supported file on disk reached a settled state.
Anything else lists the failures with their error text — no silent partial
success.

## Known limits

- Extraction quality depends on the source. These PDFs are slide exports, so
  the text layer is used when present and OCR only as a fallback
  (`skip_ocr_if_has_text=True`). Scanned-only slides depend on
  `rapidocr-onnxruntime` being installed.
- A first full run is CPU-bound and takes tens of minutes on a laptop.
- Only the API container ingests. Two ingesters against the same SQLite file
  and Chroma directory would race, so the Telegram container sets
  `BRAIN_INGEST_CORPUS=false`.
