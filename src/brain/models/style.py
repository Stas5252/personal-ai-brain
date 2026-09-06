"""
Style Engine Models and Exemplars for Personal AI Brain.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class ExemplarType(str, Enum):
    GOOD_EXAMPLE = "GOOD_EXAMPLE"
    BAD_EXAMPLE = "BAD_EXAMPLE"
    NEUTRAL_EXAMPLE = "NEUTRAL_EXAMPLE"

class ExemplarCategory(str, Enum):
    POST = "POST"
    STORIES = "STORIES"
    REELS_SCRIPT = "REELS_SCRIPT"
    CLIENT_DM = "CLIENT_DM"
    OFFER = "OFFER"
    DESCRIPTION = "DESCRIPTION"

class StyleExemplar(BaseModel):
    id: str
    title: str
    content: str
    exemplar_type: ExemplarType = ExemplarType.GOOD_EXAMPLE
    category: ExemplarCategory = ExemplarCategory.POST
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class StyleProfile(BaseModel):
    vocabulary: List[str] = Field(default_factory=list)
    sentence_length_avg: float = Field(default=12.0)
    tone: str = "Искренний, кинематографичный, тёплый"
    humor: str = "Тонкая самоирония, деликатный"
    emoji_frequency: str = "Умеренная (1-2 на абзац)"
    paragraph_structure: str = "Короткие абзацы по 1-3 строки, динамичный ритм"
    hooks: List[str] = Field(default_factory=list)
    cta_patterns: List[str] = Field(default_factory=list)
    storytelling_ratio: float = 0.7
    punctuation_habits: str = "Любит тире и лаконичные точки, избегает многоточий"
    emotional_intensity: str = "Сдержанно-эмоциональный, эстетичный"
    formal_informal_ratio: float = 0.3  # 0.0 = completely informal, 1.0 = highly formal
    forbidden_expressions: List[str] = Field(default_factory=list)
    preferred_expressions: List[str] = Field(default_factory=list)

class StyleBenchmarkResult(BaseModel):
    vocabulary_similarity: float = Field(ge=0.0, le=1.0)
    sentence_rhythm_score: float = Field(ge=0.0, le=1.0)
    emoji_density_score: float = Field(ge=0.0, le=1.0)
    cta_presence_score: float = Field(ge=0.0, le=1.0)
    forbidden_violations: int = 0
    overall_score: float = Field(ge=0.0, le=1.0)
    notes: str = ""
