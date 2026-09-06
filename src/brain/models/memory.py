"""
Memory Models and Enums for Personal AI Brain.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

class MemoryType(str, Enum):
    PROFILE = "PROFILE"
    PREFERENCE = "PREFERENCE"
    FACT = "FACT"
    GOAL = "GOAL"
    DECISION = "DECISION"
    PROJECT = "PROJECT"
    CLIENT = "CLIENT"
    STYLE = "STYLE"
    EPISODE = "EPISODE"
    TEMPORARY = "TEMPORARY"

class MemoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    EXPIRED = "EXPIRED"

class AdmissionAction(str, Enum):
    SAVE = "SAVE"
    UPDATE = "UPDATE"
    IGNORE = "IGNORE"
    TEMPORARY = "TEMPORARY"

class AdmissionDecision(BaseModel):
    action: AdmissionAction
    reason: str
    memory_type: MemoryType = MemoryType.FACT
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    target_memory_id: Optional[str] = None
    extracted_fact: str = ""

class MemoryItem(BaseModel):
    id: str
    type: MemoryType
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "conversation"
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    expires_at: Optional[str] = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    superseded_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
