# Production operations runbook

Этот документ описывает безопасный запуск, наблюдение, резервное копирование, восстановление и откат Personal AI Brain. Он не заменяет live-приёмку из [`LIVE_RELEASE_CHECKLIST.md`](LIVE_RELEASE_CHECKLIST.md).

## Статусы релиза

Используйте только следующие формулировки:

- **Offline verified** — полный набор `pytest -m 'not live'`, lint, Compose config и image build завершились успешно.
- **Staging verified** — контейнеры запущены с отдельными тестовыми данными, health/readiness и smoke-сценарии пройдены.
- **Production ready** — дополнительно завершены все live-проверки Gemini, Vision и Telegram из чек-листа.
- **Degraded** — сервис запущен, но readiness, провайдер модели, индекс знаний или доставка Telegram не готовы.

Mock-тесты и placeholder-секреты не подтверждают `Production ready`.

## Подготовка

1. Создайте `.env` из `.env.example`.
2. Сгенерируйте разные случайные значения для `BRAIN_API_KEY` и `WEBUI_SECRET_KEY`.
3. Укажите реальный `TELEGRAM_OWNER_ID`: бот не регистрирует первого отправителя автоматически.
4. Укажите каталог корпуса в `BRAIN_CORPUS_HOST_DIR`. Он монтируется только в bootstrap/worker, только для чтения и не попадает в image.
5. Оставьте публичные порты на `127.0.0.1`, если нет TLS reverse proxy и firewall.

Проверка конфигурации без запуска:

```bash
python scripts/validate_environment.py api
python scripts/validate_environment.py worker
python scripts/validate_environment.py telegram
docker compose config --quiet
```

## Запуск и первичная проверка

```bash
docker compose build brain_api knowledge_worker telegram
docker compose up -d brain_api knowledge_worker telegram
docker compose ps
docker compose logs --tail=200 brain_api knowledge_worker telegram
```

Проверки API:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health/live
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${BRAIN_API_KEY}" \
  http://127.0.0.1:8000/health/ready
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${BRAIN_API_KEY}" \
  http://127.0.0.1:8000/v1/models
```

`/health/live` подтверждает работу процесса. `/health/ready` не вызывает Gemini и возвращает 2xx только если доступны SQLite/storage, Chroma соответствует embedding spec, все пять verified-core источников завершены без failed/active jobs и heartbeat worker свежий.

## Наблюдение

```bash
docker compose ps
docker compose logs --since=30m brain_api
docker compose logs --since=30m knowledge_worker
docker compose logs --since=30m telegram
```

Требуют реакции:

- readiness возвращает не-2xx;
- повторные ошибки SQLite lock после `BRAIN_SQLITE_BUSY_TIMEOUT_MS`;
- worker heartbeat старше `BRAIN_WORKER_HEARTBEAT_MAX_AGE_SECONDS` или worker регулярно возвращает просроченные lease;
- изменилась версия/размерность embeddings и требуется переиндексация;
- Telegram повторяет update либо не может доставить ответ;
- grounding не находит источник там, где он ожидается, или источник пытается задавать инструкции модели.

## Резервное копирование

Данные SQLite, WAL-файлы, Chroma и пользовательские загрузки находятся в Compose volume `brain-data`. Для согласованной копии остановите всех писателей.

1. Найдите точное имя volume и проверьте его вручную:

```bash
docker volume ls --format '{{.Name}}' | grep 'brain-data$'
export BRAIN_VOLUME='<точное-имя-volume>'
```

2. Остановите сервисы и создайте архив:

```bash
mkdir -p backups
docker compose stop telegram knowledge_worker brain_api
docker run --rm \
  -v "${BRAIN_VOLUME}:/source:ro" \
  -v "${PWD}/backups:/backup" \
  alpine:3.20 sh -c \
  'cd /source && tar -czf /backup/brain-data-$(date -u +%Y%m%dT%H%M%SZ).tar.gz .'
