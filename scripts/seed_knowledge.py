#!/usr/bin/env python3
"""
scripts/seed_knowledge.py

Индексирует все KB-файлы из src/brain/knowledge/*.md в ChromaDB.
Запускать один раз при деплое (или при обновлении базы знаний).

Использование:
    python scripts/seed_knowledge.py
    python scripts/seed_knowledge.py --reset     # сброс и переиндексация
    python scripts/seed_knowledge.py --check     # только проверка
"""

import os
import sys
import argparse
import hashlib
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Настройка
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent.parent
KB_DIR = ROOT_DIR / "src" / "brain" / "knowledge"
CHUNK_SIZE = 800       # символов на чанк
CHUNK_OVERLAP = 150   # перекрытие между чанками
COLLECTION_NAME = "photography_kb"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Зависимости
# ---------------------------------------------------------------------------
try:
    import chromadb
except ImportError:
    sys.exit("❌  chromadb не установлен. Запусти: pip install chromadb")


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Разбивает текст на перекрывающиеся чанки."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


def file_md5(path: Path) -> str:
    """MD5 файла для определения изменений."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_kb_files() -> list[dict]:
    """Загружает все .md файлы из KB_DIR."""
    docs = []
    for md_file in sorted(KB_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8").strip()
        if not content:
            continue
        docs.append({
            "path": md_file,
            "name": md_file.stem,
            "content": content,
            "md5": file_md5(md_file),
        })
    return docs


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------

def get_chroma_client():
    """Возвращает клиент ChromaDB (persistent или HTTP)."""
    chroma_url = os.getenv("CHROMA_URL")          # HTTP-режим (Docker)
    chroma_path = os.getenv("CHROMA_PATH", ".chroma_db")  # локальный путь

    if chroma_url:
        log.info(f"ChromaDB HTTP: {chroma_url}")
        return chromadb.HttpClient(host=chroma_url.rstrip("/"))
    else:
        log.info(f"ChromaDB local: {chroma_path}")
        return chromadb.PersistentClient(path=chroma_path)


def seed(reset: bool = False) -> int:
    """Индексирует KB-файлы. Возвращает количество добавленных чанков."""
    client = get_chroma_client()

    if reset:
        log.warning("Удаляю коллекцию для переиндексации...")
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    docs = load_kb_files()
    if not docs:
        log.error(f"Нет .md файлов в {KB_DIR}")
        return 0

    log.info(f"Найдено {len(docs)} KB-файлов")

    # Получаем уже проиндексированные IDs
    existing = set(collection.get()["ids"])
    added = 0

    for doc in docs:
        chunks = chunk_text(doc["content"])
        ids, texts, metas = [], [], []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc['name']}::{i}::{doc['md5'][:8]}"

            # Пропускаем уже проиндексированные (инкрементальный режим)
            if chunk_id in existing and not reset:
                continue

            ids.append(chunk_id)
            texts.append(chunk)
            metas.append({
                "source": doc["name"],
                "chunk_index": i,
                "total_chunks": len(chunks),
                "md5": doc["md5"],
            })

        if ids:
            collection.add(ids=ids, documents=texts, metadatas=metas)
            added += len(ids)
            log.info(f"  ✅ {doc['name']}: +{len(ids)} чанков")
        else:
            log.info(f"  ⏭  {doc['name']}: актуален, пропущен")

    total = collection.count()
    log.info(f"\n🎉 Готово! Добавлено: {added} чанков. Всего в коллекции: {total}")
    return added


def check():
    """Выводит информацию о текущем состоянии коллекции."""
    client = get_chroma_client()
    try:
        collection = client.get_collection(COLLECTION_NAME)
        total = collection.count()
        log.info(f"\n📊 Коллекция '{COLLECTION_NAME}': {total} чанков")

        # Тестовый запрос
        results = collection.query(
            query_texts=["как работать с возражением дорого"],
            n_results=3
        )
        log.info("\n🔍 Тестовый запрос: 'как работать с возражением дорого'")
        for i, (doc, meta) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0]
        )):
            log.info(f"  [{i+1}] source={meta['source']} | {doc[:100]}...")
    except Exception as e:
        log.error(f"Коллекция не найдена или ошибка: {e}")
        log.info("Запусти: python scripts/seed_knowledge.py")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Индексация KB-файлов в ChromaDB"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Удалить коллекцию и переиндексировать с нуля"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Только проверка — не индексировать"
    )
    args = parser.parse_args()

    if not KB_DIR.exists():
        sys.exit(f"❌  Директория не найдена: {KB_DIR}")

    if args.check:
        check()
    else:
        seed(reset=args.reset)


if __name__ == "__main__":
    main()
