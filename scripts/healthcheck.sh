#!/usr/bin/env bash
# Personal AI Brain — Health Check Script
# Usage: bash scripts/healthcheck.sh
# Returns exit code 0 if all services OK, 1 if any service is down.

set -euo pipefail

BRAIN_URL="${BRAIN_URL:-http://localhost:8000}"
WEBUI_URL="${WEBUI_URL:-http://localhost:8080}"
BRAIN_API_KEY="${BRAIN_API_KEY:-brain-secure-stage5-federation-key-2026}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}🔍 Personal AI Brain — Health Check${NC}"
echo -e "${BLUE}======================================${NC}"
echo -e "Timestamp: $(date '+%d.%m.%Y %H:%M:%S')"
echo ""

failed=0

check_url() {
    local name="$1"
    local url="$2"
    local grep_for="${3:-}"
    local extra_headers="${4:-}"

    local cmd="curl -sf --max-time 5"
    if [ -n "$extra_headers" ]; then
        cmd="$cmd -H '$extra_headers'"
    fi
    cmd="$cmd '$url'"

    local response
    response=$(eval $cmd 2>/dev/null || echo "FAILED")

    if [ "$response" = "FAILED" ]; then
        echo -e "${RED}❌ $name${NC} — not responding ($url)"
        return 1
    fi

    if [ -n "$grep_for" ] && ! echo "$response" | grep -q "$grep_for" 2>/dev/null; then
        echo -e "${RED}❌ $name${NC} — unexpected response (expected: $grep_for)"
        return 1
    fi

    echo -e "${GREEN}✅ $name${NC}"
    return 0
}

check_url "Brain API /health" "$BRAIN_URL/health" "ok" || failed=$((failed+1))
check_url "Brain API /v1/models" "$BRAIN_URL/v1/models" "personal-ai-brain" \
    "Authorization: Bearer $BRAIN_API_KEY" || failed=$((failed+1))
check_url "Open WebUI" "$WEBUI_URL" "" || failed=$((failed+1))

if pgrep -f 'telegram_runner' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Telegram runner — process running${NC}"
else
    echo -e "${YELLOW}⚠️  Telegram runner — not running${NC}"
    echo -e "   Start with: python -m src.brain.channels.telegram_runner"
fi

DATA_DIR="${BRAIN_DATA_DIR:-data}"
for dir in "$DATA_DIR" "$DATA_DIR/uploads" "$DATA_DIR/.derived"; do
    if [ -d "$dir" ]; then
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        echo -e "${GREEN}✅ Directory: $dir${NC} ($size)"
    else
        echo -e "${RED}❌ Missing directory: $dir${NC}"
        failed=$((failed+1))
    fi
done

DB_PATH="${BRAIN_DB_PATH:-${DATA_DIR}/brain.db}"
if [ -f "$DB_PATH" ]; then
    db_size=$(du -sh "$DB_PATH" 2>/dev/null | cut -f1)
    echo -e "${GREEN}✅ Brain DB${NC} — $DB_PATH ($db_size)"
else
    echo -e "${YELLOW}⚠️  Brain DB not found: $DB_PATH (will be created on first run)${NC}"
fi

echo ""
echo "==========================================="
if [ $failed -eq 0 ]; then
    echo -e "${GREEN}🎉 All checks passed! Bot is ready.${NC}"
else
    echo -e "${RED}❌ $failed check(s) failed. Review errors above.${NC}"
    exit 1
fi
