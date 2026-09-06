"""
Profile Models for Personal AI Brain.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class UserProfile(BaseModel):
    identity: str = Field(default="", description="Имя или бренд пользователя")
    profession: str = Field(default="Фотограф", description="Основная профессия")
    city: str = Field(default="", description="Город/регион работы")
    niche: str = Field(default="", description="Специализация/ниша в фотографии")
    services: List[str] = Field(default_factory=list, description="Перечень услуг")
    prices: Dict[str, str] = Field(default_factory=dict, description="Ценовая политика/пакеты")
    audience: str = Field(default="", description="Целевая аудитория")
    clients: str = Field(default="", description="Типажи клиентов")
    goals: List[str] = Field(default_factory=list, description="Текущие цели бизнеса/творчества")
    business_stage: str = Field(default="", description="Стадия развития")
    tone: str = Field(default="Дружелюбный экспертный", description="Тон коммуникации")
    language: str = Field(default="ru", description="Основной язык")
    preferred_models: List[str] = Field(default_factory=lambda: ["models/gemini-2.5-flash"], description="Предпочитаемые модели")
    content_preferences: str = Field(default="", description="Предпочтения по контенту")
    sales_preferences: str = Field(default="", description="Подход к продажам")
    visual_preferences: str = Field(default="", description="Визуальный почерк и эстетика")
    brand_preferences: str = Field(default="", description="Атрибуты личного бренда")
    forbidden_topics: List[str] = Field(default_factory=list, description="Табуированные темы")
    forbidden_words: List[str] = Field(default_factory=list, description="Запрещенные стоп-слова")
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class OnboardingQuestion(BaseModel):
    index: int
    id: str
    question: str
    field_target: str
    example: str

class OnboardingSession(BaseModel):
    session_id: str
    current_step: int = 0
    answers: Dict[str, str] = Field(default_factory=dict)
    completed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
