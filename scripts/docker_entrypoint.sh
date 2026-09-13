#!/bin/bash
set -Eeuo pipefail

SERVICE="${BRAIN_SERVICE:-api}"
echo "🧠 Personal AI Brain — starting ${SERVICE}..."

if [ "${BRAIN_STRICT_STARTUP:-true}" = "true" ]; then
    python /app/scripts/validate_environment.py "$SERVICE"
fi

DATA_DIR="${BRAIN_DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

# Startup never performs ingestion. Bootstrap services only register jobs;
# the locked knowledge_worker is the sole materialization writer.
exec "$@"
