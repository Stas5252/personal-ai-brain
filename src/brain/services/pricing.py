"""Parsing of money amounts supplied by the user.

The bot must never invent a price. A photographer takes real business
decisions from these numbers, so a fabricated base price is strictly worse
than refusing to answer. Every function here returns a number the user
actually typed, or raises.

Pure stdlib on purpose: this is the one piece of pricing logic that has to be
testable without the database, the LLM or the vector store.
"""
from __future__ import annotations

import re

__all__ = [
    "MAX_REASONABLE_PRICE",
    "MIN_REASONABLE_PRICE",
    "PriceNotFound",
    "format_money",
    "parse_base_price",
]

# A shoot cheaper than this is almost certainly a typo or a quantity, and
# anything above the ceiling is a phone number or an order id rather than a
# base price. Both bounds only decide whether we ask again; they never adjust
# the number itself.
MIN_REASONABLE_PRICE = 500
MAX_REASONABLE_PRICE = 5_000_000

ASK_FOR_PRICE = (
    "Не вижу базовой цены. Напиши число \u2014 например \u00ab15000\u00bb, "
    "\u00ab15 000 \u20bd\u00bb или \u00ab15\u043a\u00bb.\n"
    "Цену за тебя я не придумываю: прайс на выдуманной базе \u2014 это "
    "потерянные деньги или отпугнутый клиент."
)

# Thin and non-breaking spaces are what you get when a price is pasted out of
# a web page or an existing price list, so they must count as separators.
_ODD_SPACES = "\u00a0\u202f\u2009\u2007"

_NUMBER = re.compile(
    r"(?P<number>\d{1,3}(?:[ .,]\d{3})+|\d+)"
    r"(?P<multiplier>\s*(?:\u043a\b|k\b|\u0442\u044b\u0441\.?|\u0442\u044b\u0441\u044f\u0447[\u0430\u0438\u0443]?))?",
    re.IGNORECASE,
)

_CURRENCY_AFTER = re.compile(
    r"^\s*(?:\u20bd|\u0440\u0443\u0431\.?|\u0440\u0443\u0431\u043b\u0435\u0439|\u0440\u0443\u0431\u043b\u044f|\u0440\.|rub|\u20b8|\u0442\u0435\u043d\u0433\u0435|\u0433\u0440\u043d)",
    re.IGNORECASE,
)

_PRICE_WORD_BEFORE = re.compile(
    r"(?:\u20bd|\u0446\u0435\u043d\u0430|\u0446\u0435\u043d\u0443|\u043f\u0440\u0430\u0439\u0441|\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c|\u0447\u0435\u043a|\u0431\u0430\u0437\u0430|\u0431\u0430\u0437\u043e\u0432\u0430\u044f|\u043e\u0442|\u0437\u0430)\s*$",
    re.IGNORECASE,
)

# Dates and phone numbers are the two things people paste that look like money
# but never are.
_DATE = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}")
_PHONE = re.compile(r"(?:\+?\d[\s\-()]?){10,}")


class PriceNotFound(ValueError):
    """Raised when the text holds no number that can be trusted as a price."""


def format_money(value: int) -> str:
    """Render an amount the way a Russian price list does: 15 000 \u20bd."""
    return f"{int(value):,} \u20bd".replace(",", "\u00a0")


def _normalise(text: str) -> str:
    for char in _ODD_SPACES:
        text = text.replace(char, " ")
    return text


def _blocked_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in (_DATE, _PHONE):
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return spans


def parse_base_price(text: str) -> int:
    """Return the base price stated in ``text``.

    Raises :class:`PriceNotFound` when the user did not state one. Callers must
    surface that as a question, never as a default.
    """
    cleaned = _normalise(text or "")
    if not cleaned.strip():
        raise PriceNotFound(ASK_FOR_PRICE)

    blocked = _blocked_spans(cleaned)
    best: tuple[int, int] | None = None

    for match in _NUMBER.finditer(cleaned):
        start, end = match.span("number")
        if any(begin <= start < finish for begin, finish in blocked):
            continue

        digits = re.sub(r"[ .,]", "", match.group("number"))
        if not digits.isdigit():
            continue

        value = int(digits)
        multiplier = match.group("multiplier")
        if multiplier:
            value *= 1000
        if not MIN_REASONABLE_PRICE <= value <= MAX_REASONABLE_PRICE:
            continue

        has_currency = bool(_CURRENCY_AFTER.match(cleaned[match.end():])) or bool(
            _PRICE_WORD_BEFORE.search(cleaned[:start])
        )
        # An amount carrying a currency sign beats a bare number, and a bare
        # number still beats nothing. Ties keep the first mention, which is how
        # people write "base 15000, premium 30000".
        score = (2 if has_currency else 0) + (1 if multiplier else 0)
        if best is None or score > best[0]:
            best = (score, value)

    if best is None:
        raise PriceNotFound(ASK_FOR_PRICE)
    return best[1]
