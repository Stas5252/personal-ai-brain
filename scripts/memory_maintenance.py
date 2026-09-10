#!/usr/bin/env python3
"""
Ночная уборка памяти.

Зачем это нужно. Память пополняется во время разговора, и даже с проверкой
на повторы один и тот же факт со временем обрастает формулировками.
Скрипт делает две вещи: удаляет истекшие временные заметки и сворачивает
близкие повторы в одну запись.

Удаления данных нет: повторы помечаются SUPERSEDED со ссылкой на ту запись,
которая осталась активной, поэтому историю всегда можно поднять.

Запуск:
    python scripts/memory_maintenance.py --dry-run   # только показать, что будет свёрнуто
    python scripts/memory_maintenance.py             # выполнить уборку

В боевом режиме удобно вешать в cron раз в сутки, например в 04:30.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.brain.engines import memory_hygiene as hygiene  # noqa: E402
from src.brain.engines.memory_engine import MemoryEngine  # noqa: E402
from src.brain.models.memory import MemoryStatus, MemoryType  # noqa: E402


def _shorten(text: str, limit: int = 90) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "\u2026"


def preview(engine: MemoryEngine) -> int:
    """Показывает, какие записи сошлись бы в одну, но ничего не меняет."""
    planned = 0
    for m_type in MemoryType:
        items = engine.get_memories(status=MemoryStatus.ACTIVE, memory_type=m_type)
        if len(items) < 2:
            continue
        payload = [
            {
                "id": i.id,
                "content": i.content,
                "importance": i.importance,
                "updated_at": i.updated_at or i.created_at or "",
            }
            for i in items
        ]
        by_id = {i.id: i for i in items}
        for group in hygiene.consolidation_groups(payload):
            keeper = by_id.get(group.get("keeper"))
            duplicates = [by_id.get(d) for d in (group.get("duplicates") or [])]
            duplicates = [d for d in duplicates if d is not None]
            if keeper is None or not duplicates:
                continue
            print(f"\n[{m_type.value}] останется: {_shorten(keeper.content)}")
            for dup in duplicates:
                planned += 1
                print(f"    свернётся: {_shorten(dup.content)}")
    return planned


def report_stats(engine: MemoryEngine, title: str) -> None:
    stats = engine.stats()
    print(f"\n{title}")
    print(f"  по статусам:   {stats.get('by_status', {})}")
    print(f"  активные типы: {stats.get('active_by_type', {})}")
    print(f"  источники:     {stats.get('active_by_source', {})}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Уборка долговременной памяти")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="только показать план, ничего не менять",
    )
    args = parser.parse_args()

    engine = MemoryEngine()
    report_stats(engine, "Память до уборки:")

    planned = preview(engine)
    if planned == 0:
        print("\nПовторов нет, сворачивать нечего.")
    else:
        print(f"\nК сворачиванию: {planned}")

    if args.dry_run:
        print("\nРежим просмотра: ничего не изменено.")
        return 0

    expired = engine.purge_expired()
    merged = engine.consolidate()
    print(f"\nУдалено истекших заметок: {expired}")
    print(f"Свёрнуто повторов:        {merged}")
    report_stats(engine, "Память после уборки:")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
