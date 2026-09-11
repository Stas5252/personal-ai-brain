"""Outreach policy: how often the bot may write first, and when it must stay silent.

Reviews of companion bots agree on what makes people mute them: more than
four or five self-initiated messages in two weeks, a second nudge sent before
the first one was answered, and the same reminder repeated again and again.

ProactiveEngine used to build a nudge on every call, with no record of what
had already been sent and no idea whether she ever answered, so nothing in
the code prevented any of those three mistakes.

decide() is pure and testable, OutreachLedger only stores and reads rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

# Границы, за которыми забота превращается в спам.
WINDOW_DAYS = 14
MAX_PER_WINDOW = 4
MIN_HOURS_BETWEEN = 72
SAME_TYPE_COOLDOWN_DAYS = 14
MAX_UNANSWERED = 1
# Одно касание без ответа останавливает всё, но не навсегда: иначе один
# пропущенный вопрос выключил бы проактивность до конца жизни бота.
UNANSWERED_HOLD_DAYS = 7
QUIET_START = 22
QUIET_END = 9

ALLOW = "ok"
BLOCK_QUIET = "quiet_hours"
BLOCK_WAITING = "waiting_for_reply"
BLOCK_WINDOW = "window_limit"
BLOCK_TOO_SOON = "too_soon"
BLOCK_SAME_TYPE = "same_type_cooldown"


def parse_moment(value):
    """ISO text (with or without a zone) -> aware UTC datetime; None if unusable."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def within_quiet_hours(hour, start=QUIET_START, end=QUIET_END):
    """True inside the silent window, including a window that wraps midnight."""
    hour = int(hour) % 24
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


def normalize_history(history):
    """Keeps only rows with a readable timestamp, newest first."""
    rows = []
    for item in history or []:
        row = item or {}
        sent = parse_moment(row.get("sent_at") if hasattr(row, "get") else None)
        if sent is None:
            continue
        rows.append({
            "nudge_type": str(row.get("nudge_type") or ""),
            "sent_at": sent,
            "answered": bool(row.get("answered")),
        })
    rows.sort(key=lambda entry: entry["sent_at"], reverse=True)
    return rows


def decide(
    nudge_type,
    history,
    now=None,
    quiet_hour=None,
    quiet_start=QUIET_START,
    quiet_end=QUIET_END,
    max_per_window=MAX_PER_WINDOW,
    min_hours_between=MIN_HOURS_BETWEEN,
    same_type_cooldown_days=SAME_TYPE_COOLDOWN_DAYS,
    max_unanswered=MAX_UNANSWERED,
    unanswered_hold_days=UNANSWERED_HOLD_DAYS,
):
    """Returns (allowed, reason) for one proactive touch. Never raises.

    Rules, in the order a person notices them being broken:
    quiet hours -> unanswered touch -> too many in two weeks -> too soon
    after the previous one -> the same reminder again.
    """
    moment = parse_moment(now) or datetime.now(timezone.utc)
    hour = moment.hour if quiet_hour is None else int(quiet_hour)
    if within_quiet_hours(hour, quiet_start, quiet_end):
        return False, BLOCK_QUIET

    rows = normalize_history(history)
    window = [row for row in rows if row["sent_at"] >= moment - timedelta(days=WINDOW_DAYS)]

    hold_start = moment - timedelta(days=int(unanswered_hold_days))
    waiting = sum(1 for row in window if not row["answered"] and row["sent_at"] >= hold_start)
    if waiting >= int(max_unanswered):
        return False, BLOCK_WAITING

    if len(window) >= int(max_per_window):
        return False, BLOCK_WINDOW

    if rows and (moment - rows[0]["sent_at"]) < timedelta(hours=float(min_hours_between)):
        return False, BLOCK_TOO_SOON

    cooldown_start = moment - timedelta(days=int(same_type_cooldown_days))
    wanted = str(nudge_type or "")
    if any(row["nudge_type"] == wanted and row["sent_at"] >= cooldown_start for row in rows):
        return False, BLOCK_SAME_TYPE

    return True, ALLOW


class OutreachLedger:
    """Stores every self-initiated message, so the limits above are real.

    A failing database must not crash a nudge or, worse, unlock the limits:
    history() returning an empty list on error is the one case where the
    caller still decides on the strictest fresh-start assumption.
    """

    TABLE = "outreach_log"

    def __init__(self, connect=None):
        self._connect = connect

    def _open(self):
        if self._connect is not None:
            return self._connect()
        from src.brain.db import get_connection
        return get_connection()

    def _ensure(self, conn):
        conn.cursor().execute(
            f"CREATE TABLE IF NOT EXISTS {self.TABLE} ("
            "id TEXT PRIMARY KEY, nudge_type TEXT, message TEXT, sent_at TEXT, answered INTEGER DEFAULT 0)"
        )

    @staticmethod
    def _row(row):
        if hasattr(row, "keys"):
            return {
                "nudge_type": row["nudge_type"],
                "message": row["message"],
                "sent_at": row["sent_at"],
                "answered": bool(row["answered"]),
            }
        return {"nudge_type": row[0], "message": row[1], "sent_at": row[2], "answered": bool(row[3])}

    def history(self, days=WINDOW_DAYS):
        try:
            conn = self._open()
            self._ensure(conn)
            since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
            cur = conn.cursor()
            cur.execute(
                f"SELECT nudge_type, message, sent_at, answered FROM {self.TABLE} "
                "WHERE sent_at >= ? ORDER BY sent_at DESC",
                (since,),
            )
            rows = [self._row(item) for item in cur.fetchall()]
            conn.commit()
            conn.close()
            return rows
        except Exception:
            return []

    def record(self, nudge_type, message, now=None):
        moment = parse_moment(now) or datetime.now(timezone.utc)
        try:
            conn = self._open()
            self._ensure(conn)
            conn.cursor().execute(
                f"INSERT INTO {self.TABLE} (id, nudge_type, message, sent_at, answered) VALUES (?, ?, ?, ?, 0)",
                (str(uuid.uuid4()), str(nudge_type or ""), str(message or "")[:2000], moment.isoformat()),
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def mark_answered(self):
        """Her reply closes every open touch; returns how many were closed."""
        try:
            conn = self._open()
            self._ensure(conn)
            cur = conn.cursor()
            cur.execute(f"UPDATE {self.TABLE} SET answered = 1 WHERE answered = 0")
            changed = int(cur.rowcount or 0)
            conn.commit()
            conn.close()
            return changed
        except Exception:
            return 0

    def summary(self, days=WINDOW_DAYS):
        rows = self.history(days=days)
        return {
            "window_days": int(days),
            "limit": MAX_PER_WINDOW,
            "sent": len(rows),
            "unanswered": sum(1 for row in rows if not row["answered"]),
            "last_sent": rows[0]["sent_at"] if rows else None,
            "last_type": rows[0]["nudge_type"] if rows else None,
        }
