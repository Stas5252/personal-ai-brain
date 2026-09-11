"""
Context Engine and Token Budgeting for Personal AI Brain.
Assembles prompt context according to strict hierarchy and weighted scoring.
"""
from typing import List, Optional, Tuple, Dict, Any
from src.brain.config import (
    WEIGHT_RELEVANCE, WEIGHT_IMPORTANCE, WEIGHT_RECENCY, MAX_CONTEXT_CHARS, BUDGET_QUOTAS
)
from src.brain.models.profile import UserProfile
from src.brain.models.memory import MemoryItem
from src.brain.models.knowledge import KnowledgeChunk, SourceTrace
from src.brain.models.client import Client
from src.brain.models.project import Project
from src.brain.models.style import StyleProfile
from src.brain.models.context import ContextItem, ContextType, AssembledContext
from src.brain.engines.memory_engine import recency_score

class ContextEngine:
    def __init__(self):
        pass

    def rank_items(self, items: List[ContextItem]) -> List[ContextItem]:
        """
        Ranks context candidates using:
        score = WEIGHT_RELEVANCE * relevance + WEIGHT_IMPORTANCE * importance + WEIGHT_RECENCY * recency
        """
        for it in items:
            it.score = (
                WEIGHT_RELEVANCE * it.relevance +
                WEIGHT_IMPORTANCE * it.importance +
                WEIGHT_RECENCY * it.recency
            )
        return sorted(items, key=lambda x: x.score, reverse=True)

    def assemble_context(
        self,
        query: str,
        system_policy: str,
        profile: UserProfile,
        memories: List[Tuple[MemoryItem, float]],
        knowledge: List[Tuple[KnowledgeChunk, float, SourceTrace]],
        style_instructions: Optional[str] = None,
        project: Optional[Project] = None,
        client: Optional[Client] = None,
        specialized_prompt: Optional[str] = None
    ) -> AssembledContext:
        """
        Assembles all layers into structured context strictly observing the hierarchy:
        SYSTEM POLICY > USER PROFILE > PROJECT CONTEXT > CLIENT CONTEXT > MEMORY > KNOWLEDGE
        """
        # 1. System policy block
        policy_block = system_policy
        if specialized_prompt:
            policy_block += f"\n\n### ТЕКУЩИЙ СПЕЦИАЛИЗИРОВАННЫЙ ФОКУС:\n{specialized_prompt}"

        # 2. User profile block (dynamic, never hardcoded in policy)
        profile_lines = ["### ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:"]
        if profile.identity:
            profile_lines.append(f"- Имя/Проект: {profile.identity}")
        if profile.profession:
            profile_lines.append(f"- Профессия: {profile.profession}")
        if profile.niche:
            profile_lines.append(f"- Ниша: {profile.niche}")
        if profile.city:
            profile_lines.append(f"- Город: {profile.city}")
        if profile.services:
            profile_lines.append(f"- Услуги: {', '.join(profile.services)}")
        if profile.prices:
            prices_str = "; ".join([f"{k}: {v}" for k, v in profile.prices.items()])
            profile_lines.append(f"- Цены: {prices_str}")
        if profile.audience:
            profile_lines.append(f"- Аудитория: {profile.audience}")
        if profile.tone:
            profile_lines.append(f"- Тональность: {profile.tone}")
        if profile.forbidden_words:
            profile_lines.append(f"- Стоп-слова: {', '.join(profile.forbidden_words)}")
        profile_block = "\n".join(profile_lines)

        # 3. Project context
        project_block = None
        if project:
            tasks_str = ", ".join([f"{t.title} ({'✓' if t.completed else '…'})" for t in project.tasks]) if project.tasks else "нет активных"
            decisions_str = "; ".join(project.decisions) if project.decisions else "нет"
            project_block = (
                f"### АКТИВНЫЙ КОНТЕКСТ ПРОЕКТА '{project.name}':\n"
                f"- Статус: {project.status.value}\n"
                f"- Описание: {project.description}\n"
                f"- Задачи: {tasks_str}\n"
                f"- Принятые решения: {decisions_str}"
            )

        # 4. Client context
        client_block = None
        if client:
            client_block = (
                f"### АКТИВНЫЙ КОНТЕКСТ КЛИЕНТА '{client.name}':\n"
                f"- Статус: {client.status.value}\n"
                f"- Интересующая услуга: {client.service or 'не указана'}\n"
                f"- Бюджет: {client.budget or 'не указан'}\n"
                f"- Пожелания: {client.preferences or 'нет данных'}\n"
                f"- Возражения/Нюансы: {client.objections or 'нет'}"
            )

        # 5. Memories
        # recency берётся из реальных дат записи: раньше здесь стояла константа 1.0,
        # из-за чего вес свежести в ранжировании не работал вообще.
        context_memories = []
        for m, score in memories:
            context_memories.append(ContextItem(
                id=m.id,
                item_type=ContextType.MEMORY,
                title=f"Memory ({m.type.value})",
                content=m.content,
                score=score,
                relevance=score,
                importance=m.importance,
                recency=recency_score(m.created_at, m.updated_at),
                metadata={"source": m.source}
            ))

        # 6. Knowledge Chunks & Traces
        # У материалов курса даты индексации не означают устаревание методики,
        # поэтому свежесть здесь намеренно нейтральная.
        context_knowledge = []
        traces = []
        for chunk, score, trace in knowledge:
            context_knowledge.append(ContextItem(
                id=chunk.id,
                item_type=ContextType.KNOWLEDGE,
                title=f"{trace.title} [{chunk.layer.value}]",
                content=chunk.content,
                score=score,
                relevance=score,
                importance=chunk.metadata.confidence,
                recency=1.0,
                metadata={"source_id": trace.source_id, "layer": chunk.layer.value}
            ))
            traces.append(trace)

        # Enforce budget quotas and strict character limits
        max_mem_chars = int(MAX_CONTEXT_CHARS * BUDGET_QUOTAS.get("memories", 0.15))
        max_know_chars = int(MAX_CONTEXT_CHARS * BUDGET_QUOTAS.get("knowledge", 0.20))
        max_project_chars = int(MAX_CONTEXT_CHARS * BUDGET_QUOTAS.get("project_context", 0.20))
        max_client_chars = int(MAX_CONTEXT_CHARS * BUDGET_QUOTAS.get("client_context", 0.15))
        max_profile_chars = int(MAX_CONTEXT_CHARS * BUDGET_QUOTAS.get("user_profile", 0.15))

        # Truncate profile, project, and client blocks if exceeding budget
        if len(profile_block) > max_profile_chars:
            profile_block = profile_block[:max_profile_chars - 20] + "\n... [truncated]"

        if project_block and len(project_block) > max_project_chars:
            project_block = project_block[:max_project_chars - 20] + "\n... [truncated]"

        if client_block and len(client_block) > max_client_chars:
            client_block = client_block[:max_client_chars - 20] + "\n... [truncated]"

        # Rank and truncate memories according to quota
        ranked_memories = self.rank_items(context_memories)
        fitted_memories: List[ContextItem] = []
        mem_chars = 0
        for m in ranked_memories:
            if mem_chars + len(m.content) <= max_mem_chars:
                fitted_memories.append(m)
                mem_chars += len(m.content)
            elif not fitted_memories:
                m.content = m.content[:max_mem_chars]
                fitted_memories.append(m)
                break

        # Rank and truncate knowledge chunks according to quota
        ranked_knowledge = self.rank_items(context_knowledge)
        trace_map = {k.id: t for k, t in zip(context_knowledge, traces)}
        fitted_knowledge: List[ContextItem] = []
        fitted_traces: List[SourceTrace] = []
        know_chars = 0
        for k in ranked_knowledge:
            if know_chars + len(k.content) <= max_know_chars:
                fitted_knowledge.append(k)
                if k.id in trace_map:
                    fitted_traces.append(trace_map[k.id])
                know_chars += len(k.content)
            elif not fitted_knowledge:
                k.content = k.content[:max_know_chars]
                fitted_knowledge.append(k)
                if k.id in trace_map:
                    fitted_traces.append(trace_map[k.id])
                break

        # Global ceiling enforcement: total_chars <= MAX_CONTEXT_CHARS
        def _calc_total():
            return (
                len(policy_block) +
                len(profile_block) +
                (len(project_block) if project_block else 0) +
                (len(client_block) if client_block else 0) +
                (len(style_instructions) if style_instructions else 0) +
                sum(len(m.content) for m in fitted_memories) +
                sum(len(k.content) for k in fitted_knowledge)
            )

        while _calc_total() > MAX_CONTEXT_CHARS and fitted_knowledge:
            fitted_knowledge.pop()
            if fitted_traces:
                fitted_traces.pop()

        while _calc_total() > MAX_CONTEXT_CHARS and fitted_memories:
            fitted_memories.pop()

        total_chars = _calc_total()

        return AssembledContext(
            system_policy=policy_block,
            user_profile=profile_block,
            project_context=project_block,
            client_context=client_block,
            style_context=style_instructions,
            memories=fitted_memories,
            knowledge_chunks=fitted_knowledge,
            total_chars=total_chars,
            estimated_tokens=total_chars // 4,
            traces=fitted_traces
        )
