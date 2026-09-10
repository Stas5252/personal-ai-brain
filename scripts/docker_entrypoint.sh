#!/bin/bash
set -Eeuo pipefail

SERVICE="${BRAIN_SERVICE:-api}"
echo "🧠 Personal AI Brain — starting ${SERVICE}..."

if [ "${BRAIN_STRICT_STARTUP:-true}" = "true" ]; then
    python /app/scripts/validate_environment.py "$SERVICE"
fi

DATA_DIR="${BRAIN_DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

# Marker is versioned: bumping it re-runs seeding once after a knowledge change.
# v4 adds the course-notes tier, which earlier versions never indexed.
SEED_MARKER="${DATA_DIR}/.kb_seeded_v4"
if [ "$SERVICE" = "api" ] && [ ! -f "$SEED_MARKER" ]; then
    echo "📚 Indexing built-in Markdown knowledge (core + course notes)..."
    if python /app/scripts/seed_vetted_knowledge.py; then
        touch "$SEED_MARKER"
        echo "✅ Markdown knowledge indexed."
    else
        echo "❌ Knowledge indexing failed; refusing partial startup." >&2
        exit 1
    fi
fi

# The course corpus is ~680 MB of slide exports that need OCR, which takes far
# longer than a container start is allowed to. So it runs in the background: the
# API answers immediately from the Markdown core while the corpus fills in.
# The run is resumable and idempotent, so restarting mid-way is safe.
if [ "$SERVICE" = "api" ] && [ "${BRAIN_INGEST_CORPUS:-true}" = "true" ]; then
    CORPUS_DIR_PATH="${BRAIN_CORPUS_DIR:-/app/материалы для ии}"
    CORPUS_LOG="${DATA_DIR}/corpus_ingest.log"
    if [ -d "$CORPUS_DIR_PATH" ]; then
        echo "🗂  Course corpus ingestion running in background → ${CORPUS_LOG}"
        nohup python /app/scripts/ingest_course_corpus.py >>"$CORPUS_LOG" 2>&1 &
        echo $! >"${DATA_DIR}/corpus_ingest.pid"
    else
        echo "ℹ️  Course corpus folder not found at '${CORPUS_DIR_PATH}'; skipping."
    fi
fi

exec "$@"
