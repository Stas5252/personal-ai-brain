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
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    visual_description: Optional[str] = None
    ocr_text: Optional[str] = None

class KnowledgeChunk(BaseModel):
    id: str
    source_id: str
    layer: KnowledgeLayer
    content: str
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
