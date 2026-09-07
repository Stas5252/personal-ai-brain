r"""
Knowledge Ingestion Script for Personal AI Brain.
Bulk imports courses, video lessons, PDFs, presentations, audio recordings, and guides
into the Brain's Knowledge Ingestion Factory (ChromaDB Vector Index + SQLite FTS5).

Usage:
    python import_knowledge.py "C:\Users\пп\Desktop\вика курсы"
    python import_knowledge.py   (scans C:\Users\пп\Desktop\вика курсы or data/import/ by default)
"""
import sys
import os
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.models.knowledge import KnowledgeLayer, IngestionStatus
from src.brain.config import DATA_DIR
from src.brain.db import get_connection

SUPPORTED_EXTS = {
    ".pdf", ".pptx", ".docx", ".xlsx", ".html", ".htm", ".txt", ".md", ".csv",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
    ".mp4", ".mov", ".mkv", ".webm"
}

IGNORED_PATTERNS = {
    ".exe", ".zip", ".rar", ".7z", ".ttf", ".otf", ".tgs", ".webp",
    ".atn", ".xmp", ".dng", ".css", ".js", ".json"
}

INCOMPLETE_EXTS = {
    ".crdownload", ".part", ".tmp", ".downloading", ".incomplete"
}

DEFAULT_COURSE_PATH = Path(r"C:\Users\пп\Desktop\вика курсы")


def is_file_locked_or_downloading(p: Path) -> Tuple[bool, Optional[str]]:
    """Checks if a file is incomplete, actively downloading, or locked by another process."""
    name_lower = p.name.lower()
    for marker in INCOMPLETE_EXTS:
        if name_lower.endswith(marker):
            return True, f"Incomplete download ({marker})"
    if name_lower.endswith("~") or name_lower.startswith("~$"):
        return True, "Temporary lock file"

    try:
        if p.stat().st_size == 0:
            return True, "File is empty (0 bytes, possibly just created)"
        with open(p, "rb") as f:
            f.read(1024)
        return False, None
    except PermissionError as pe:
        return True, f"File locked (sharing violation / active write): {pe}"
    except OSError as oe:
        return True, f"I/O error accessing file: {oe}"


def clean_title_from_filename(p: Path) -> str:
    """Produces human-readable Russian title from filename."""
    stem = p.stem
    # Remove leading number prefixes like '1_', '2_0_', '10_'
    cleaned = re.sub(r"^\d+[\s._\-]+", "", stem)
    cleaned = cleaned.replace("_", " ").strip()
    return cleaned if len(cleaned) > 2 else stem.replace("_", " ")


def derive_tags_from_name(name: str) -> List[str]:
    """Extracts thematic photography tags from filename."""
    name_l = name.lower()
    tags = ["яровая", "курс_фотографии"]
    keyword_tags = [
        ("свет", "свет"),
        ("бабочк", "схема_света"),
        ("портрет", "портрет"),
        ("reels", "reels"),
        ("рилс", "reels"),
        ("сторис", "stories"),
        ("продаж", "продажи"),
        ("оффер", "офферы"),
        ("возражен", "возражения"),
        ("рассылк", "рассылки"),
        ("клиент", "клиенты"),
        ("прайс", "прайс"),
        ("тариф", "тарифы"),
        ("визуал", "визуал"),
        ("монтаж", "монтаж"),
        ("пинтерест", "pinterest"),
        ("pinterest", "pinterest"),
        ("нейросе", "нейросети"),
        ("промт", "промты"),
        ("чат_джипити", "chatgpt"),
        ("прогрев", "прогрев"),
        ("фотодень", "фотодень"),
        ("розыгрыш", "розыгрыш"),
        ("чб", "чб_обработка"),
        ("hypic", "hypic")
    ]
    for pattern, tag in keyword_tags:
        if pattern in name_l and tag not in tags:
            tags.append(tag)
    return tags


