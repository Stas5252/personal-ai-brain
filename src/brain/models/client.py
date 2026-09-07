"""
Client Entity Models for Personal AI Brain.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class ClientStatus(str, Enum):
    LEAD = "LEAD"
    CONTACTED = "CONTACTED"
    INTERESTED = "INTERESTED"
    PROPOSAL = "PROPOSAL"
    THINKING = "THINKING"
    NEGOTIATING = "NEGOTIATING"
    CONFIRMED = "CONFIRMED"
    BOOKED = "BOOKED"
    PAID = "PAID"
    IN_PROGRESS = "IN_PROGRESS"
    SHOOTING = "SHOOTING"
    COMPLETED = "COMPLETED"
    FOLLOW_UP = "FOLLOW_UP"
    REPEAT = "REPEAT"
    LOST = "LOST"

class Client(BaseModel):
    id: str
    name: str
    contact: Optional[str] = None
    status: ClientStatus = ClientStatus.LEAD
    source: Optional[str] = "Telegram"
    source_channel: Optional[str] = None
    budget: Optional[str] = None
    service: Optional[str] = None
    preferences: str = ""
    preferred_style: str = ""
    objections: str = ""
    objections_history: List[str] = Field(default_factory=list)
    history: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    last_contact_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
