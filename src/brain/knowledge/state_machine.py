"""
Processing State Machine for Knowledge Ingestion Factory.
Manages 14 distinct states, idempotency checkpoints, and recoverable transitions.
"""
from typing import Optional, Set
from datetime import datetime, timezone
from src.brain.models.knowledge import IngestionStatus
from src.brain.db import get_connection

VALID_TRANSITIONS = {
    IngestionStatus.DISCOVERED: {IngestionStatus.VALIDATING, IngestionStatus.SKIPPED, IngestionStatus.DUPLICATE, IngestionStatus.FAILED},
    IngestionStatus.VALIDATING: {IngestionStatus.EXTRACTING, IngestionStatus.FAILED, IngestionStatus.SKIPPED, IngestionStatus.DUPLICATE},
    IngestionStatus.EXTRACTING: {IngestionStatus.NORMALIZING, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.NORMALIZING: {IngestionStatus.CLASSIFYING, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.CLASSIFYING: {IngestionStatus.CHUNKING, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.CHUNKING: {IngestionStatus.EMBEDDING, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.EMBEDDING: {IngestionStatus.INDEXING, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.INDEXING: {IngestionStatus.VERIFYING, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.VERIFYING: {IngestionStatus.COMPLETED, IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING},
    IngestionStatus.COMPLETED: {IngestionStatus.DISCOVERED}, # Allows reprocess
    IngestionStatus.FAILED: {IngestionStatus.RETRY_PENDING, IngestionStatus.DISCOVERED},
    IngestionStatus.RETRY_PENDING: {IngestionStatus.VALIDATING, IngestionStatus.EXTRACTING, IngestionStatus.CHUNKING, IngestionStatus.FAILED},
    IngestionStatus.SKIPPED: {IngestionStatus.DISCOVERED},
    IngestionStatus.DUPLICATE: {IngestionStatus.DISCOVERED}
}

class IngestionStateMachine:
    def __init__(self, source_id: str, job_id: Optional[str] = None):
        self.source_id = source_id
        self.job_id = job_id

    def get_current_status(self) -> IngestionStatus:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT ingestion_status FROM knowledge_sources WHERE source_id = ?", (self.source_id,))
        row = c.fetchone()
        conn.close()
        if not row or not row["ingestion_status"]:
            return IngestionStatus.DISCOVERED
        return IngestionStatus(row["ingestion_status"])

    @property
    def current_status(self) -> IngestionStatus:
        return self.get_current_status()

    def transition(self, target_status: IngestionStatus, error_message: Optional[str] = None, progress: Optional[float] = None) -> IngestionStatus:
        current = self.get_current_status()
        allowed = VALID_TRANSITIONS.get(current, set())
        
        # Permit idempotent self-transition or transition to FAILED from any stage
        if target_status != current and target_status not in allowed and target_status != IngestionStatus.FAILED:
            raise ValueError(f"Illegal state transition from {current.value} to {target_status.value} for source {self.source_id}")

        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        c = conn.cursor()

        # Upsert knowledge_sources record
        c.execute("""
        INSERT INTO knowledge_sources (source_id, title, category, ingestion_status, checkpoint_stage, error_message, timestamp, mime_type, file_size, sha256)
        VALUES (?, ?, 'GLOBAL', ?, ?, ?, ?, 'text/plain', 0, '')
        ON CONFLICT(source_id) DO UPDATE SET
            ingestion_status = excluded.ingestion_status,
            checkpoint_stage = excluded.checkpoint_stage,
            error_message = excluded.error_message,
            timestamp = excluded.timestamp
        """, (self.source_id, self.source_id, target_status.value, target_status.value, error_message, now_str))

        # Update ingestion_jobs record if job_id is bound
        if self.job_id:
            prog_val = progress if progress is not None else (1.0 if target_status == IngestionStatus.COMPLETED else 0.5)
            c.execute("""
            UPDATE ingestion_jobs
            SET status = ?, stage = ?, checkpoint_stage = ?, error_message = ?, progress = ?, updated_at = ?
            WHERE job_id = ?
            """, (target_status.value, target_status.value, target_status.value, error_message, prog_val, now_str, self.job_id))

        if progress is not None:
            self._last_progress = progress

        conn.commit()
        conn.close()
        return target_status

    def get_checkpoint(self) -> Dict[str, Any]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT checkpoint_stage, ingestion_status FROM knowledge_sources WHERE source_id = ?", (self.source_id,))
        row = c.fetchone()
        prog = getattr(self, "_last_progress", 0.0)
        if self.job_id:
            c.execute("SELECT progress FROM ingestion_jobs WHERE job_id = ?", (self.job_id,))
            j_row = c.fetchone()
            if j_row and j_row["progress"] is not None:
                prog = j_row["progress"]
        conn.close()
        stage = row["checkpoint_stage"] if row and row["checkpoint_stage"] else (row["ingestion_status"] if row else "DISCOVERED")
        return {"stage": stage, "progress": prog}

    def can_resume(self) -> Tuple[bool, Optional[IngestionStatus]]:
        """Checks if a failed or interrupted job has a valid checkpoint to resume from."""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT ingestion_status, checkpoint_stage FROM knowledge_sources WHERE source_id = ?", (self.source_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return False, None

        status = IngestionStatus(row["ingestion_status"])
        checkpoint = row["checkpoint_stage"]

        if status in [IngestionStatus.FAILED, IngestionStatus.RETRY_PENDING] and checkpoint:
            try:
                cp_status = IngestionStatus(checkpoint)
                return True, cp_status
            except ValueError:
                return False, None
        return False, None
