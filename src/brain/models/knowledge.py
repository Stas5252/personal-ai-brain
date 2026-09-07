"""
Knowledge Models for Hierarchical RAG and Traceability.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class KnowledgeLayer(str, Enum):
    GLOBAL = "GLOBAL"
    PROFESSIONAL = "PROFESSIONAL"
    PERSONAL = "PERSONAL"
    BUSINESS = "BUSINESS"
    PROJECT = "PROJECT"
    CLIENT = "CLIENT"

class HallucinationType(str, Enum):
    GROUNDED = "grounded"
    INFERENCE = "inference"
    GENERAL_KNOWLEDGE = "general_knowledge"
    UNKNOWN = "unknown"

class IngestionStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    NORMALIZING = "NORMALIZING"
    CLASSIFYING = "CLASSIFYING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    SKIPPED = "SKIPPED"
    DUPLICATE = "DUPLICATE"

class ContentType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    OCR = "ocr"
    VISION_DESCRIPTION = "vision_description"
    TRANSCRIPT = "transcript"
    FUSION = "fusion"

class ClassificationMethod(str, Enum):
    RULES = "rules"
    METADATA = "metadata"
    LLM = "llm"
    MANUAL = "manual"
    REVIEW_REQUIRED = "review_required"

class KnowledgeSource(BaseModel):
    source_id: str
    original_filename: str
    mime_type: str
    file_size: int
    sha256: str
    p_hash: Optional[str] = None
    storage_path: Optional[str] = None
    derived_dir: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ingestion_status: IngestionStatus = IngestionStatus.DISCOVERED
    processing_version: str = "v1.0"
    source_type: str = "document" # document, image, audio, video, url
    layer: KnowledgeLayer = KnowledgeLayer.GLOBAL
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    classification_method: ClassificationMethod = ClassificationMethod.RULES
    seen_count: int = 1
    checkpoint_stage: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def status(self) -> IngestionStatus:
        return self.ingestion_status

class KnowledgeMetadata(BaseModel):
    source_id: str
    title: str
    author: Optional[str] = "Owner"
    date: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    type: str = "document"  # document, table, video, audio, image, chat_note
    category: KnowledgeLayer = KnowledgeLayer.GLOBAL
    subcategory: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    project: Optional[str] = None
    client: Optional[str] = None
    language: str = "ru"
    source_path: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    sheet_name: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    heading_path: Optional[str] = None
    visual_description: Optional[str] = None
    ocr_text: Optional[str] = None
    is_generated: bool = False # Separation of factual source vs derived AI summary

class KnowledgeChunk(BaseModel):
    id: str
    source_id: str
    layer: KnowledgeLayer
    content: str
    content_type: ContentType = ContentType.TEXT
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    sheet_name: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    heading_path: Optional[str] = None
    language: str = "ru"
    token_count: int = 0
    metadata: KnowledgeMetadata
    score: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SourceTrace(BaseModel):
    source_id: str
    title: str
    layer: KnowledgeLayer
    chunk_id: Optional[str] = None
    confidence: float = 1.0
    snippet: str = ""
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    sheet_name: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    timestamp_range: Optional[str] = None

class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    status: IngestionStatus = IngestionStatus.DISCOVERED
    priority: int = 10
    stage: str = "DISCOVERED"
    attempts: int = 0
    max_attempts: int = 3
    progress: float = 0.0
    checkpoint_stage: Optional[str] = None
    error_message: Optional[str] = None
    worker_id: Optional[str] = None
    lease_until: Optional[str] = None
    heartbeat_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def retry_count(self) -> int:
        return self.attempts

    @property
    def error(self) -> Optional[str]:
        return self.error_message
