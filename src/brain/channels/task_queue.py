"""One background worker so a slow answer never freezes the update loop.

The polling loop reads Telegram updates in a single thread. Generating a photo
takes up to two minutes, and while that ran inside the loop nothing new was
read: from the chat it simply looked like the bot had died. Heavy work is
therefore handed to a worker thread and the loop keeps reading.

The worker is deliberately single and FIFO. Two messages from the same person
still get answered in the order they were sent, and two jobs never write the
same profile or memory row at the same time.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

LOGGER = logging.getLogger(__name__)


class SerialWorker:
    """FIFO background executor with one thread and no silent job loss."""

    def __init__(self, name: str = "brain-worker", logger: Optional[logging.Logger] = None) -> None:
        self._name = name
        self._log = logger or LOGGER
        self._queue: "queue.Queue[Optional[tuple[Callable[..., Any], tuple, dict]]]" = queue.Queue()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                func, args, kwargs = item
                try:
                    func(*args, **kwargs)
                except Exception:
                    # One failed job must never take the worker down with it:
                    # the next message still has to be answered.
                    self._log.exception("background job failed in %s", self._name)
            finally:
                self._queue.task_done()

    def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Queues a job and starts the worker if it is not running yet."""
        self._queue.put((func, args, kwargs))
        self._ensure_thread()

    def pending(self) -> int:
        """Jobs queued or running right now."""
        try:
            return int(self._queue.unfinished_tasks)
        except AttributeError:  # pragma: no cover - defensive
            return int(self._queue.qsize())

    def busy(self) -> bool:
        return self.pending() > 0

    def join(self, timeout: Optional[float] = None) -> bool:
        """Waits until the queue is drained. Returns False on timeout."""
        deadline = None if timeout is None else time.monotonic() + float(timeout)
        while self.pending():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True

    def stop(self, timeout: Optional[float] = 2.0) -> None:
        """Asks the worker to finish the queue and exit."""
        with self._lock:
            thread = self._thread
        if thread is None:
            return
        self._queue.put(None)
        thread.join(timeout=timeout)
        with self._lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None
