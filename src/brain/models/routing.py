"""
Agent Router Models and Enums.
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class IntentType(str, Enum):
    GENERAL = "GENERAL"
    PHOTO = "PHOTO"
    CONTENT = "CONTENT"
    REELS = "REELS"
    STORIES = "STORIES"
    SALES = "SALES"
    CLIENT = "CLIENT"
    PRICING = "PRICING"
    MARKETING = "MARKETING"
    PROFILE_AUDIT = "PROFILE_AUDIT"
    MOODBOARD = "MOODBOARD"
    PROJECT = "PROJECT"
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"

class RoutingDecision(BaseModel):
    primary_intent: IntentType
    secondary_intents: List[IntentType] = Field(default_factory=list)
    specialized_system_prompt: str = ""
    required_tools: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    reasoning: str = ""
