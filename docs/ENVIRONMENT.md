# Отчёт об аудите окружения (Environment Audit)

**Дата проведения аудита:** 2026-09-06  
**Инженер:** Senior AI Infrastructure Engineer + Principal Architect  
**Рабочая директория:** `C:\Users\пп\Desktop\ии для вики`

---

## 1. Аппаратная конфигурация (Hardware)

| Компонент | Значение | Примечание |
| :--- | :--- | :--- |
| **Операционная система** | Microsoft Windows 10 Pro (Версия: 10.0.19045, 64-разрядная) | Сборка 19045, WSL2 активирован |
| **Процессор (CPU)** | 13th Gen Intel(R) Core(TM) i5-13400F | 10 физических ядер, 16 логических процессоров |
| **Оперативная память (RAM)**| 32 GB (Всего: 33 362 188 KB, Свободно: ~22 818 536 KB) | Достаточно для одновременной работы контейнеров и локальных задач |
| **Графический процессор (GPU)** | NVIDIA GeForce RTX 3070 (8192 MiB VRAM / 8 GB GDDR6) | Bus-Id: `00000000:01:00.0`, TDP: 240W, активен дисплей |
| **Драйвер NVIDIA** | Driver Version: `591.74` | WDDM 3.x, полная поддержка DirectML и CUDA |
| **Версия CUDA (Драйвер)** | CUDA Version: `13.1` | Драйвер поддерживает рантаймы до CUDA 13.1 |
| **Дисковое пространство** | Диск `C:`: 930.85 GB всего, **94.16 GB свободно** (~836.7 GB занято) | Файловая система NTFS. Свободного места достаточно для образов и баз данных |

---

## 2. Программный стек (Software & Tooling)

| Инструмент | Версия / Состояние | Путь / Источник |
| :--- | :--- | :--- |
| **Docker Desktop** | 4.81.0 (сборка 232925) | `C:\Program Files\Docker\Docker\Docker Desktop.exe` |
| **Docker Engine** | 29.6.1 (API 1.55, containerd e53c7c1, runc v1.3.6) | WSL2 Linux Engine (`npipe:////./pipe/dockerDesktopLinuxEngine`) |
| **Docker Compose** | v5.2.0 | Плагин Docker CLI (`docker compose`) |
| **NVIDIA Container Toolkit** | Поддерживается (WSL2 Linux Kernel 6.18, CDI `docker.com/gpu=webgpu`, рантайм `nvidia`) | Доступно в Docker Desktop |
| **Git** | 2.52.0.windows.1 | Установлен в PATH |
| **Python** | Python 3.14.2 | Установлен в PATH |
| **Node.js** | v24.13.0 | Установлен в PATH |
| **FFmpeg** | 9.0-full_build (gyan.dev) с поддержкой `--enable-cuda-llvm`, `--enable-nvenc`, `--enable-nvdec`, `--enable-whisper` | Установлен в PATH |
| **NVCC (CUDA Compiler)** | Не добавлен в пользовательский PATH хоста | Компиляция ядер на хосте не требуется, рантайм доступен внутри контейнеров |

---

## 3. Анализ сетевой доступности (Network Connectivity)

Проведены прямые запросы к критическим сетевым узлам:
- `https://www.google.com`: **HTTP 200 OK** (Прямой доступ)
- `https://github.com`: **HTTP 200 OK** (Прямой доступ)
- `https://registry-1.docker.io/v2/`: **HTTP 401** (Ожидаемый ответ эндпоинта без токена, Docker Hub доступен без блокировок)
- `https://api.openai.com/v1/models`: **HTTP 401** (Ожидаемый ответ без Bearer-токена, OpenAI API доступен)
- `https://generativelanguage.googleapis.com`: **HTTP 200 OK** (Gemini API полностью доступен)

---

## 4. Карта портов хоста (Port Allocation Map)

Перед внесением изменений выполнена ревизия всех прослушиваемых TCP портов:

### Занятые порты другими проектами (Docker):
- `3000`: `ars-api`
- `5432`: `ars-postgres` (PostgreSQL 16 с pgvector)
- `6379`: `ars-redis` (Redis 7)
- `8000`: `ars-assistant` (FastAPI / Uvicorn)
- `8081`: `ars-telegram-bot-api`
- `8787`: `ars-montage`
- `9000, 9001`: `ars-minio` (S3 Storage)

### Системные и служебные порты хоста:
- `135, 139, 445`: Windows RPC / SMB
- `10808, 10809, 10813`: Локальные прокси-шлюзы
- `5040, 5354, 5357, 7680, 8045, 9012, 9013, 13030-13032, 22112`

### Статус целевого порта для Open WebUI:
- Порт **`8080`**: **СВОБОДЕН** (проверено через `Get-NetTCPConnection`).
- Порт **`8090`**: **СВОБОДЕН** (резервный порт).
- Решение: назначить `8080:8080` для Open WebUI.

---

## 5. Изоляция томов данных (Volume Isolation)

В системе обнаружено множество томов проектов `ars_*` (`ars_minio_data`, `ars_postgres_data`, `ars_redis_data` и др.) и `kd_geo_*`.
Для полного исключения конфликтов:
- Создан изолированный проект `personal-ai` в `docker-compose.yml`.
- Назначен независимый именованный том: **`open-webui-data`**.
- Существующие тома и контейнеры остаются нетронутыми.

---

## 6. Доступный AI Provider

В переменных окружения хоста обнаружен активный ключ `GEMINI_API_KEY`:
- Протестирован эндпоинт `https://generativelanguage.googleapis.com/v1beta/models?key=...`: возвращено 50 доступных моделей (включая `gemini-2.5-flash`, `gemini-2.5-pro`).
- Протестирован OpenAI-совместимый эндпоинт:
  `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` с заголовком `Authorization: Bearer $GEMINI_API_KEY`. Запрос вернул корректный JSON-ответ.
- Провайдер готов к бесшовной интеграции через OpenAI-совместимый слой Open WebUI.
