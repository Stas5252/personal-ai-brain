"""
Embedding Quality Benchmark across Russian, English, and Mixed texts.
Measures semantic similarity discrimination margin: cos_sim(positive) - cos_sim(negative).
"""
import math
from typing import Dict, Any, List, Tuple
from src.brain.knowledge.embeddings.provider import EmbeddingProvider
from src.brain.knowledge.embeddings.implementations import (
    ChromaOnnxEmbeddingProvider, HashFallbackEmbeddingProvider, GeminiEmbeddingProvider
)

BENCHMARK_PAIRS = [
    # 1. Russian semantic pairs
    {
        "category": "Russian",
        "query": "Схема студийного света для женского портрета",
        "positive": "Расположение октобокса и отражателя для мягкого освещения модели в фотостудии",
        "negative": "Классический рецепт шарлотки с корицей и яблоками"
    },
    {
        "category": "Russian",
        "query": "Стоимость съемки и предоплата за бронирование",
        "positive": "Пакет услуг фотографа стоит 45 000 рублей, задаток при бронировании даты 10 000 рублей",
        "negative": "Замена моторного масла и масляного фильтра в автомобиле"
    },
    # 2. English semantic pairs
    {
        "category": "English",
        "query": "Studio portrait lighting modifiers and softbox setup",
        "positive": "Using beauty dish and octabox for soft flattering studio portrait photography",
        "negative": "How to assemble an IKEA wooden bookshelf in three steps"
    },
    # 3. Mixed Russian / English pairs
    {
        "category": "Mixed",
        "query": "Сценарий для Instagram Reels про позирование на фотосессии",
        "positive": "Hook and script for 15-second Reels showing posing mistakes during photoshoot",
        "negative": "PostgreSQL relational database index tuning and query optimization"
    }
]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)

def run_embedding_benchmark(provider: EmbeddingProvider) -> Dict[str, Any]:
    """Evaluates embedding discrimination accuracy and margins across languages."""
    results = []
    total_margin = 0.0
    passed_tests = 0

    for idx, item in enumerate(BENCHMARK_PAIRS):
        q_vec = provider.embed_query(item["query"])
        pos_vec = provider.embed_query(item["positive"])
        neg_vec = provider.embed_query(item["negative"])

        pos_sim = cosine_similarity(q_vec, pos_vec)
        neg_sim = cosine_similarity(q_vec, neg_vec)
        margin = pos_sim - neg_sim

        # Success condition: positive similarity must be strictly greater than negative
        is_passed = margin > 0.10
        if is_passed:
            passed_tests += 1

        total_margin += margin
        results.append({
            "test_id": f"EMB_{idx+1}",
            "category": item["category"],
            "query": item["query"],
            "positive_similarity": round(pos_sim, 4),
            "negative_similarity": round(neg_sim, 4),
            "margin": round(margin, 4),
            "passed": is_passed
        })

    avg_margin = round(total_margin / len(BENCHMARK_PAIRS), 4)
    pass_rate = round((passed_tests / len(BENCHMARK_PAIRS)) * 100, 1)

    return {
        "provider": provider.provider_name,
        "dimension": provider.dimension,
        "pass_rate_percent": pass_rate,
        "average_margin": avg_margin,
        "tests_passed": passed_tests,
        "total_tests": len(BENCHMARK_PAIRS),
        "details": results
    }
