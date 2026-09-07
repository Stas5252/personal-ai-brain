"""
Background Ingestion Worker & Daemon for Knowledge Ingestion Factory.
Pulls jobs from IngestionQueue with atomic leasing, periodic heartbeats,
stale job reclamation, checkpoint tracking, and graceful shutdown.
"""
import os
import sys
import time
import json
import uuid
import signal
import logging
import threading
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

from src.brain.db import get_connection
from src.brain.models.knowledge import IngestionJob, IngestionStatus
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.factory import KnowledgeIngestionFactory

logger = logging.getLogger("brain.knowledge.worker")

class IngestionWorker:
    """
    Ingestion Worker that processes jobs with lease management and heartbeats.
    Eliminates arbitrary code execution (no eval()) and provides resilient processing.
    """
    def __init__(
        self,
        queue: Optional[IngestionQueue] = None,
        factory: Optional[KnowledgeIngestionFactory] = None,
        worker_id: Optional[str] = None,
        lease_seconds: int = 60
    ):
        self.queue = queue or IngestionQueue()
        self.factory = factory or KnowledgeIngestionFactory()
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.lease_seconds = lease_seconds
        self._current_job_id: Optional[str] = None
        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def _start_heartbeat(self, job_id: str):
        self._stop_heartbeat.clear()
        interval = max(5.0, self.lease_seconds / 3.0)

        def _hb_loop():
            while not self._stop_heartbeat.wait(interval):
                try:
                    self.queue.heartbeat(job_id, self.worker_id, self.lease_seconds)
                except Exception as e:
                    logger.warning(f"Heartbeat failed for job {job_id}: {e}")

        self._heartbeat_thread = threading.Thread(target=_hb_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_loop(self):
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)
        self._heartbeat_thread = None

    def process_job(self, job: IngestionJob) -> bool:
        """Processes a single job with heartbeat and checkpoint tracking."""
        source_id = job.source_id
        self._current_job_id = job.job_id
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT storage_path, title, category, metadata_json FROM knowledge_sources WHERE source_id = ?", (source_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            self.queue.fail_job(job.job_id, f"Source '{source_id}' not found in database")
            self._current_job_id = None
            return False

        file_path = Path(row["storage_path"])
        if not file_path.exists():
            self.queue.fail_job(job.job_id, f"Original file not found at '{file_path}'")
            self._current_job_id = None
            return False

        self._start_heartbeat(job.job_id)
        try:
            self.queue.update_progress(job.job_id, "PROCESSING", 0.3, checkpoint_stage="EXTRACTING")

            # Parse metadata strictly via json.loads (NO eval())
            raw_meta = row["metadata_json"]
            meta: Dict[str, Any] = {}
            if raw_meta and isinstance(raw_meta, str):
                try:
                    meta = json.loads(raw_meta)
                except Exception:
                    meta = {}

            # Ingest/process through factory
            self.factory.ingest_file(
                file_path=file_path,
                title=row["title"],
                metadata=meta,
                job_id=job.job_id,
                source_id=job.source_id
            )
            self.queue.complete_job(job.job_id)
            return True
        except Exception as e:
            logger.error(f"Job {job.job_id} processing failed: {e}", exc_info=True)
            self.queue.fail_job(job.job_id, str(e))
            return False
        finally:
            self._stop_heartbeat_loop()
            self._current_job_id = None

    def process_next(self) -> bool:
        """Pulls and processes next ready job using atomic lease. Returns True if a job was processed."""
        job = self.queue.claim_job(worker_id=self.worker_id, lease_seconds=self.lease_seconds)
        if not job:
            return False
        return self.process_job(job)

    def run_batch(self, max_jobs: int = 10) -> int:
        """Processes up to max_jobs from queue."""
        processed = 0
        for _ in range(max_jobs):
            if not self.process_next():
                break
            processed += 1
        return processed


class IngestionWorkerDaemon:
    """
    Continuous daemon runner with signal management, periodic stale job recovery,
    and graceful shutdown.
    """
    def __init__(
        self,
        worker: Optional[IngestionWorker] = None,
        poll_interval: float = 2.0,
        reclaim_interval: float = 60.0
    ):
        self.worker = worker or IngestionWorker()
        self.poll_interval = poll_interval
        self.reclaim_interval = reclaim_interval
        self.running = False

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received. Initiating graceful shutdown...")
        self.running = False

    def start(self):
        """Starts the worker daemon loop."""
        self.running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info(f"Ingestion Worker Daemon started [ID: {self.worker.worker_id}]. Polling queue...")
        last_reclaim = 0.0

        while self.running:
            try:
                now = time.time()
                # Periodic stale job reclamation
                if now - last_reclaim > self.reclaim_interval:
                    reclaimed = self.worker.queue.reclaim_stale_jobs()
                    if reclaimed > 0:
                        logger.info(f"Reclaimed {reclaimed} stale/abandoned jobs for retry.")
                    last_reclaim = now

                # Claim and process
                processed = self.worker.process_next()
                if not processed:
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Daemon worker loop error: {e}", exc_info=True)
                time.sleep(self.poll_interval)

        logger.info(f"Ingestion Worker Daemon [ID: {self.worker.worker_id}] stopped cleanly.")

    def stop(self):
        self.running = False


def main():
    parser = argparse.ArgumentParser(description="Knowledge Ingestion Worker Daemon")
    parser.add_argument("--worker-id", type=str, default=None, help="Unique worker identifier")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds when idle")
    parser.add_argument("--lease-seconds", type=int, default=60, help="Job lease timeout in seconds")
    parser.add_argument("--once", action="store_true", help="Process current queue batch and exit")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for --once execution")
    parser.add_argument("--reclaim-stale", action="store_true", help="Reclaim stale jobs and exit")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
    )

    queue = IngestionQueue()
    if args.reclaim_stale:
        reclaimed = queue.reclaim_stale_jobs(stale_threshold_seconds=args.lease_seconds)
        print(f"Reclaimed {reclaimed} stale jobs.")
        sys.exit(0)

    worker = IngestionWorker(
        queue=queue,
        worker_id=args.worker_id,
        lease_seconds=args.lease_seconds
    )

    if args.once:
        print(f"Processing up to {args.batch_size} jobs...")
        processed = worker.run_batch(max_jobs=args.batch_size)
        print(f"Finished. Processed {processed} jobs.")
        sys.exit(0)

    daemon = IngestionWorkerDaemon(
        worker=worker,
        poll_interval=args.poll_interval,
        reclaim_interval=float(args.lease_seconds)
    )
    daemon.start()


if __name__ == "__main__":
    main()
