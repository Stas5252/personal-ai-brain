# Руководство по установке и эксплуатации (Installation & Operations Guide)

**Продукт:** Персональный AI-ассистент (Open WebUI Foundation)  
**Платформа:** Docker & Docker Compose (Windows 10 / WSL2)  
**Директория проекта:** `C:\Users\пп\Desktop\ии для вики`
**Версия платформы:** `ghcr.io/open-webui/open-webui:0.11.3` (Pinned)

---

## 1. Системные требования

- **ОС:** Windows 10/11 64-bit с подсистемой WSL2
- **Docker:** Docker Desktop 4.x (активный движок `desktop-linux`)
- **Порты:** Должен быть свободен внешний порт `8080` (настраивается через переменную `PORT`)
- **Память:** минимум 2 GB свободной RAM
- **Диск:** минимум 5 GB свободного пространства (для образов и эмбеддингов)

---

## 2. Структура файлов проекта

```
ии для вики/
├── .env                  # Локальные переменные окружения и ключи (в .gitignore)
├── .env.example          # Шаблон конфигурации окружения
├── .gitignore            # Игнорирование секретов и локальных данных
├── docker-compose.yml    # Манифест развёртывания Open WebUI
├── tests/                # Тестовые фикстуры и бенчмарки
│   ├── fixtures/
│   └── artifacts/
└── docs/                 # Архитектурная и эксплуатационная документация
    ├── ENVIRONMENT.md
    ├── ARCHITECTURE_OPTIONS.md
    ├── ARCHITECTURE.md
    ├── INSTALLATION.md
    ├── DECISIONS.md
    ├── TESTING.md
    └── FOUNDATION_VALIDATION.md
```

---

## 3. Пошаговый запуск системы

### Шаг 1. Конфигурация `.env`
Скопируйте `.env.example` в `.env` и задайте безопасные значения:

```bash
# Порт сервиса
PORT=8080

# Секретный ключ для подписи сессионных токенов (генерируется: python -c "import secrets; print(secrets.token_hex(32))")
WEBUI_SECRET_KEY=***REDACTED***

# Регистрация (отключена после создания администратора для безопасности)
ENABLE_SIGNUP=false

# Название рабочего пространства
WEBUI_NAME=Personal AI Studio

# Модель по умолчанию
DEFAULT_MODELS=gemini-2.5-flash

# Эндпоинт и ключ модели (Google Gemini OpenAI-compatible)
OPENAI_API_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
OPENAI_API_KEY=***REDACTED***
```

### Шаг 2. Запуск контейнера
В терминале PowerShell выполните:

```powershell
docker compose up -d
```

### Шаг 3. Проверка статуса
```powershell
docker compose ps
docker compose logs -f open-webui
```

При успешном старте сервис станет доступен по адресу:  
👉 **`http://localhost:8080`**

### Шаг 4. Управление доступом
После создания первого пользователя-администратора параметр `ENABLE_SIGNUP` в `.env` переводится в `false`, блокируя публичную регистрацию.

---

## 4. Эксплуатационные команды (Operations)

| Действие | Команда |
| :--- | :--- |
| **Остановка сервиса** | `docker compose down` |
| **Перезапуск сервиса** | `docker compose restart` |
| **Просмотр логов** | `docker compose logs -f` |
| **Обновление до проверенной версии** | Изменить тег версии в `docker-compose.yml` и выполнить `docker compose up -d` |
| **Проверка статуса контейнера** | `docker compose ps` |

---

## 5. Резервное копирование и восстановление (Backup & Restore)

Все пользовательские данные, диалоги, документы и настройки хранятся в томе `open-webui-data`.

### Создание резервной копии:
```powershell
docker run --rm -v open-webui-data:/data -v ${PWD}:/backup alpine tar czvf /backup/open-webui-backup-$(Get-Date -Format "yyyyMMdd").tar.gz -C /data .
```

### Восстановление из копии:
```powershell
docker run --rm -v open-webui-data:/data -v ${PWD}:/backup alpine sh -c "cd /data && rm -rf * && tar xzvf /backup/open-webui-backup-<ДАТА>.tar.gz"
```