def ensure_yaishka_ingested(factory: KnowledgeIngestionFactory) -> bool:
    """Ensures data/yaishka_full_screenshots_transcription.md is indexed in Knowledge Base."""
    yaishka_file = DATA_DIR / "yaishka_full_screenshots_transcription.md"
    if not yaishka_file.exists():
        return False

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT source_id, title FROM knowledge_sources WHERE title LIKE ? AND ingestion_status = 'COMPLETED'", ("%Yaishka%",))
    existing = c.fetchone()
    conn.close()

    if existing:
        return True

    print("[*] Индексация полной методологии Яишки (data/yaishka_full_screenshots_transcription.md)...")
    try:
        factory.ingest_file(
            yaishka_file,
            title="Методология и разборы Яишки (Yaishka Knowledge Base)",
            layer=KnowledgeLayer.PROFESSIONAL,
            tags=["yaishka", "методология", "фотография", "свет", "мудборды", "возражения", "reels", "прайс"],
            author="Яишка / Yarovaya Photo School"
        )
        print("    ✅ База знаний Яишки успешно проиндексирована.")
        return True
    except Exception as e:
        print(f"    ❌ Ошибка индексации Yaishka: {e}")
        return False


SFX_MUSIC_KEYWORDS = (
    "whoosh", "glitch", "click-button", "swhoosh", "marker", "paper", "keyboard",
    "buzzer", "hit.", "hit ", "cash", "data 2", "swipe", "техно", "riser", "instrumental",
    "slowed", "reverb", "sped-up", "sped up", "camera", "cam ", "burn ", "burn_"
)


def is_sound_effect_or_music(p: Path) -> bool:
    """Detects video editing SFX sound packs or instrumental background music tracks."""
    ext = p.suffix.lower()
    if ext not in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]:
        return False
    name_l = p.name.lower()
    if any(k in name_l for k in SFX_MUSIC_KEYWORDS):
        return True
    if ext in [".wav", ".mp3"] and p.stat().st_size < 300 * 1024 and "audio" not in name_l:
        return True
    return False


def collect_course_materials(target_path: Path) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    """Scans directory and segregates ready files from downloading/locked/ignored files."""
    ready_files: List[Path] = []
    skipped_files: List[Tuple[Path, str]] = []

    if target_path.is_file():
        locked, reason = is_file_locked_or_downloading(target_path)
        if locked:
            skipped_files.append((target_path, reason or "Locked"))
        elif target_path.suffix.lower() in SUPPORTED_EXTS:
            ready_files.append(target_path)
        return ready_files, skipped_files

    for root, _, files in os.walk(target_path):
        for f in files:
            p = Path(root) / f
            ext = p.suffix.lower()

            # Skip thumbnails and temp files
            if p.name.endswith(".thumb.jpg") or p.name.endswith("_thumb.jpg"):
                continue
            if ext in IGNORED_PATTERNS:
                continue

            # Skip video-editing sound effects (swooshes, clicks, beeps)
            if is_sound_effect_or_music(p):
                continue

            # Check if file is still downloading or locked
            locked, reason = is_file_locked_or_downloading(p)
            if locked:
                skipped_files.append((p, reason or "Locked"))
                continue

            if ext in SUPPORTED_EXTS:
                ready_files.append(p)

    return ready_files, skipped_files


def sort_by_educational_priority(files: List[Path]) -> List[Path]:
    """Prioritizes syllabus/HTML chats and documents ahead of large media."""
    def priority_key(p: Path) -> int:
        ext = p.suffix.lower()
        if p.name.startswith("messages") and ext in [".html", ".htm"]:
            return 1
        if ext in [".md", ".txt"]:
            return 2
        if ext in [".pdf", ".pptx", ".docx", ".xlsx"]:
            return 3
        if ext in [".ogg", ".m4a", ".mp3", ".wav"]:
            return 4
        if ext in [".mp4", ".mov", ".webm"]:
            return 5
        return 6

    return sorted(files, key=lambda f: (priority_key(f), f.stat().st_size))


