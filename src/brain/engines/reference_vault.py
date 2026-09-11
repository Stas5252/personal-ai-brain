"""
Хранилище визуальных референсов и листа героя.

Зачем он нужен. Движок генерации умеет держать лицо и стиль неизменными, если
ему дать набор референсов и карточку внешности. Но брать их было неоткуда:
хранить негде. Этот модуль — то самое место. Он помнит, какие фотографии
присланы, какую роль каждая играет (лицо, фигура, стиль, локация, предмет) и
что она сама сказала о своей внешности.

Правила те же, что и во всём проекте. Файл проверяется по сигнатуре байтов, а
не по расширению, поэтому скриншот с ошибкой не попадёт в набор под видом фото.
Если файл исчез с диска, запись убирается, а не всплывает тихой ошибкой во
время генерации. Незаполненное поле листа героя просто отсутствует —
выдуманных примет не бывает.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brain.db import get_connection
from src.brain.engines import visual_identity as vi
from src.brain.engines.image_engine import MAX_REFERENCE_BYTES, _looks_like_image


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_trait_key(key: str) -> str:
    return str(key or "").strip().lower().replace("ё", "е")


class ReferenceVault:
    """Набор референсов и лист героя, живущие между перезапусками бота."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path) if db_path else None
        self._ensure_tables()

    # -- infrastructure -----------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if self.db_path:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        return get_connection()

    def _ensure_tables(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS visual_references (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    note TEXT,
                    added_at TEXT NOT NULL,
                    bytes INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS character_sheet (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_visual_refs_role "
                "ON visual_references(role, added_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "path": row["path"],
            "role": row["role"],
            "note": row["note"] or "",
            "added_at": row["added_at"],
            "bytes": int(row["bytes"] or 0),
        }

    # -- references ---------------------------------------------------------
    def add_reference(
        self,
        path: str | Path,
        role: Optional[str] = None,
        note: str = "",
        added_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Кладёт фотографию в набор. Один и тот же файл не задваивается."""
        file_path = Path(str(path)).expanduser()
        if not file_path.is_file():
            raise ValueError(f"Файл не найден: {file_path.name}")
        raw = file_path.read_bytes()
        if not raw:
            raise ValueError("Файл пустой — пришли фото ещё раз.")
        if len(raw) > MAX_REFERENCE_BYTES:
            raise ValueError("Файл больше 12 МБ — сожми его и пришли снова.")
        if not _looks_like_image(raw):
            raise ValueError("Это не фотография: нужен PNG, JPEG или WebP.")

        record = {
            "id": uuid.uuid4().hex,
            "path": str(file_path),
            "role": vi.normalize_role(role),
            "note": (note or "").strip(),
            "added_at": added_at or _now(),
            "bytes": len(raw),
        }

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM visual_references WHERE path = ?", (record["path"],))
            existing = cur.fetchone()
            if existing:
                record["id"] = existing["id"]
                cur.execute(
                    "UPDATE visual_references SET role = ?, note = ?, added_at = ?, bytes = ? "
                    "WHERE id = ?",
                    (record["role"], record["note"], record["added_at"], record["bytes"], record["id"]),
                )
            else:
                cur.execute(
                    "INSERT INTO visual_references (id, path, role, note, added_at, bytes) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record["id"],
                        record["path"],
                        record["role"],
                        record["note"],
                        record["added_at"],
                        record["bytes"],
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return record

    def list_references(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        """Все референсы, свежие сверху. Роль можно отфильтровать."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            if role:
                cur.execute(
                    "SELECT * FROM visual_references WHERE role = ? ORDER BY added_at DESC",
                    (vi.normalize_role(role),),
                )
            else:
                cur.execute("SELECT * FROM visual_references ORDER BY added_at DESC")
            return [self._row_to_dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def active_references(self, limit: int = vi.MAX_REFERENCES) -> List[Dict[str, Any]]:
        """Готовый набор для генерации: лицо первым, не больше предела модели."""
        return vi.select_references(self.list_references(), limit=limit)

    def remove_reference(self, reference_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM visual_references WHERE id = ?", (str(reference_id),))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def clear_references(self, role: Optional[str] = None) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            if role:
                cur.execute("DELETE FROM visual_references WHERE role = ?", (vi.normalize_role(role),))
            else:
                cur.execute("DELETE FROM visual_references")
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def prune_missing(self) -> int:
        """Убирает записи, чьи файлы исчезли с диска. Возвращает число убранных."""
        gone = [item["id"] for item in self.list_references() if not Path(item["path"]).is_file()]
        if not gone:
            return 0
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.executemany("DELETE FROM visual_references WHERE id = ?", [(i,) for i in gone])
            conn.commit()
        finally:
            conn.close()
        return len(gone)

    # -- character sheet ----------------------------------------------------
    def set_trait(self, key: str, value: str) -> str:
        """Записывает поле листа героя. Чужие поля не принимаются."""
        normalized = _normalize_trait_key(key)
        if normalized not in vi.TRAIT_ORDER:
            allowed = ", ".join(vi.TRAIT_ORDER)
            raise ValueError(f"Такого поля нет. Доступные: {allowed}.")
        text = str(value or "").strip()
        conn = self._connect()
        try:
            cur = conn.cursor()
            if not text:
                cur.execute("DELETE FROM character_sheet WHERE key = ?", (normalized,))
            else:
                cur.execute(
                    "INSERT INTO character_sheet (key, value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "updated_at = excluded.updated_at",
                    (normalized, text, _now()),
                )
            conn.commit()
        finally:
            conn.close()
        return text

    def traits(self) -> Dict[str, str]:
        """Заполненные поля листа героя в осмысленном порядке."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM character_sheet")
            stored = {row["key"]: row["value"] for row in cur.fetchall()}
        finally:
            conn.close()
        return {key: stored[key] for key in vi.TRAIT_ORDER if stored.get(key)}

    def clear_traits(self) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM character_sheet")
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def character_sheet(self) -> str:
        return vi.character_sheet(self.traits())

    # -- reporting ----------------------------------------------------------
    def summary(self) -> str:
        """Человеческая сводка для чата: что уже есть и чего не хватает."""
        references = self.list_references()
        lines: List[str] = []
        sheet = self.character_sheet()
        lines.append(sheet if sheet else "Лист героя пока пустой.")
        if references:
            lines.append(
                f"Референсы: {vi.references_summary(references)} "
                f"(всего {len(references)}, в запрос идут первые {vi.MAX_REFERENCES})."
            )
        else:
            lines.append("Референсов пока нет — пришли фото и скажи, что на нём: лицо, стиль или локация.")
        if references and not any(r["role"] == vi.ROLE_FACE for r in references):
            lines.append("Нет ни одного референса лица — именно он сильнее всего держит схожесть.")
        return "\n".join(lines)
