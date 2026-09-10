#!/bin/bash
set -Eeuo pipefail

SERVICE="${BRAIN_SERVICE:-api}"
echo "🧠 Personal AI Brain — starting ${SERVICE}..."

if [ "${BRAIN_STRICT_STARTUP:-true}" = "true" ]; then
    python /app/scripts/validate_environment.py "$SERVICE"
fi

SEED_MARKER="/app/data/.kb_seeded_v3"
if [ "$SERVICE" = "api" ] && [ ! -f "$SEED_MARKER" ]; then
    echo "📚 Indexing vetted original knowledge core..."
    if python /app/scripts/seed_vetted_knowledge.py; then
        touch "$SEED_MARKER"
        echo "✅ Vetted knowledge core indexed."
    else
        echo "❌ Knowledge indexing failed; refusing partial startup." >&2
        exit 1
    fi
fi

exec "$@"
