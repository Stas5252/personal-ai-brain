"""
Knowledge Ingestion Script for Personal AI Brain.
Bulk imports courses, video lessons, PDFs, presentations, audio recordings, and guides
into the Brain's Knowledge Ingestion Factory (ChromaDB Vector Index + SQLite FTS5).

Usage:
    python import_knowledge.py "C:\path\to\courses_or_pdfs"
    python import_knowledge.py   (scans data/import/ by default)
"""
import sys
import os
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.config import DATA_DIR

SUPPORTED_EXTS = {
    ".pdf", ".docx", ".txt", ".md", ".csv",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
    ".jpg", ".jpeg", ".png", ".webp"
}

def main():
    parser = argparse.ArgumentParser(description="Bulk ingest knowledge files into Personal AI Brain")
    parser.add_argument("path", nargs="?", default=None, help="Directory or file path to ingest")
    args = parser.parse_args()

    default_import_dir = DATA_DIR / "import"
    default_import_dir.mkdir(parents=True, exist_ok=True)

    target_path = Path(args.path) if args.path else default_import_dir

    print("=" * 70)
    print("      PERSONAL AI BRAIN — KNOWLEDGE INGESTION FACTORY")
    print("=" * 70)
    print(f"[*] Целевая папка для импорта: {target_path.resolve()}")

    if not target_path.exists():
        print(f"[!] Путь не существует: {target_path}")
        print(f"[*] Поместите ваши PDF, курсы, видео или аудио в папку: {default_import_dir.resolve()}")
        print(f"    и запустите команду снова: python import_knowledge.py")
        return

    # Collect files
    files_to_ingest = []
    if target_path.is_file():
        if target_path.suffix.lower() in SUPPORTED_EXTS:
            files_to_ingest.append(target_path)
    else:
        for root, _, files in os.walk(target_path):
            for f in files:
                p = Path(root) / f
                if p.suffix.lower() in SUPPORTED_EXTS:
                    files_to_ingest.append(p)

    if not files_to_ingest:
        print(f"[!] В папке '{target_path}' не найдено поддерживаемых файлов.")
        print(f"    Поддерживаемые форматы: {', '.join(sorted(SUPPORTED_EXTS))}")
        print(f"[*] Перетащите файлы курсов, видео или PDF в папку '{default_import_dir.resolve()}' и повторите запуск.")
        return

    print(f"[*] Найдено файлов для индексации: {len(files_to_ingest)}")
    print("-" * 70)

    factory = KnowledgeIngestionFactory()
    success_count = 0
    total_chunks = 0

    for i, file_path in enumerate(files_to_ingest, 1):
        rel_name = file_path.name
        size_mb = file_path.stat().st_size / (1024 * 1024)
        print(f"[{i}/{len(files_to_ingest)}] Индексация: {rel_name} ({size_mb:.2f} МБ)...", end=" ", flush=True)

        try:
            source, chunks = factory.ingest_file(file_path)
            chunk_cnt = len(chunks)
            total_chunks += chunk_cnt
            success_count += 1
            print(f"✅ Готово! (Слой: {source.layer.value if hasattr(source, 'layer') and source.layer else 'auto'}, фрагментов: {chunk_cnt})")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    print("-" * 70)
    print(f"🎉 ИМПОРТ ЗАВЕРШЕН!")
    print(f"• Успешно обработано файлов: {success_count} из {len(files_to_ingest)}")
    print(f"• Создано смысловых фрагментов (chunks) в векторной базе: {total_chunks}")
    print(f"• Все материалы теперь доступны Brain для поиска и генерации ответов.")

if __name__ == "__main__":
    main()
