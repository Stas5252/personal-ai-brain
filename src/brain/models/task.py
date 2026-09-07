"""
Unified Task Model for Personal AI Brain.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"

class ApprovalState(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class Task(BaseModel):
    task_id: str
    title: str
    type: str = "general"  # content, sales, shooting, follow_up, admin, workflow
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    due_at: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    approval_state: ApprovalState = ApprovalState.NONE
