#!/usr/bin/env python3
"""Run the sole production ingestion writer with lock and process heartbeat."""
from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class WorkerHeartbeat:
    def __init__(self, path: Path, interval_seconds: float = 5.0):
        self.path = path
        self.interval_seconds = max(1.0, interval_seconds)
        self.pid = os.getpid()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _write(self) -> None:
        payload = {
            "service": "knowledge_worker",
            "pid": self.pid,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = self.path.with_name(f"{self.path.name}.{self.pid}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._write()

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval_seconds + 1.0)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if int(payload.get("pid", -1)) == self.pid:
                self.path.unlink(missing_ok=True)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass


def main() -> int:
    from src.brain.config import DATA_DIR
    from src.brain.health import WORKER_HEARTBEAT_FILENAME
    from src.brain.knowledge.queue.worker import main as worker_main

    lock_path = Path(os.environ.get("BRAIN_INGESTION_WRITER_LOCK", str(Path(DATA_DIR) / ".ingestion-writer.lock")))
    heartbeat_path = Path(DATA_DIR) / WORKER_HEARTBEAT_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"Another ingestion writer owns {lock_path}; refusing startup.", file=sys.stderr)
            return 73
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        with WorkerHeartbeat(heartbeat_path):
            worker_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
