"""
Визуальная личность: один и тот же человек и один и тот же взгляд от кадра к кадру.

Зачем этот модуль существует. Генератор изображений не помнит прошлый кадр.
Если просто отправить ему текст, в каждом новом фото будет другое лицо, другая
длина волос и другая палитра — лента рассыпается. Модуль делает три вещи:

1. Собирает лист героя — короткое описание внешности, которое повторяется
   в каждом запросе. В лист попадает только то, что она сказала сама:
   придуманных примет здесь не бывает.
2. Упорядочивает референсы: сначала лицо, потом фигура, потом стиль и локация,
   и не больше 14 штук — столько модель реально учитывает.
3. Проверяет готовый кадр детерминированно и готовит усиленный промпт для
   одного повтора, если пришла заглушка вместо фото или вежливый отказ.

Модуль чистый: только stdlib, без сети и без базы, чтобы каждое правило
проверялось тестами без ключей и окружения.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# Предел модели по числу референсов в одном запросе.
MAX_REFERENCES = 14
# Кадр легче 30 КБ практически всегда пустой или превью.
MIN_IMAGE_BYTES = 30 * 1024
MAX_SHEET_CHARS = 600

ROLE_FACE = "face"
ROLE_BODY = "body"
ROLE_STYLE = "style"
ROLE_LOCATION = "location"
ROLE_PROP = "prop"
ROLE_ORDER = (ROLE_FACE, ROLE_BODY, ROLE_STYLE, ROLE_LOCATION, ROLE_PROP)
DEFAULT_ROLE = ROLE_STYLE

ROLE_LABELS: Dict[str, str] = {
    ROLE_FACE: "лицо",
    ROLE_BODY: "фигура и осанка",
    ROLE_STYLE: "стиль и цвет",
    ROLE_LOCATION: "локация",
    ROLE_PROP: "предметы",
}

_ROLE_ALIASES: Dict[str, str] = {
    "лицо": ROLE_FACE, "портрет": ROLE_FACE, "герой": ROLE_FACE, "face": ROLE_FACE,
    "фигура": ROLE_BODY, "осанка": ROLE_BODY, "рост": ROLE_BODY, "body": ROLE_BODY,
    "стиль": ROLE_STYLE, "цвет": ROLE_STYLE, "палитра": ROLE_STYLE, "одежда": ROLE_STYLE,
    "style": ROLE_STYLE,
    "локация": ROLE_LOCATION, "фон": ROLE_LOCATION, "место": ROLE_LOCATION,
    "location": ROLE_LOCATION,
    "предмет": ROLE_PROP, "реквизит": ROLE_PROP, "prop": ROLE_PROP,
}

# В лист героя попадают только эти поля и только если она их заполнила.
TRAIT_ORDER = ("герой", "возраст", "волосы", "глаза", "телосложение", "одежда", "приметы")
TRAIT_LABELS: Dict[str, str] = {
    "герой": "кто в кадре",
    "возраст": "возраст",
    "волосы": "волосы",
    "глаза": "глаза",
    "телосложение": "телосложение",
    "одежда": "обычная одежда",
    "приметы": "особые приметы",
}

IDENTITY_MARKER = "Один и тот же человек во всех кадрах"

FINDING_NO_IMAGE = "no_image"
FINDING_TOO_SMALL = "too_small"
FINDING_REFUSAL_TEXT = "model_refused_in_text"
FINDING_IDENTITY_MISSING = "identity_not_locked"
FINDING_ASPECT_MISSING = "aspect_not_requested"

FINDING_LABELS: Dict[str, str] = {
    FINDING_NO_IMAGE: "изображение не вернулось",
    FINDING_TOO_SMALL: "файл подозрительно маленький",
    FINDING_REFUSAL_TEXT: "модель ответила отказом в тексте",
    FINDING_IDENTITY_MISSING: "внешность не зафиксирована в промпте",
    FINDING_ASPECT_MISSING: "соотношение сторон потерялось",
}

_RETRYABLE = {
    FINDING_TOO_SMALL,
    FINDING_REFUSAL_TEXT,
    FINDING_IDENTITY_MISSING,
    FINDING_ASPECT_MISSING,
}

_REFUSAL_MARKERS = (
    "не могу", "не смогу", "не получилось", "не смогла", "не буду",
    "i cannot", "i can't", "cannot create", "unable to", "i'm sorry", "i am sorry",
)


def normalize_role(value: Optional[str]) -> str:
    """Приводит роль референса к одному из известных значений."""
    raw = (value or "").strip().lower().replace("ё", "е")
    if raw in ROLE_ORDER:
        return raw
    return _ROLE_ALIASES.get(raw, DEFAULT_ROLE)


def character_sheet(traits: Optional[Dict[str, Any]], max_chars: int = MAX_SHEET_CHARS) -> str:
    """
    Лист героя из её собственных слов.

    Неизвестные ключи и пустые значения молча отбрасываются: лучше короткий
    лист, чем выдуманные приметы в каждом кадре.
    """
    if not traits:
        return ""
    parts: List[str] = []
    for key in TRAIT_ORDER:
        value = str(traits.get(key) or "").strip()
        if not value:
            continue
        parts.append(f"{TRAIT_LABELS[key]} — {value}")
    if not parts:
        return ""
    sheet = "Лист героя: " + "; ".join(parts) + "."
    if len(sheet) <= max_chars:
        return sheet
    return sheet[: max_chars - 1].rstrip(" ;,") + "."


def identity_lock(sheet: str = "", roles: Optional[Sequence[str]] = None) -> str:
    """Блок промпта, который держит внешность неизменной."""
    sheet = (sheet or "").strip()
    role_names = [ROLE_LABELS[r] for r in ROLE_ORDER if roles and r in set(roles)]
    if not sheet and not role_names:
        return ""
    lines = [
        IDENTITY_MARKER
        + ": не меняй черты лица, разрез глаз, форму бровей, овал лица, "
        "цвет и длину волос."
    ]
    if sheet:
        lines.append(sheet)
    if role_names:
        lines.append(
            "Референсы — источник внешности и стиля (" + ", ".join(role_names)
            + "), а не сюжета: композицию и действие бери из брифа."
        )
    return "\n".join(lines)


def select_references(
    items: Optional[Sequence[Dict[str, Any]]],
    limit: int = MAX_REFERENCES,
) -> List[Dict[str, Any]]:
    """
    Отбирает референсы в том порядке, в котором их важно показать модели.

    Сначала лицо, потом фигура, потом стиль, локация и предметы; внутри роли —
    свежие выше. Дубли по пути убираются, список режется по пределу модели.
    """
    if not items:
        return []
    cap = max(0, min(int(limit or 0), MAX_REFERENCES))
    if cap == 0:
        return []

    pool: List[Dict[str, Any]] = []
    seen: set = set()
    for index, item in enumerate(items):
        path = str((item or {}).get("path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        pool.append(
            {
                "path": path,
                "role": normalize_role((item or {}).get("role")),
                "added_at": str((item or {}).get("added_at") or ""),
                "_index": index,
            }
        )

    pool.sort(key=lambda p: (p["added_at"], -p["_index"]), reverse=True)
    pool.sort(key=lambda p: ROLE_ORDER.index(p["role"]))
    return [{k: v for k, v in p.items() if k != "_index"} for p in pool[:cap]]


def references_summary(items: Optional[Sequence[Dict[str, Any]]]) -> str:
    """Человеческая строка вида «лицо — 3, стиль и цвет — 5»."""
    counts: Dict[str, int] = {}
    for item in items or []:
        role = normalize_role((item or {}).get("role"))
        counts[role] = counts.get(role, 0) + 1
    parts = [f"{ROLE_LABELS[r]} — {counts[r]}" for r in ROLE_ORDER if counts.get(r)]
    return ", ".join(parts)


def qa_findings(
    result: Optional[Dict[str, Any]],
    prompt: str = "",
    references: int = 0,
    aspect_ratio: Optional[str] = None,
) -> List[str]:
    """
    Честная проверка готового кадра без сети и без второй модели.

    Мы не делаем вид, что судим красоту снимка. Мы ловим то, что точно плохо:
    кадра нет, файл пустой, модель ответила отказом текстом, внешность не
    зафиксирована при наличии референсов, соотношение сторон потерялось.
    """
    findings: List[str] = []
    payload = result or {}
    if str(payload.get("status") or "").upper() != "AVAILABLE" or not payload.get("image_path"):
        return [FINDING_NO_IMAGE]

    size = payload.get("bytes")
    try:
        size_value = int(size)
    except (TypeError, ValueError):
        size_value = 0
    if size_value and size_value < MIN_IMAGE_BYTES:
        findings.append(FINDING_TOO_SMALL)

    notes = str(payload.get("notes") or "").lower()
    if notes and any(marker in notes for marker in _REFUSAL_MARKERS):
        findings.append(FINDING_REFUSAL_TEXT)

    text = prompt or str(payload.get("prompt") or "")
    if references > 0 and IDENTITY_MARKER not in text:
        findings.append(FINDING_IDENTITY_MISSING)

    if aspect_ratio and aspect_ratio not in text:
        findings.append(FINDING_ASPECT_MISSING)

    return findings


def should_retry(findings: Optional[Sequence[str]]) -> bool:
    """Повтор имеет смысл только там, где его может исправить текст промпта."""
    return any(f in _RETRYABLE for f in (findings or []))


def explain_findings(findings: Optional[Sequence[str]]) -> str:
    """Человеческое объяснение для чата и логов."""
    labels = [FINDING_LABELS.get(f, f) for f in (findings or [])]
    return ", ".join(labels)


def strengthen_prompt(
    prompt: str,
    findings: Optional[Sequence[str]] = None,
    sheet: str = "",
    aspect_ratio: Optional[str] = None,
) -> str:
    """Готовит промпт для одного повтора: добавляет ровно то, чего не хватило."""
    base = (prompt or "").strip()
    found = set(findings or [])
    additions: List[str] = []

    if FINDING_IDENTITY_MISSING in found:
        lock = identity_lock(sheet, roles=[ROLE_FACE])
        if lock:
            additions.append(lock)
    if FINDING_TOO_SMALL in found:
        additions.append(
            "Отдай полноценный кадр в максимальном доступном разрешении, без превью и без пустого поля."
        )
    if FINDING_REFUSAL_TEXT in found:
        additions.append(
            "Сцена бытовая и безопасная: обычная фотосъёмка в одежде, без обнажённости, "
            "без брендов и без реальных знаменитостей."
        )
    if FINDING_ASPECT_MISSING in found and aspect_ratio:
        additions.append(f"Соотношение сторон: {aspect_ratio}.")

    fresh = [line for line in additions if line and line not in base]
    if not fresh:
        return base
    return (base + "\n" + "\n".join(fresh)).strip()
