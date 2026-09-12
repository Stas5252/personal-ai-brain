"""Durable knowledge ingestion worker with heartbeat and lease fencing."""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from src.brain.db import get_connection
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.models.knowledge import IngestionJob

logger = logging.getLogger("brain.knowledge.worker")


class IngestionWorker:
    def __init__(
        self,
        queue: Optional[IngestionQueue] = None,
        factory: Optional[KnowledgeIngestionFactory] = None,
        worker_id: Optional[str] = None,
        lease_seconds: int = 60,
    ):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.queue = queue or IngestionQueue()
        self.factory = factory or KnowledgeIngestionFactory()
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.lease_seconds = lease_seconds
        self._current_job: Optional[IngestionJob] = None
        self._stop_heartbeat = threading.Event()
        self._lease_lost = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def _start_heartbeat(self, job: IngestionJob) -> None:
        self._stop_heartbeat.clear()
        self._lease_lost.clear()
        interval = max(1.0, min(20.0, self.lease_seconds / 3.0))

        def _heartbeat_loop() -> None:
            while not self._stop_heartbeat.wait(interval):
                try:
                    ok = self.queue.heartbeat(
                        job.job_id,
                        self.worker_id,
                        self.lease_seconds,
                        lease_token=job.lease_token,
                    )
                    if not ok:
                        self._lease_lost.set()
                        logger.error("Lease lost for ingestion job %s", job.job_id)
                        return
                except Exception:
                    self._lease_lost.set()
                    logger.exception("Heartbeat failed for ingestion job %s", job.job_id)
                    return

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_loop(self) -> None:
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
        self._heartbeat_thread = None

    def _require_live_lease(self, job: IngestionJob) -> None:
        if self._lease_lost.is_set() or not self.queue.owns_lease(
            job.job_id, self.worker_id, job.lease_token
        ):
            self._lease_lost.set()
            raise RuntimeError("Ingestion lease was lost; stale worker is fenced")

    def _fail_owned_job(self, job: IngestionJob, message: str) -> bool:
        try:
            return self.queue.fail_job(
                job.job_id,
                message,
                self.worker_id,
                job.lease_token,
            )
        except Exception:
            logger.exception("Could not record failure for ingestion job %s", job.job_id)
            return False

    def process_job(self, job: IngestionJob) -> bool:
        """Process a claimed job; only its current token may mutate queue state."""
        if job.worker_id != self.worker_id or job.lease_token <= 0:
            raise ValueError("worker may process only a job claimed with its current lease token")
        self._current_job = job
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT storage_path, title, category, metadata_json "
                "FROM knowledge_sources WHERE source_id = ?",
                (job.source_id,),
            ).fetchone()
        finally:
            connection.close()

        if not row:
            self._fail_owned_job(job, f"Source {job.source_id!r} not found in database")
            self._current_job = None
            return False
        file_path = Path(row["storage_path"])
        if not file_path.exists():
            self._fail_owned_job(job, "Registered original file is missing from storage")
            self._current_job = None
            return False

        self._start_heartbeat(job)
        try:
            self._require_live_lease(job)
            if not self.queue.update_progress(
                job.job_id,
                "EXTRACTING",
                0.3,
                checkpoint_stage="EXTRACTING",
                worker_id=self.worker_id,
                lease_token=job.lease_token,
            ):
                raise RuntimeError("Lease lost before ingestion started")

            metadata: Dict[str, Any] = {}
            raw_metadata = row["metadata_json"]
            if raw_metadata and isinstance(raw_metadata, str):
                try:
                    parsed = json.loads(raw_metadata)
                    if isinstance(parsed, dict):
                        metadata = parsed
                except json.JSONDecodeError:
                    logger.warning("Ignoring invalid source metadata JSON for %s", job.source_id)

            # Queue state is updated only through the fenced queue API. Source
            # pipeline checkpoints remain source-local and idempotent.
            self.factory.ingest_file(
                file_path=file_path,
                title=row["title"],
                metadata=metadata,
                source_id=job.source_id,
            )
            self._require_live_lease(job)
            if not self.queue.complete_job(job.job_id, self.worker_id, job.lease_token):
                raise RuntimeError("Lease lost before completion could be committed")
            return True
        except Exception as exc:
            logger.exception("Ingestion job %s failed", job.job_id)
            self._fail_owned_job(job, str(exc))
            return False
        finally:
            self._stop_heartbeat_loop()
            self._current_job = None

    def process_next(self) -> bool:
        job = self.queue.claim_job(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if not job:
            return False
        return self.process_job(job)

    def run_batch(self, max_jobs: int = 10) -> int:
        processed = 0
        for _ in range(max_jobs):
            job = self.queue.claim_job(
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if not job:
                break
            self.process_job(job)
            processed += 1
        return processed


class IngestionWorkerDaemon:
    def __init__(
        self,
        worker: Optional[IngestionWorker] = None,
        poll_interval: float = 2.0,
        reclaim_interval: float = 60.0,
    ):
        self.worker = worker or IngestionWorker()
        self.poll_interval = max(0.1, poll_interval)
        self.reclaim_interval = max(1.0, reclaim_interval)
        self.running = False

    def _handle_signal(self, signum, frame) -> None:
        logger.info("Signal %s received; stopping after the current operation", signum)
        self.running = False

    def start(self) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        logger.info("Ingestion worker %s started", self.worker.worker_id)
        last_reclaim = 0.0
        while self.running:
            try:
                now = time.monotonic()
                if now - last_reclaim >= self.reclaim_interval:
                    reclaimed = self.worker.queue.reclaim_stale_jobs()
                    if reclaimed:
                        logger.info("Reclaimed %s expired ingestion jobs", reclaimed)
                    last_reclaim = now
                if not self.worker.process_next():
                    time.sleep(self.poll_interval)
            except Exception:
                logger.exception("Ingestion daemon loop failed")
                time.sleep(self.poll_interval)
        logger.info("Ingestion worker %s stopped", self.worker.worker_id)

    def stop(self) -> None:
        self.running = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge ingestion worker")
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--reclaim-stale", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    )
    queue = IngestionQueue()
    if args.reclaim_stale:
        print(f"Reclaimed {queue.reclaim_stale_jobs()} stale jobs.")
        return
    worker = IngestionWorker(
        queue=queue,
        worker_id=args.worker_id,
        lease_seconds=args.lease_seconds,
    )
    if args.once:
        print(f"Finished. Processed {worker.run_batch(args.batch_size)} jobs.")
        return
    IngestionWorkerDaemon(
        worker=worker,
        poll_interval=args.poll_interval,
        reclaim_interval=float(args.lease_seconds),
    ).start()


if __name__ == "__main__":
    main()
