"""
Project Entity Models for Personal AI Brain.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class ProjectStatus(str, Enum):
    IDEA = "IDEA"
    PLANNING = "PLANNING"
    PRE_PRODUCTION = "PRE_PRODUCTION"
    SHOOTING = "SHOOTING"
    POST_PROCESSING = "POST_PROCESSING"
    DELIVERED = "DELIVERED"
    ARCHIVED = "ARCHIVED"

class ProjectTask(BaseModel):
    id: str
    title: str
    completed: bool = False
    deadline: Optional[str] = None

class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNING
    start_date: Optional[str] = None
    deadline: Optional[str] = None
    client_id: Optional[str] = None
    files: List[str] = Field(default_factory=list)
    conversations: List[str] = Field(default_factory=list)
    tasks: List[ProjectTask] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    memory_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
