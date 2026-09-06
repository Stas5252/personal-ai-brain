"""
Client Entity Models for Personal AI Brain.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class ClientStatus(str, Enum):
    LEAD = "LEAD"
    NEGOTIATING = "NEGOTIATING"
    CONFIRMED = "CONFIRMED"
    PAID = "PAID"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    LOST = "LOST"

class Client(BaseModel):
    id: str
    name: str
    contact: Optional[str] = None
    status: ClientStatus = ClientStatus.LEAD
    source: Optional[str] = "Telegram"
    budget: Optional[str] = None
    service: Optional[str] = None
    preferences: str = ""
    objections: str = ""
    history: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
