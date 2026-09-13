# 🧠 Personal AI Brain

Self-hosted ИИ-напарник фотографа на Gemini: контент, съёмки, продажи, продвижение, CRM, память, Telegram и Web UI.

> **Один репозиторий — один продукт. Актуальная версия всегда в `master`.** Старые `feature/*` и `fix/*` — уже завершённая история разработки, а не отдельные проекты.

## Что реализовано

- 32 guided-функции Telegram в четырёх разделах: контент, продажи, съёмки и продвижение.
- Пошаговый ввод: кнопка запускает конкретный сценарий и запрашивает недостающие данные.
- Текст, голосовые и изображения; Vision честно сообщает о недоступности провайдера.
- Ответы опираются на собственные материалы владельца, а ссылка на урок рендерится из фактического поиска, а не из прозы модели.
- Профиль фотографа, память, проекты, задачи и CRM.
- Контент-планы, Reels, Stories, прайсы, переписки, возражения, мудборды, аудит профиля, стратегия продвижения и план дня.
- FastAPI, OpenAI-compatible API и Open WebUI.
- Гибридный поиск: ChromaDB + SQLite FTS5 с трассировкой источников.
- Owner-only Telegram и API-аутентификация.

## База знаний: что индексируется на самом деле

Production-развёртывание индексирует три слоя, и все три — свои:

1. **Редакционно проверенное ядро** (`scripts/seed_vetted_knowledge.py`): правила достоверности и работы с фактами; операционная система фотобизнеса, CRM, цены и метрики; визуальное продюсирование, свет, композиция, позирование и обработка; клиентский сервис, договоры, возражения, переносы и приватность; Reels, Stories, посты, рассылки, коллаборации и продвижение.
2. **Конспекты курса** — Markdown-материалы по продажам и возражениям, ценообразованию, контент-маркетингу, личному бренду, сторис и хайлайтам, клиентскому сервису, психологии, монетизации, аудитории и организации фотодня. Они входят в тот же production-seed: маркер `.kb_seeded_v4` был поднят именно ради этого слоя.
3. **Курсовой корпус PDF** (`материалы для ии`, ~680 МБ слайдов с OCR) — `scripts/ingest_course_corpus.py`. Запускается в фоне при старте API: OCR не успевает за время старта контейнера, поэтому API отвечает сразу из Markdown-слоёв, а корпус догружается. Прогон идемпотентный и возобновляемый, перезапуск на середине безопасен. Отключается `BRAIN_INGEST_CORPUS=false`, путь задаётся `BRAIN_CORPUS_DIR`.

Пользовательские документы добавляются отдельно через `/знания` или API.

Готовность базы видна не по логам, а по эндпоинту:

```bash
curl -H "Authorization: Bearer $BRAIN_API_KEY" localhost:8000/health/knowledge
```

`complete: true` и `corpus_files_settled: 57` означают, что корпус дошёл до конца. Пока их нет — ответы опираются только на Markdown-слои, и это видно в `statuses`/`failures`.

## Ответы опираются на материалы, а не на память модели

Все вызовы модели проходят через один слой grounding (`src/brain/services/knowledge_grounding.py`), поэтому материалы доступны всем движкам и всем 32 guided-функциям, а не только свободному чату.

Строку «📚 Источники: …» пишет система из фактически найденных фрагментов, а не модель: придуманная моделью ссылка удаляется, а если не нашлось ничего — ссылки нет вовсе. JSON-контракты движков строку не получают. Те же названия приходят в ответе API полем `sources`.

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `BRAIN_GROUNDING_ENABLED` | `true` | Подмешивать материалы владельца в каждый запрос |
| `BRAIN_GROUNDING_TOP_K` | `5` | Сколько фрагментов искать |
| `BRAIN_GROUNDING_MAX_CHARS` | `2400` | Бюджет выдержек на один запрос |
| `BRAIN_SOURCES_IN_ANSWER` | `true` | Добавлять строку источников в текстовые ответы |
| `BRAIN_LAYER_STRICT` | `false` | Жёстко фильтровать поиск по слою знаний вместо предпочтения |

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

Первый старт считается завершённым не когда контейнеры поднялись, а когда `/health/knowledge` показывает `complete: true`. См. `docs/LIVE_RELEASE_CHECKLIST.md`.

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
src/brain/knowledge/    Ядро, конспекты курса, индексация и поиск
src/brain/services/     BrainService, grounding и guided actions
scripts/                Startup validation, production seed, оценка ответов
tests/                  Reliability и acceptance-наборы
docs/                   Архитектура, ветки и live checklist
```

## Проверки

```bash
python -m compileall -q src scripts tests
python scripts/validate_environment.py api
python scripts/eval_knowledge_answers.py --min-pass 0.7 --verbose
pytest -q tests/reliability tests/brain/test_guided_actions.py
```

`eval_knowledge_answers.py` задаёт 21 вопрос так, как их печатает владелец («клиент говорит что дорого, что ему ответить»), и проверяет, какой урок приходит первым. Режим по умолчанию не требует БД, эмбеддингов и сети, поэтому идёт в CI на каждом пуше; `--engine` прогоняет тот же набор через настоящий поиск по проиндексированному корпусу.

CI дополнительно проверяет Compose, Ruff и продуктовые acceptance-сценарии.

## Статус каналов

- Brain API — implemented.
- Telegram — implemented; реальная доставка требует токена и live checklist.
- Open WebUI — implemented.
- MAX — experimental до появления полноценного transport runner.

См. `docs/REPOSITORY_STRUCTURE.md`, `docs/YAISHKA_PARITY_PLUS_PLAN.md` и `docs/LIVE_RELEASE_CHECKLIST.md`.
