#!/usr/bin/env python3
"""Run the sole production ingestion writer under a lifetime process lock."""
from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from src.brain.config import DATA_DIR
    from src.brain.knowledge.queue.worker import main as worker_main

    lock_path = Path(os.environ.get("BRAIN_INGESTION_WRITER_LOCK", str(Path(DATA_DIR) / ".ingestion-writer.lock")))
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
        worker_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
