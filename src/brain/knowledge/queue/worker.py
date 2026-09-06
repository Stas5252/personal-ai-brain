"""
Background Ingestion Worker for Knowledge Ingestion Factory.
Pulls jobs from IngestionQueue and runs them through KnowledgeIngestionFactory
with checkpointing, recovery, and retry handling.
"""
import time
from pathlib import Path
from typing import Optional

from src.brain.db import get_connection
from src.brain.models.knowledge import IngestionJob, IngestionStatus
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue
from src.brain.knowledge.factory import KnowledgeIngestionFactory

class IngestionWorker:
    def __init__(self, queue: Optional[IngestionQueue] = None, factory: Optional[KnowledgeIngestionFactory] = None):
        self.queue = queue or IngestionQueue()
        self.factory = factory or KnowledgeIngestionFactory()

    def process_job(self, job: IngestionJob) -> bool:
        """Processes a single job with checkpoint tracking."""
        source_id = job.source_id
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT storage_path, title, category, metadata_json FROM knowledge_sources WHERE source_id = ?", (source_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            self.queue.fail_job(job.job_id, f"Source '{source_id}' not found in database")
            return False

        file_path = Path(row["storage_path"])
        if not file_path.exists():
            self.queue.fail_job(job.job_id, f"Original file not found at '{file_path}'")
            return False

        try:
            self.queue.update_progress(job.job_id, "PROCESSING", 0.3, checkpoint_stage="EXTRACTING")
            # Ingest/process through factory
            self.factory.ingest_file(
                file_path=file_path,
                title=row["title"],
                metadata=eval(row["metadata_json"] or "{}") if isinstance(row["metadata_json"], str) else {},
                job_id=job.job_id
            )
            self.queue.complete_job(job.job_id)
            return True
        except Exception as e:
            self.queue.fail_job(job.job_id, str(e))
            return False

    def process_next(self) -> bool:
        """Pulls and processes next ready job. Returns True if a job was processed."""
        job = self.queue.get_next_job()
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
