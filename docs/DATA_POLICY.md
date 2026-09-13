# File, type and retention policy

Эта политика фиксирует границы, которые должны совпадать с `src/brain/config.py`, upload validation и operations runbook.

## Размеры

| Канал | Переменная | Default | Назначение |
|---|---|---:|---|
| Internet/API/Telegram upload | `MAX_FILE_SIZE_BYTES` | 20 MiB | Ограничивает непроверенный пользовательский файл до записи/извлечения. Допустимый production range: 1 MiB–2 GiB. |
| Version-controlled course corpus | `CORPUS_MAX_FILE_SIZE_BYTES` | 64 MiB | Отдельный лимит для trusted bootstrap corpus; не повышает API limit. |
| Chat query | фиксированный guard | 32,000 chars | Один запрос. |
| Conversation history | фиксированный guard | 64,000 chars | Суммарный текст истории. |

Повышение лимитов требует оценки RAM/CPU/disk, extraction timeout и backup window. Reverse proxy должен иметь не больший body limit.

## Поддерживаемые типы

Расширение и фактическая сигнатура/MIME проверяются вместе; переименование исполняемого файла в допустимое расширение должно быть отклонено.

- Documents: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.txt`, `.md`, `.html`
- Images: `.jpg`, `.jpeg`, `.png`, `.webp`, `.tiff`, `.tif`
- Audio: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`
- Video: `.mp4`, `.mov`, `.mkv`, `.webm`

Архивы, исполняемые файлы, symlinks и неизвестные типы не являются knowledge inputs.

## Retention и удаление

| Данные | Где | Retention | Удаление |
|---|---|---|---|
| Временный upload для knowledge registration | `data/uploads` | Только до завершения регистрации | API удаляет temporary upload в `finally`; зарегистрированный original уже скопирован в storage. |
| Обычный asset upload | `data/uploads` | До явной ручной очистки | Перед удалением убедиться, что asset не используется проектом/ответом. Автоматического TTL пока нет. |
| Knowledge originals | `data/storage/originals` | Пока существует source | Удалять только через source deletion/approved maintenance, чтобы SQLite, FTS, Chroma и derived очищались согласованно. |
| Derived extraction artifacts | `data/storage/derived` | Пока существует source | Удаляются вместе с source; допускается регенерация из original. |
| SQLite + WAL/SHM | `data/brain.db*` | Бессрочно, включая профиль/CRM/memory/jobs | Только по approved data deletion; backup перед изменением. |
| Chroma vectors/spec | `data/vector_db` | Пока совместимы с active embedding spec | Controlled reindex/rollback из `docs/OPERATIONS.md`; не удалять отдельно при работающих сервисах. |
| Reindex backup | `data/vector_db.backup-*` | Последний совместимый backup до live verification | Старые копии удалять вручную только после проверенного полного backup. |
| CI artifacts | GitHub Actions | 14 дней | Автоматически по workflow retention. |
| Production backups | Внешнее encrypted storage | По локальной legal/business policy | Минимум один проверенный pre-release backup; документировать owner и expiry вне репозитория. |

`docker compose down --volumes` запрещён для обычного обновления/отката: он удаляет рабочие данные.

## Privacy и инциденты

`brain-data` содержит пользовательские материалы, профиль, CRM и память. Backup должен быть зашифрован, доступ — минимальным, а логи/metrics не должны содержать запросы, filenames, document text, токены или персональные идентификаторы. При удалении данных сохраняйте audit timestamp и scope, но не копируйте удалённый контент в issue/PR.
