# 🧠 Personal AI Brain

Self-hosted ИИ-напарник фотографа на Gemini: контент, съёмки, продажи, продвижение, CRM, память, Telegram и Web UI.

> **Один репозиторий — один продукт. Актуальная версия всегда в `master`.** Старые `feature/*` и `fix/*` — уже завершённая история разработки, а не отдельные проекты.

## Что реализовано

- 32 guided-функции Telegram в четырёх разделах: контент, продажи, съёмки и продвижение.
- Пошаговый ввод: кнопка запускает конкретный сценарий и запрашивает недостающие данные.
- Текст, голосовые и изображения; Vision честно сообщает о недоступности провайдера.
- Профиль фотографа, память, проекты, задачи и CRM.
- Контент-планы, Reels, Stories, прайсы, переписки, возражения, мудборды, аудит профиля, стратегия продвижения и план дня.
- FastAPI, OpenAI-compatible API и Open WebUI.
- Гибридный поиск: ChromaDB + SQLite FTS5 с трассировкой источников.
- Owner-only Telegram и API-аутентификация.

## Проверенное ядро знаний

Production-развёртывание индексирует только собственное редакционно проверенное ядро:

1. правила достоверности и работы с фактами;
2. операционная система фотобизнеса, CRM, цены и метрики;
3. визуальное продюсирование, свет, композиция, позирование и обработка;
4. клиентский сервис, договоры, возражения, переносы и приватность;
5. Reels, Stories, посты, рассылки, коллаборации и продвижение.

Список задаётся в `scripts/seed_vetted_knowledge.py`. Старые учебные конспекты сохранены только как исторические материалы и не входят в production-seed. Пользовательские документы добавляются отдельно через `/знания` или API.

## Быстрый запуск

```bash
git clone https://github.com/Stas5252/personal-ai-brain.git
cd personal-ai-brain
cp .env.example .env
```

Сгенерируйте разные секреты:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Заполните в `.env` как минимум:

```env
GEMINI_API_KEY=
BRAIN_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_ID=
WEBUI_SECRET_KEY=
```

Запуск и проверка:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Порты по умолчанию доступны только на `127.0.0.1`. Для публичного доступа используйте TLS reverse proxy и firewall.

## Команды Telegram

| Команда | Действие |
|---|---|
| `/start` | Запуск и онбординг |
| `/profile` | Профиль |
| `/brief` | Обновление профиля |
| `/library` | Библиотека запросов |
| `/uroki` | Мини-уроки |
| `/capabilities` | Каталог guided-функций |
| `/знания` | Добавление пользовательского материала |
| `/cancel` | Отмена текущего мастера |
| `/reset` | Сброс профиля |

## Структура

```text
src/brain/api/          FastAPI и OpenAI-compatible API
src/brain/channels/     Telegram, Web и экспериментальный MAX
src/brain/engines/      Контент, продажи, съёмки, продвижение, память
src/brain/knowledge/    Проверенное ядро и legacy-материалы
src/brain/services/     BrainService и guided actions
scripts/                Startup validation и production seed
tests/                  Reliability и acceptance-наборы
docs/                   Архитектура, ветки и live checklist
```

## Проверки

```bash
python -m compileall -q src scripts tests
python scripts/validate_environment.py api
pytest -q tests/reliability tests/brain/test_guided_actions.py
```

CI дополнительно проверяет Compose, Ruff и продуктовые acceptance-сценарии.

## Статус каналов

- Brain API — implemented.
- Telegram — implemented; реальная доставка требует токена и live checklist.
- Open WebUI — implemented.
- MAX — experimental до появления полноценного transport runner.

См. `docs/REPOSITORY_STRUCTURE.md`, `docs/YAISHKA_PARITY_PLUS_PLAN.md` и `docs/LIVE_RELEASE_CHECKLIST.md`.
