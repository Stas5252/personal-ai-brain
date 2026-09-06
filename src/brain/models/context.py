"""
Context Assembly and Budget Models.
"""
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from src.brain.models.knowledge import SourceTrace

class ContextType(str, Enum):
    SYSTEM_POLICY = "SYSTEM_POLICY"
    USER_PROFILE = "USER_PROFILE"
    PROJECT_CONTEXT = "PROJECT_CONTEXT"
    CLIENT_CONTEXT = "CLIENT_CONTEXT"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    STYLE = "STYLE"

class ContextItem(BaseModel):
    id: str
    item_type: ContextType
    title: str
    content: str
    score: float = 1.0
    relevance: float = 1.0
    importance: float = 1.0
    recency: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AssembledContext(BaseModel):
    system_policy: str
    user_profile: str
    project_context: Optional[str] = None
    client_context: Optional[str] = None
    style_context: Optional[str] = None
    memories: List[ContextItem] = Field(default_factory=list)
    knowledge_chunks: List[ContextItem] = Field(default_factory=list)
    total_chars: int = 0
    estimated_tokens: int = 0
    traces: List[SourceTrace] = Field(default_factory=list)