def main():
    parser = argparse.ArgumentParser(description="Bulk ingest knowledge files into Personal AI Brain")
    parser.add_argument("path", nargs="?", default=None, help="Directory or file path to ingest")
    parser.add_argument("--max-files", type=int, default=None, help="Limit number of files to process")
    parser.add_argument("--skip-videos", action="store_true", help="Skip heavy video files in synchronous run")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of existing files")
    args = parser.parse_args()

    # Determine target path
    if args.path:
        target_path = Path(args.path)
    elif DEFAULT_COURSE_PATH.exists():
        target_path = DEFAULT_COURSE_PATH
    else:
        target_path = DATA_DIR / "import"
        target_path.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("       PERSONAL AI BRAIN — MULTIMODAL KNOWLEDGE INGESTION")
    print("=" * 75)
    print(f"[*] Целевая папка для импорта: {target_path.resolve()}")

    if not target_path.exists():
        print(f"[!] Путь не существует: {target_path}")
        return

    # Use factory in non-strict mode for real-world course documents (preserves all text even if slides have photos)
    factory = KnowledgeIngestionFactory(strict_mode=False)

    # 1. Ensure Yaishka core methodology is indexed
    ensure_yaishka_ingested(factory)

    # 2. Collect and filter files
    print("[*] Сканирование структуры папок и проверка статуса файлов...")
    ready_files, skipped_files = collect_course_materials(target_path)

    if skipped_files:
        print(f"[!] Обнаружено файлов в процессе загрузки или заблокированных: {len(skipped_files)}")
        for sp, reason in skipped_files[:5]:
            print(f"    • {sp.name}: {reason} (будет догружен позже)")
        if len(skipped_files) > 5:
            print(f"    ... и еще {len(skipped_files) - 5} файлов.")

    # Filter out videos if requested
    if args.skip_videos:
        ready_files = [f for f in ready_files if f.suffix.lower() not in [".mp4", ".mov", ".webm"]]

    # Sort files by pedagogical priority
    ready_files = sort_by_educational_priority(ready_files)

    if args.max_files:
        ready_files = ready_files[:args.max_files]

    print(f"[*] Готово к индексации файлов: {len(ready_files)}")
    print("-" * 75)

    success_count = 0
    duplicate_count = 0
    error_count = 0
    total_chunks = 0
    layers_count: Dict[str, int] = {}
    queue = IngestionQueue()

    for i, file_path in enumerate(ready_files, 1):
        rel_name = file_path.name
        size_mb = file_path.stat().st_size / (1024 * 1024)
        ext = file_path.suffix.lower()

        # For very large video files (> 150MB), queue them for background leasing worker to avoid blocking
        if ext in [".mp4", ".mov"] and size_mb > 150.0:
            print(f"[{i}/{len(ready_files)}] Очередь фоновой обработки: {rel_name} ({size_mb:.1f} МБ)...", end=" ", flush=True)
            try:
                # Validate file and register in queue
                val = factory.storage.validate_file(file_path)
                if val.is_valid:
                    src_id = f"vid-{val.sha256[:16]}"
                    queue.enqueue_job(source_id=src_id, priority=5)
                    print("⏱ Поставлено в очередь фонового воркера")
                    success_count += 1
                else:
                    print(f"⚠️ {val.error_message}")
            except Exception as e:
                print(f"❌ {e}")
            continue

        title = clean_title_from_filename(file_path)
        tags = derive_tags_from_name(file_path.name)
        author = "Ярослава Яровая / Yarovaya Photo School"

        print(f"[{i}/{len(ready_files)}] Индексация: {rel_name} ({size_mb:.2f} МБ)...", end=" ", flush=True)

        try:
            source, chunks = factory.ingest_file(
                file_path=file_path,
                title=title,
                author=author,
                tags=tags,
                force=args.force
            )
            chunk_cnt = len(chunks)
            total_chunks += chunk_cnt

            layer_name = source.layer.value if source.layer else "GLOBAL"
            layers_count[layer_name] = layers_count.get(layer_name, 0) + 1

            if source.ingestion_status == IngestionStatus.DUPLICATE:
                duplicate_count += 1
                print(f"🔁 Уже в базе (Дубликат, фрагментов: {chunk_cnt})")
            else:
                success_count += 1
                print(f"✅ Готово! [Слой: {layer_name}, фрагментов: {chunk_cnt}]")

        except Exception as e:
            error_count += 1
            print(f"❌ Ошибка: {e}")

    print("-" * 75)
    print("🎉 ИМПОРТ КУРСОВ И МАТЕРИАЛОВ ЗАВЕРШЕН!")
    print(f"• Успешно обработано / поставлено в очередь: {success_count} файлов")
    if duplicate_count > 0:
        print(f"• Уже присутствовало в базе (пропущено без дублирования): {duplicate_count}")
    if error_count > 0:
        print(f"• Файлов с ошибками/неподдерживаемых: {error_count}")
    print(f"• Создано смысловых фрагментов (chunks) в векторной базе: {total_chunks}")
    print("• Распределение по слоям знаний:")
    for lyr, cnt in sorted(layers_count.items()):
        print(f"    - {lyr}: {cnt} источников")
    print("• Все знания теперь активны в BrainService, Telegram и Web Studio!")


if __name__ == "__main__":
    main()
