# Personal AI Brain: Спецификация REST API (Brain API & OpenAI Adapter)

**Проект:** Персональный AI-ассистент фотографа и визуального креатора  
**Модуль:** Brain API (`src/brain/api/`)  
**Статус:** Реализован и верифицирован (FastAPI, 21 эндпоинт, 100% PASS)  

---

## 1. Архитектура интеграции

Personal AI Brain работает как автономный микросервис на FastAPI и предоставляет два интерфейсных фасада:
1. **Нативный Brain API (`/brain/*`):** 21 эндпоинт для полного управления профилем, памятью, знаниями, стилем, проектами и клиентами.
2. **OpenAI-совместимый адаптер (`/v1/*`):** эндпоинты `/v1/models` и `/v1/chat/completions`. Это позволяет подключить Brain к любому стандартному клиенту (Open WebUI, LibreChat, мобильные приложения) как модель `personal-ai-brain` без изменения кода клиентов.

```
       [Open WebUI]        [Telegram Bot]        [Мобильный MAX]
             |                   |                      |
             | /v1/chat/completions                     | /brain/chat
             v                   +----------------------+
    +--------------------------------------------------------+
    |                 FASTAPI APPLICATION                    |
    |  /v1/models               /brain/memory                |
    |  /v1/chat/completions     /brain/knowledge             |
    |  /brain/chat              /brain/style/exemplars       |
    |  /brain/profile           /brain/projects & clients    |
    +--------------------------------------------------------+
                                 |
                                 v
                       BRAIN CORE SERVICE
```

---

## 2. Аутентификация

Все запросы к защищенным эндпоинтам требуют передачи Bearer-токена в заголовке `Authorization`:
```http
Authorization: Bearer <BRAIN_API_KEY>
```
При отсутствии или невалидности токена сервис возвращает HTTP `401 Unauthorized` с телом:
```json
{"detail": "Invalid brain bearer token"}
```

---

## 3. Спецификация ключевых эндпоинтов

### 3.1. Оркестрация диалога (Chat & Completions)

#### `POST /brain/chat`
Основной эндпоинт оркестрации персонального мозга.

- **Request Body:**
```json
{
  "query": "Как аргументировать стоимость пакета Премиум?",
  "project_id": null,
  "client_id": null,
  "model": "gemini-2.5-flash",
  "auto_admission": true
}
```

- **Response:**
```json
{
  "response": "Текст ответа ассистента в авторском стиле фотографа...",
  "routing": {
    "primary_intent": "SALES",
    "secondary_intents": ["PRICING", "CONTENT"],
    "confidence": 0.92,
    "required_tools": []
  },
  "admission": {
    "action": "SAVE",
    "reason": "Client or project transaction fact",
    "memory_type": "CLIENT"
  },
  "benchmark": {
    "vocabulary_similarity": 0.85,
    "sentence_rhythm_score": 0.90,
    "emoji_density_score": 1.0,
    "cta_presence_score": 1.0,
    "forbidden_violations": 0,
    "overall_score": 0.93
  },
  "hallucination_verdict": "grounded",
  "trace": {
    "request_id": "req-9c88210f",
    "primary_intent": "SALES",
    "latency_sec": 1.42,
    "model": "gemini-2.5-flash"
  }
}
```

#### `POST /v1/chat/completions` (OpenAI Adapter)
Позволяет Open WebUI вызывать Personal AI Brain как стандартную LLM-модель.

- **Request Body:**
```json
{
  "model": "personal-ai-brain",
  "messages": [
    {"role": "user", "content": "Привет, подскажи схему света бабочка"}
  ]
}
```

- **Response:**
```json
{
  "id": "brain-chat-7a8f9c112",
  "object": "chat.completion",
  "created": 1788682100,
  "model": "personal-ai-brain",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Схема Бабочка (Paramount) строится на фронтальном верхнем источнике..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 85,
    "total_tokens": 205
  },
  "brain_trace": { ... }
}
```

---

### 3.2. Долговременная память (`/brain/memory`)

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `POST` | `/brain/memory` | Добавление факта с проверкой через Admission Policy. |
| `GET` | `/brain/memory` | Получение активных воспоминаний с фильтрацией по статусу, типу, клиенту. |
| `DELETE` | `/brain/memory/{id}` | Удаление конкретного воспоминания по ID. |
| `DELETE` | `/brain/memory/user` | Полный сброс памяти пользователя (GDPR / Right to be Forgotten). |

---

### 3.3. Профиль пользователя и онбординг (`/brain/profile`, `/brain/onboarding`)

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `GET` | `/brain/profile` | Получение текущего структурированного профиля автора. |
| `POST` | `/brain/profile` | Сохранение/обновление профиля автора. |
| `POST` | `/brain/onboarding/start` | Старт 10-шаговой сессии интерактивного онбординга. |
| `POST` | `/brain/onboarding/answer` | Прием ответа на текущий вопрос, продвижение к следующему шагу или генерация готового профиля. |

---

### 3.4. Иерархическая база знаний (`/brain/knowledge`)

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `POST` | `/brain/knowledge` | Добавление документа в один из 6 слоев знаний с чанкованием. |
| `GET` | `/brain/knowledge` | Ретривал фрагментов по семантическому запросу со сквозной ссылкой `SourceTrace`. |

---

### 3.5. Стиль и эталоны (`/brain/style/exemplars`)

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `POST` | `/brain/style/exemplars` | Добавление эталона (`GOOD_EXAMPLE` / `BAD_EXAMPLE`). |
| `GET` | `/brain/style/exemplars` | Получение эталонов с фильтрацией по категории (`POST`, `REELS_SCRIPT` и др.). |

---

### 3.6. Проекты и клиенты (`/brain/projects`, `/brain/clients`)

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `POST` | `/brain/projects` | Создание нового проекта съемки. |
| `GET` | `/brain/projects/{id}` | Получение карточки проекта, статуса, задач и решений. |
| `POST` | `/brain/clients` | Создание карточки клиента (статус, бюджет, предпочтения). |
| `GET` | `/brain/clients/{id}` | Получение карточки клиента и истории работы. |

---

### 3.7. Маршрутизация и телеметрия (`/brain/route`, `/brain/context`, `/brain/traces`)

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `POST` | `/brain/route` | Тестирование классификатора интентов без вызова языковой модели. |
| `POST` | `/brain/context` | Предпросмотр собранного структурированного промпта и подсчет токенов. |
| `GET` | `/brain/traces` | Журнал последних телеметрических трейсов (латентность, интенты, модели). |

---

## 4. Подключение к Open WebUI

Чтобы Open WebUI работал через Personal AI Brain:
1. В веб-интерфейсе Open WebUI перейдите в **Admin Panel -> Settings -> Connections -> OpenAI API**.
2. Укажите URL: `http://host.docker.internal:8000/v1` (или IP хоста).
3. Укажите API Key: `test-brain-key` (или ключ из `.env`).
4. В списке моделей появится `personal-ai-brain`. Выберите её в качестве модели по умолчанию.
