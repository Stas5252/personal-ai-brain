#!/usr/bin/env bash
# Personal AI Brain — production health check
# Usage: BRAIN_API_KEY='<configured key>' bash scripts/healthcheck.sh

set -euo pipefail

BRAIN_URL="${BRAIN_URL:-http://localhost:8000}"
WEBUI_URL="${WEBUI_URL:-http://localhost:8080}"
: "${BRAIN_API_KEY:?Set BRAIN_API_KEY to the configured API key}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
failed=0

echo
echo -e "${BLUE}Personal AI Brain — health check${NC}"
echo -e "${BLUE}================================${NC}"
echo "Timestamp: $(date '+%d.%m.%Y %H:%M:%S')"
echo

check_url() {
    local name="$1"
    local url="$2"
    local expected="$3"
    local authenticated="${4:-false}"
    local -a curl_args=(--fail --silent --show-error --max-time 5)
    if [[ "$authenticated" == "true" ]]; then
        curl_args+=(--header "Authorization: Bearer ${BRAIN_API_KEY}")
    fi
    local response
    if ! response="$(curl "${curl_args[@]}" "$url" 2>/dev/null)"; then
        echo -e "${RED}FAILED $name${NC} — not responding ($url)"
        return 1
    fi
    if [[ -n "$expected" ]] && ! grep -Fq "$expected" <<<"$response"; then
        echo -e "${RED}FAILED $name${NC} — unexpected response (expected: $expected)"
        return 1
    fi
    echo -e "${GREEN}OK $name${NC}"
}

check_url "Brain API liveness" "$BRAIN_URL/health/live" '"status":"alive"' || failed=$((failed + 1))
check_url "Brain API readiness" "$BRAIN_URL/health/ready" '"status":"ready"' true || failed=$((failed + 1))
check_url "Brain API models" "$BRAIN_URL/v1/models" "personal-ai-brain" true || failed=$((failed + 1))
check_url "Open WebUI" "$WEBUI_URL" "" || failed=$((failed + 1))

if pgrep -f 'telegram_production_ingestion' >/dev/null 2>&1; then
    echo -e "${GREEN}OK Telegram runner — process running${NC}"
else
    echo -e "${YELLOW}WARN Telegram runner — process not visible on this host${NC}"
fi

DATA_DIR="${BRAIN_DATA_DIR:-data}"
for dir in "$DATA_DIR" "$DATA_DIR/uploads" "$DATA_DIR/storage" "$DATA_DIR/vector_db"; do
    if [[ -d "$dir" ]]; then
        size="$(du -sh "$dir" 2>/dev/null | cut -f1)"
        echo -e "${GREEN}OK Directory: $dir${NC} ($size)"
    else
        echo -e "${RED}FAILED Missing directory: $dir${NC}"
        failed=$((failed + 1))
    fi
done

DB_PATH="${BRAIN_DB_PATH:-${DATA_DIR}/brain.db}"
if [[ -f "$DB_PATH" ]]; then
    db_size="$(du -sh "$DB_PATH" 2>/dev/null | cut -f1)"
    echo -e "${GREEN}OK Brain DB${NC} — $DB_PATH ($db_size)"
else
    echo -e "${RED}FAILED Brain DB not found: $DB_PATH${NC}"
    failed=$((failed + 1))
fi

echo
if (( failed == 0 )); then
    echo -e "${GREEN}All checks passed; service is ready.${NC}"
else
    echo -e "${RED}${failed} check(s) failed.${NC}"
    exit 1
fi
