"""
Core Brain Service Orchestrator for Personal AI Brain.
Coordinates Routing, Profile, Memory, Knowledge, Style, Projects, Clients, and Observability Traces.
"""
import uuid
import json
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from src.brain.db import get_connection
from src.brain.prompts.system_policy import UNIVERSAL_SYSTEM_POLICY
from src.brain.models.profile import UserProfile
from src.brain.models.memory import MemoryItem, MemoryType, AdmissionAction
from src.brain.models.knowledge import KnowledgeLayer, KnowledgeChunk, SourceTrace, HallucinationType
from src.brain.models.client import Client, ClientStatus
from src.brain.models.project import Project, ProjectStatus
from src.brain.models.style import StyleProfile, ExemplarCategory
from src.brain.models.routing import IntentType, RoutingDecision
from src.brain.models.trace import RequestTrace

from src.brain.engines.profile_engine import ProfileEngine
from src.brain.engines.memory_engine import MemoryEngine
from src.brain.engines.knowledge_engine import KnowledgeEngine
from src.brain.engines.style_engine import StyleEngine
from src.brain.engines.agent_router import AgentRouter
from src.brain.engines.context_engine import ContextEngine
from src.brain.services.llm_provider import LLMProvider

class BrainService:
    def __init__(self):
        self.profile_engine = ProfileEngine()
        self.memory_engine = MemoryEngine()
        self.knowledge_engine = KnowledgeEngine()
        self.style_engine = StyleEngine()
        self.router = AgentRouter()
        self.context_engine = ContextEngine()
        self.llm = LLMProvider()

    # --- Client & Project CRUD ---
    def create_client(self, name: str, contact: str = "", status: ClientStatus = ClientStatus.LEAD, service: str = "", budget: str = "", preferences: str = "", objections: str = "") -> Client:
        client_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        client = Client(
            id=client_id, name=name, contact=contact, status=status,
            service=service, budget=budget, preferences=preferences,
            objections=objections, created_at=now_str, updated_at=now_str
        )
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO clients (id, name, contact, status, source, budget, service, preferences, objections, history_json, projects_json, notes_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', ?, ?)
        """, (client.id, client.name, client.contact, client.status.value, client.source, client.budget, client.service, client.preferences, client.objections, client.created_at, client.updated_at))
        conn.commit()
        conn.close()
        return client

    def get_client(self, client_id: str) -> Optional[Client]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            return None
        return Client(
            id=r["id"], name=r["name"], contact=r["contact"],
            status=ClientStatus(r["status"]), source=r["source"],
            budget=r["budget"], service=r["service"], preferences=r["preferences"],
            objections=r["objections"], history=json.loads(r["history_json"] or "[]"),
            projects=json.loads(r["projects_json"] or "[]"), notes=json.loads(r["notes_json"] or "[]"),
            created_at=r["created_at"], updated_at=r["updated_at"]
        )

    def create_project(self, name: str, description: str = "", status: ProjectStatus = ProjectStatus.PLANNING, client_id: Optional[str] = None, deadline: Optional[str] = None) -> Project:
        proj_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        proj = Project(
            id=proj_id, name=name, description=description, status=status,
            client_id=client_id, deadline=deadline, created_at=now_str, updated_at=now_str
        )
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO projects (id, name, description, status, start_date, deadline, client_id, files_json, conversations_json, tasks_json, decisions_json, outputs_json, memory_ids_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', '[]', '[]', '[]', ?, ?)
        """, (proj.id, proj.name, proj.description, proj.status.value, proj.start_date, proj.deadline, proj.client_id, proj.created_at, proj.updated_at))
        conn.commit()
        conn.close()
        return proj

    def get_project(self, project_id: str) -> Optional[Project]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            return None
        return Project(
            id=r["id"], name=r["name"], description=r["description"],
            status=ProjectStatus(r["status"]), start_date=r["start_date"],
            deadline=r["deadline"], client_id=r["client_id"],
            files=json.loads(r["files_json"] or "[]"),
            conversations=json.loads(r["conversations_json"] or "[]"),
            tasks=json.loads(r["tasks_json"] or "[]"),
            decisions=json.loads(r["decisions_json"] or "[]"),
            outputs=json.loads(r["outputs_json"] or "[]"),
            memory_ids=json.loads(r["memory_ids_json"] or "[]"),
            created_at=r["created_at"], updated_at=r["updated_at"]
        )

    # --- Main Pipeline: Chat Request Execution ---
    def process_chat(
        self,
        query: str,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        preferred_model: Optional[str] = None,
        auto_admission: bool = True
    ) -> Dict[str, Any]:
        t0 = time.time()
        request_id = str(uuid.uuid4())

        # 1. Evaluate memory admission on the user's input (automatic memory learning)
        admission_result = None
        if auto_admission:
            adm_dec = self.memory_engine.evaluate_admission(query)
            if adm_dec.action in [AdmissionAction.SAVE, AdmissionAction.TEMPORARY]:
                self.memory_engine.add_memory(
                    content=adm_dec.extracted_fact or query,
                    memory_type=adm_dec.memory_type,
                    importance=adm_dec.importance,
                    confidence=adm_dec.confidence,
                    project_id=project_id,
                    client_id=client_id,
                    source="chat_admission"
                )
                admission_result = adm_dec.action.value

        # 2. Routing
        routing: RoutingDecision = self.router.route(query)

        # 3. Retrieve relevant memories (scored)
        memories = self.memory_engine.retrieve_relevant_memories(
            query=query, limit=4, project_id=project_id, client_id=client_id
        )

        # 4. Retrieve knowledge chunks
        target_layer = None
        if routing.primary_intent in [IntentType.PHOTO, IntentType.MOODBOARD]:
            target_layer = KnowledgeLayer.PROFESSIONAL
        elif routing.primary_intent in [IntentType.SALES, IntentType.PRICING]:
            target_layer = KnowledgeLayer.BUSINESS
            
        knowledge_hits = self.knowledge_engine.retrieve(
            query=query, layer=target_layer, project=project_id, client=client_id, limit=3
        )
        # If specific layer returned nothing, search all layers
        if not knowledge_hits and target_layer is not None:
            knowledge_hits = self.knowledge_engine.retrieve(
                query=query, layer=None, project=project_id, client=client_id, limit=3
            )

        # 5. User Profile & Style Directives
        profile = self.profile_engine.get_profile()
        style_profile = StyleProfile(
            tone=profile.tone or "Искренний, кинематографичный",
            forbidden_expressions=profile.forbidden_words
        )
        style_instr = self.style_engine.build_style_instructions(style_profile)

        # 6. Project & Client Entities
        project = self.get_project(project_id) if project_id else None
        client = self.get_client(client_id) if client_id else None

        # 7. Assemble Context
        assembled = self.context_engine.assemble_context(
            query=query,
            system_policy=UNIVERSAL_SYSTEM_POLICY,
            profile=profile,
            memories=memories,
            knowledge=knowledge_hits,
            style_instructions=style_instr,
            project=project,
            client=client,
            specialized_prompt=routing.specialized_system_prompt
        )

        # 8. Build Messages for LLM
        # Formulate system context
        context_parts = [assembled.system_policy, assembled.user_profile]
        if assembled.project_context:
            context_parts.append(assembled.project_context)
        if assembled.client_context:
            context_parts.append(assembled.client_context)
        if assembled.style_context:
            context_parts.append(assembled.style_context)
            
        if assembled.memories:
            m_text = "\n".join([f"- [{m.title}]: {m.content}" for m in assembled.memories])
            context_parts.append(f"### ДОЛГОВРЕМЕННАЯ ПАМЯТЬ ПОЛЬЗОВАТЕЛЯ:\n{m_text}")
            
        if assembled.knowledge_chunks:
            k_text = "\n\n".join([f"--- Источник: {k.title} ---\n{k.content}" for k in assembled.knowledge_chunks])
            context_parts.append(f"### МАТЕРИАЛЫ ИЗ БАЗЫ ЗНАНИЙ:\n{k_text}")

        system_message = "\n\n".join(context_parts)
        llm_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": query}
        ]

        # 9. Call Model Provider
        status_code, response_text, dt, model_used = self.llm.chat_completion(
            messages=llm_messages, preferred_model=preferred_model
        )

        # 10. Evaluate Hallucination & Style Benchmark
        hallucination = self.knowledge_engine.evaluate_hallucination(query, knowledge_hits, response_text)
        benchmark = self.style_engine.evaluate_benchmark(response_text, style_profile, forbidden_words=profile.forbidden_words)

        total_latency = time.time() - t0

        # 11. Trace Logging
        trace = RequestTrace(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
            primary_intent=routing.primary_intent,
            secondary_intents=routing.secondary_intents,
            retrieved_memories=[{"id": m[0].id, "content": m[0].content, "score": m[1]} for m in memories],
            retrieved_sources=assembled.traces,
            project_id=project_id,
            client_id=client_id,
            style_applied=True,
            selected_tools=routing.required_tools,
            model=model_used,
            latency_sec=round(total_latency, 2),
            hallucination_verdict=hallucination
        )

        self._save_trace(trace)

        return {
            "response": response_text,
            "status_code": status_code,
            "trace": trace.model_dump(),
            "style_benchmark": benchmark.model_dump(),
            "context_summary": {
                "estimated_tokens": assembled.estimated_tokens,
                "memories_count": len(memories),
                "knowledge_chunks_count": len(knowledge_hits),
                "admission_action": admission_result
            }
        }

    def _save_trace(self, trace: RequestTrace):
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO request_traces (request_id, timestamp, query, intent, data_json)
        VALUES (?, ?, ?, ?, ?)
        """, (trace.request_id, trace.timestamp, trace.query, trace.primary_intent.value, trace.model_dump_json()))
        conn.commit()
        conn.close()

    def get_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT data_json FROM request_traces ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [json.loads(r["data_json"]) for r in rows]
