#!/bin/bash
set -Eeuo pipefail

SERVICE="${BRAIN_SERVICE:-api}"
echo "🧠 Personal AI Brain — starting ${SERVICE}..."

if [ "${BRAIN_STRICT_STARTUP:-true}" = "true" ]; then
    python /app/scripts/validate_environment.py "$SERVICE"
fi

SEED_MARKER="/app/data/.kb_seeded_v2"
if [ "$SERVICE" = "api" ] && [ ! -f "$SEED_MARKER" ]; then
    echo "📚 Indexing bundled knowledge base..."
    if python import_knowledge.py /app/src/brain/knowledge/ --skip-videos; then
        touch "$SEED_MARKER"
        echo "✅ Knowledge base indexed."
    else
        echo "❌ Knowledge indexing failed; refusing partial startup." >&2
        exit 1
    fi
fi

exec "$@"
