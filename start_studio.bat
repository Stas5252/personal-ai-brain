@echo off
chcp 65001 > nul
echo ==========================================================
echo        PERSONAL AI BRAIN - PHOTOGRAPHER WORK STUDIO
echo ==========================================================
echo [*] Запуск персонального AI-мозга фотографа...
echo [*] Открытие браузера: http://localhost:8000
start http://localhost:8000
python -m uvicorn src.brain.api.app:app --host 0.0.0.0 --port 8000
pause
