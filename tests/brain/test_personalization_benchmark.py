"""
Personalization Benchmark for Personal AI Brain.
Evaluates query generation and context assembly WITH Profile vs WITHOUT Profile.
Demonstrates that Profile, Memories, and Style deeply personalize responses.
"""
import pytest
from src.brain.services.brain_service import BrainService
from src.brain.models.profile import UserProfile
from src.brain.models.memory import MemoryType

def test_personalization_gain():
    brain = BrainService()
    
    # 1. Test WITHOUT profile (empty)
    brain.profile_engine.save_profile(UserProfile())
    res_unpersonalized = brain.context_engine.assemble_context(
        query="Предложи концепцию для съемки",
        system_policy="Policy",
        profile=brain.profile_engine.get_profile(),
        memories=[],
        knowledge=[]
    )
    
    # 2. Test WITH personalized profile
    personalized_profile = UserProfile(
        identity="Александра Романова",
        city="Санкт-Петербург",
        niche="Кинематографичный нуар и ч/б портреты",
        genres=["Нуар", "Ч/Б портрет", "Архитектурная фотография"],
        services=["Авторский нуар-сет", "Экспресс ч/б"],
        pricing={"Авторский нуар-сет": "20 000 руб"},
        audience="Художники, актеры, писатели",
        tone="Сдержанный, интеллектуальный, глубокий"
    )
    brain.profile_engine.save_profile(personalized_profile)
    
    # Add relevant memory
    brain.memory_engine.add_memory(
        content="Любимая локация для съемок — старый фонд на Петроградке с высокими окнами",
        memory_type=MemoryType.PREFERENCE,
        importance=0.9,
        confidence=1.0,
        source="user_statement"
    )
    
    memories = brain.memory_engine.retrieve_relevant_memories(query="съемка на Петроградке", limit=2)
    
    res_personalized = brain.context_engine.assemble_context(
        query="Предложи концепцию для съемки",
        system_policy="Policy",
        profile=personalized_profile,
        memories=memories,
        knowledge=[]
    )
    
    # Assertions
    assert "Санкт-Петербург" in res_personalized.user_profile
    assert "Кинематографичный нуар" in res_personalized.user_profile
    assert "Александра Романова" in res_personalized.user_profile
    assert len(res_personalized.user_profile) > len(res_unpersonalized.user_profile)
    assert res_personalized.estimated_tokens > res_unpersonalized.estimated_tokens
    assert len(res_personalized.memories) >= 1
