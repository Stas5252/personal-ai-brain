@echo off
chcp 65001 > nul
echo ==========================================================
echo        PERSONAL AI BRAIN - TELEGRAM ASSISTANT
echo ==========================================================

if not exist .env (
    echo [!] ОШИБКА: Файл .env не найден!
    echo [!] Скопируйте .env.example в .env и укажите ваши ключи:
    echo     - GEMINI_API_KEY
    echo     - TELEGRAM_BOT_TOKEN
    echo     - TELEGRAM_OWNER_ID
    echo     - BRAIN_API_KEY
    echo.
    pause
    exit /b 1
)

echo [*] Запуск персонального AI-ассистента в Telegram...
python -m src.brain.channels.telegram_production_ingestion
pause