docker compose start brain_api knowledge_worker telegram
```

3. Проверьте архив отдельно:

```bash
tar -tzf backups/brain-data-*.tar.gz | head
```

Храните архив зашифрованно: он содержит профиль, CRM, память и загруженные материалы.

## Восстановление

Восстановление перезаписывает рабочие данные. Сначала сохраните аварийную копию текущего volume.

```bash
export BRAIN_VOLUME='<точное-имя-volume>'
export BACKUP_FILE="${PWD}/backups/<выбранный-архив>.tar.gz"
docker compose stop telegram knowledge_worker brain_api

docker run --rm \
  -v "${BRAIN_VOLUME}:/restore" \
  -v "${BACKUP_FILE}:/backup.tar.gz:ro" \
  alpine:3.20 sh -ceu '
    find /restore -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    tar -xzf /backup.tar.gz -C /restore
  '

docker compose start brain_api knowledge_worker telegram
```

После восстановления обязательно проверьте `health/ready`, профиль, CRM, поиск знаний и один Telegram-сценарий. Не запускайте API и knowledge worker параллельно во время распаковки.

## Controlled vector reindex

Используйте только при смене embedding provider/model/dimension или повреждении Chroma. Команда строит новый индекс из SQLite `knowledge_chunks`, проверяет точное число векторов, атомарно меняет каталоги и сохраняет предыдущий индекс рядом как rollback target. SQLite, FTS и originals не изменяются.

1. Сделайте полный backup `brain-data` и зафиксируйте текущие commit/image digest.
2. Остановите все процессы, которые читают или пишут Chroma:

```bash
docker compose stop telegram brain_api knowledge_worker
```

3. Проверьте план без генерации embeddings:

```bash
docker compose run --rm --no-deps knowledge_worker \
  python /app/scripts/reindex_vectors.py plan
```

4. Выполните явный controlled swap. Для `EMBEDDING_PROVIDER_TYPE=gemini` это live-операция; для `chroma_onnx` и `hash_fallback` внешняя модель не вызывается.

```bash
docker compose run --rm --no-deps knowledge_worker \
  python /app/scripts/reindex_vectors.py apply --confirm REINDEX
```

5. Запустите worker/API, дождитесь readiness и проверьте несколько известных запросов:

```bash
docker compose up -d knowledge_worker brain_api
docker compose ps
```

Если проверка не прошла, снова остановите процессы и восстановите предыдущий каталог из manifest:

```bash
docker compose stop telegram brain_api knowledge_worker
docker compose run --rm --no-deps knowledge_worker \
  python /app/scripts/reindex_vectors.py rollback --confirm ROLLBACK
docker compose up -d knowledge_worker brain_api
```

Не удаляйте `vector_db.backup-*` до завершения staging/live проверки. После подтверждения оставьте один последний совместимый backup, остальные удалите вручную только после проверки полного `brain-data` архива.

## Обновление и миграции

1. Создайте резервную копию.
2. Зафиксируйте текущий commit SHA и digest image.
3. Проверьте PR CI и список оставшихся live-проверок.
4. Соберите новые images до остановки текущей версии.
5. Остановите писателей, обновите код и запустите API первым.
6. Дождитесь успешной миграции SQLite и readiness.
7. Запустите worker, затем Telegram.
8. Выполните staging/live checklist.

При смене embedding provider, модели или размерности не смешивайте векторы старого и нового пространства. Выполните controlled reindex выше.

## Откат

Откат кода безопасен только вместе с совместимыми данными.

1. Остановите Telegram, worker и API.
2. Верните предыдущий проверенный commit/image.
3. Если новая версия меняла схему или vector space, восстановите соответствующий backup.
4. Запустите API, затем worker и Telegram.
5. Проверьте readiness и минимальный live smoke.

Не используйте `docker compose down --volumes` при обычном откате: команда удаляет рабочие данные.

## Инциденты

При инциденте сохраните:

- UTC-время и commit SHA;
- `docker compose ps`;
- последние логи затронутого сервиса без секретов и пользовательского контента;
- HTTP-код readiness и degraded component;
- число повторных попыток/lease worker;
- факт успешной или неуспешной доставки Telegram.

Никогда не публикуйте `.env`, токены, API-ключи, содержимое backup или персональные данные в issue/PR.
