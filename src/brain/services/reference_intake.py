"""Разбор подписи к фото и сохранение референса на диск.

Три решения, которые здесь важнее кода:

1. Раннер удаляет временный файл сразу после ответа, поэтому фото копируется
   в постоянную папку и называется по содержимому. Иначе в базе осталась бы
   ссылка на уже удалённый путь.
2. Роль кадра называет человек, а не алгоритм. Если в подписи нет слова о роли,
   бот переспрашивает, а не угадывает: ошибка в роли тихо испортит все
   следующие генерации.
3. Конфиг импортируется внутри функции, чтобы разбор подписи работал без
   настроенного окружения — его проверяют тесты, где нет ни .env, ни папок.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.brain.engines import visual_identity as vi

# Базовые слова берутся из того же словаря, что и у движка личности: тест
# сверяет каждое из них с vi.normalize_role, чтобы два списка не разъехались.
_ROLE_BASES: Dict[str, str] = {
    "лицо": vi.ROLE_FACE,
    "портрет": vi.ROLE_FACE,
    "герой": vi.ROLE_FACE,
    "face": vi.ROLE_FACE,
    "фигура": vi.ROLE_BODY,
    "осанка": vi.ROLE_BODY,
    "рост": vi.ROLE_BODY,
    "body": vi.ROLE_BODY,
    "стиль": vi.ROLE_STYLE,
    "цвет": vi.ROLE_STYLE,
    "палитра": vi.ROLE_STYLE,
    "одежда": vi.ROLE_STYLE,
    "style": vi.ROLE_STYLE,
    "локация": vi.ROLE_LOCATION,
    "фон": vi.ROLE_LOCATION,
    "место": vi.ROLE_LOCATION,
    "location": vi.ROLE_LOCATION,
    "предмет": vi.ROLE_PROP,
    "реквизит": vi.ROLE_PROP,
    "prop": vi.ROLE_PROP,
}

# Формы перечислены руками нарочно. Стеммер здесь давал бы ложные
# срабатывания: «фонарь» превратился бы в «фон» и уехал в локации.
_ROLE_FORMS: Dict[str, str] = {
    "лица": vi.ROLE_FACE,
    "лице": vi.ROLE_FACE,
    "лицом": vi.ROLE_FACE,
    "портрета": vi.ROLE_FACE,
    "портретом": vi.ROLE_FACE,
    "героя": vi.ROLE_FACE,
    "героем": vi.ROLE_FACE,
    "фигуру": vi.ROLE_BODY,
    "фигуры": vi.ROLE_BODY,
    "фигурой": vi.ROLE_BODY,
    "осанку": vi.ROLE_BODY,
    "осанки": vi.ROLE_BODY,
    "роста": vi.ROLE_BODY,
    "стиля": vi.ROLE_STYLE,
    "стиле": vi.ROLE_STYLE,
    "стилем": vi.ROLE_STYLE,
    "цвета": vi.ROLE_STYLE,
    "цветом": vi.ROLE_STYLE,
    "палитру": vi.ROLE_STYLE,
    "палитры": vi.ROLE_STYLE,
    "одежду": vi.ROLE_STYLE,
    "одежды": vi.ROLE_STYLE,
    "локацию": vi.ROLE_LOCATION,
    "локации": vi.ROLE_LOCATION,
    "локацией": vi.ROLE_LOCATION,
    "фоне": vi.ROLE_LOCATION,
    "фона": vi.ROLE_LOCATION,
    "фоном": vi.ROLE_LOCATION,
    "места": vi.ROLE_LOCATION,
    "месте": vi.ROLE_LOCATION,
    "предмета": vi.ROLE_PROP,
    "предметы": vi.ROLE_PROP,
    "предметом": vi.ROLE_PROP,
    "реквизита": vi.ROLE_PROP,
    "реквизитом": vi.ROLE_PROP,
}

ROLE_WORDS: Dict[str, str] = {**_ROLE_BASES, **_ROLE_FORMS}

# Двоеточие стоит первым специально: иначе «волосы: русые до-плеч»
# разорвётся по дефису внутри значения.
TRAIT_SEPARATORS: Tuple[str, ...] = (":", "\u2014", "\u2013", "=", "-")

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_KEY_TRIM = re.compile(r"^[\s\u2022*\-\u2013\u2014\d.)]+")
_NOTE_TRIM = re.compile(r"^[\s,.;:\u2014\u2013\-]+|[\s,.;:\u2014\u2013\-]+$")
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _fold(text: str) -> str:
    return str(text or "").strip().lower().replace("ё", "е")


def _words(text: str) -> List[str]:
    return _WORD.findall(_fold(text))


def detect_role(caption: str = "") -> Optional[str]:
    """Роль из подписи или None, если человек её не назвал."""
    for word in _words(caption):
        role = ROLE_WORDS.get(word)
        if role:
            return role
    return None


def reference_note(caption: str = "") -> str:
    """Подпись без служебного слова роли: остаётся только то, что сказал автор."""
    raw = str(caption or "").strip()
    if not raw:
        return ""
    kept = []
    for chunk in re.split(r"([^\W\d_]+)", raw, flags=re.UNICODE):
        if chunk and _fold(chunk) in ROLE_WORDS:
            continue
        kept.append(chunk)
    note = re.sub(r"\s+", " ", "".join(kept)).strip()
    return _NOTE_TRIM.sub("", note).strip()


def role_prompt() -> str:
    labels = ", ".join(f"«{vi.ROLE_LABELS[role]}»" for role in vi.ROLE_ORDER)
    return (
        "Не понял, что на кадре важно. Пришли фото ещё раз и подпиши одним словом: "
        f"{labels}. Можно добавить заметку через запятую."
    )


def trait_prompt() -> str:
    return (
        "Напиши приметы парами «поле: значение», по одной в строке или через точку с запятой. "
        f"Доступные поля: {', '.join(vi.TRAIT_ORDER)}."
    )


def _split_pair(line: str) -> Optional[Tuple[str, str]]:
    text = str(line or "").strip()
    if not text:
        return None
    for separator in TRAIT_SEPARATORS:
        if separator in text:
            key, _, value = text.partition(separator)
            key = _fold(_KEY_TRIM.sub("", key))
            value = value.strip()
            if key and value:
                return key, value[: vi.MAX_SHEET_CHARS]
            return None
    return None


def parse_traits(text: str = "") -> Tuple[Dict[str, str], List[str]]:
    """Возвращает принятые поля и чужие ключи — молча ничего не теряется."""
    accepted: Dict[str, str] = {}
    unknown: List[str] = []
    for line in re.split(r"[\n;]+", str(text or "")):
        pair = _split_pair(line)
        if not pair:
            continue
        key, value = pair
        if key in vi.TRAIT_ORDER:
            accepted[key] = value
        elif key not in unknown:
            unknown.append(key)
    return accepted, unknown


def references_dir() -> Path:
    """Папка референсов; переопределяется BRAIN_REFERENCES_DIR."""
    from src.brain.config import DERIVED_DIR

    custom = os.getenv("BRAIN_REFERENCES_DIR", "").strip()
    target = Path(custom) if custom else Path(DERIVED_DIR) / "references"
    target.mkdir(parents=True, exist_ok=True)
    return target


def store_reference_file(source, target_dir=None) -> Path:
    """Копирует фото в постоянную папку под именем по содержимому."""
    src = Path(str(source))
    if not src.is_file():
        raise ValueError(f"Файл не найден: {src.name}")
    raw = src.read_bytes()
    if not raw:
        raise ValueError("Файл пустой — пришли фото ещё раз.")
    suffix = src.suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        suffix = ".jpg"
    folder = Path(target_dir) if target_dir else references_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"ref-{hashlib.sha256(raw).hexdigest()[:32]}{suffix}"
    if not target.exists():
        target.write_bytes(raw)
    return target


__all__ = [
    "ROLE_WORDS",
    "detect_role",
    "parse_traits",
    "reference_note",
    "references_dir",
    "role_prompt",
    "store_reference_file",
    "trait_prompt",
]
