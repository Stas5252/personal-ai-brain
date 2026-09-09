#!/bin/bash
# Personal AI Brain — Docker Entrypoint
# Автоматически индексирует KB-файлы при первом запуске.
set -e

echo "🧠 Personal AI Brain — Starting..."

# Индексация KB только один раз (маркер-файл)
SEED_MARKER="/app/data/.kb_seeded_v1"

if [ ! -f "$SEED_MARKER" ]; then
    echo "📚 Индексирую базу знаний..."
    python import_knowledge.py /app/src/brain/knowledge/ --skip-videos 2>&1 | tail -30 || true
    touch "$SEED_MARKER"
    echo "✅ База знаний проиндексирована!"
else
    echo "⏭️  База знаний уже актуальна, пропускаю."
fi

# Запускаем переданную команду (uvicorn или telegram_runner)
exec "$@"
