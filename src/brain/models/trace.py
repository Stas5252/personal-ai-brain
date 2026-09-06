"""
Observability and Tracing Models for Personal AI Brain.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from src.brain.models.routing import IntentType
from src.brain.models.knowledge import SourceTrace, HallucinationType

class RequestTrace(BaseModel):
    request_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    query: str
    primary_intent: IntentType
    secondary_intents: List[IntentType] = Field(default_factory=list)
    retrieved_memories: List[Dict[str, Any]] = Field(default_factory=list)
    retrieved_sources: List[SourceTrace] = Field(default_factory=list)
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    style_applied: bool = False
    selected_tools: List[str] = Field(default_factory=list)
    model: str = "default"
    latency_sec: float = 0.0
    hallucination_verdict: HallucinationType = HallucinationType.GENERAL_KNOWLEDGE
