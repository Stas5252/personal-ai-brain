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
from src.brain.models.task import Task, TaskStatus, TaskPriority, ApprovalState

from src.brain.engines.profile_engine import ProfileEngine
from src.brain.engines.memory_engine import MemoryEngine
from src.brain.engines.knowledge_engine import KnowledgeEngine
from src.brain.engines.style_engine import StyleEngine
from src.brain.engines.agent_router import AgentRouter
from src.brain.engines.context_engine import ContextEngine
from src.brain.services.llm_provider import LLMProvider
from src.brain.engines.content_engine import ContentEngine
from src.brain.engines.sales_engine import SalesEngine
from src.brain.engines.shooting_engine import ShootingEngine
from src.brain.engines.voice_engine import VoiceEngine
from src.brain.engines.proactive_engine import ProactiveEngine
from src.brain.engines.workflow_engine import WorkflowEngine, WorkflowInstance

class BrainService:
    def __init__(self):
        self.profile_engine = ProfileEngine()
        self.memory_engine = MemoryEngine()
        self.knowledge_engine = KnowledgeEngine()
        self.style_engine = StyleEngine()
        self.router = AgentRouter()
        self.context_engine = ContextEngine()
        self.llm = LLMProvider()
        self.content_engine = ContentEngine()
        self.sales_engine = SalesEngine()
        self.shooting_engine = ShootingEngine()
        self.voice_engine = VoiceEngine()
        self.proactive_engine = ProactiveEngine()
        self.workflow_engine = WorkflowEngine()

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
        auto_admission: bool = True,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        audio_path: Optional[str] = None
    ) -> Dict[str, Any]:
        t0 = time.time()
        request_id = str(uuid.uuid4())

        # 1. Feedback Learning Loop
        q_lower = query.lower()
        if any(w in q_lower for w in ["мне понравилось", "отличный пост", "сохрани этот стиль", "вот так пиши"]):
            try:
                from src.brain.models.memory import MemoryType
                self.memory_engine.add_memory(
                    content=f"Одобренный стиль/пример: {query}",
                    memory_type=MemoryType.PREFERENCE,
                    importance=0.9,
                    source="user_positive_feedback"
                )
            except Exception:
                pass
        elif any(w in q_lower for w in ["так больше не пиши", "никогда так не пиши", "убери инфоцыган", "не используй"]):
            try:
                from src.brain.models.memory import MemoryType
                self.memory_engine.add_memory(
                    content=f"Стилевой запрет/негативный отзыв: {query}",
                    memory_type=MemoryType.PREFERENCE,
                    importance=0.95,
                    source="user_negative_feedback"
                )
            except Exception:
                pass

        # 1b. Audio Voice Processing
        if audio_path:
            try:
                from pathlib import Path
                from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
                ae = AudioExtractor()
                derived_dir = Path("data/.derived")
                derived_dir.mkdir(parents=True, exist_ok=True)
                ext_res = ae.extract(Path(audio_path), source_id="voice_chat", derived_dir=derived_dir)
                if ext_res.success and ext_res.raw_text:
                    query = f"{query}\n[Транскрипт аудиосообщения]: {ext_res.raw_text}"
            except Exception:
                pass

        # 2. Evaluate memory admission on the user's input (automatic memory learning)
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

        # 3. User Profile, Project & Client Entities
        profile = self.profile_engine.get_profile()
        project = self.get_project(project_id) if project_id else None
        client = self.get_client(client_id) if client_id else None

        # 4. Context-Aware Multi-Intent Routing & Adaptive Questioning
        routing: RoutingDecision = self.router.route(query, context={"profile": profile, "project": project, "client": client})

        # Enrich specialized prompt with domain engine guidance
        if routing.action_type == "CLARIFY" and routing.clarifying_questions:
            q_lines = "\n".join([f"- {q}" for q in routing.clarifying_questions])
            routing.specialized_system_prompt += f"\n\nПользователь запускает процесс '{routing.workflow_suggested}'. Подтверди замысел, задай уточняющие вопросы:\n{q_lines}"
        elif routing.workflow_suggested == "no_content_emergency":
            angles = self.content_engine.emergency_content_recovery(profile=profile)
            a_lines = "\n".join([f"- {a['angle']} ({a['format']}): {a['hook']}" for a in angles])
            routing.specialized_system_prompt += f"\n\nСценарий 'Мне нечего выложить'. Предложи готовые ракурсы:\n{a_lines}"
        elif routing.workflow_suggested == "client_chat_analysis" or routing.primary_intent in [IntentType.SALES, IntentType.OBJECTION]:
            dialogue_analysis = self.sales_engine.analyze_client_dialogue(query)
            strat = dialogue_analysis.get('recommended_strategy', '')
            meaning = dialogue_analysis.get('what_client_really_means', '')
            routing.specialized_system_prompt += f"\n\nДиагностика клиента: стадия {dialogue_analysis['detected_stage']}, возражения {dialogue_analysis['detected_objections']}. Что клиент имеет в виду: {meaning}. Стратегия: {strat}"
        elif routing.primary_intent == IntentType.DAILY_PLAN or routing.workflow_suggested == "daily_planning":
            plan = self.proactive_engine.generate_daily_plan(profile=profile)
            p_lines = "\n".join([f"Приоритет {p['priority_level']} [{p['domain']}]: {p['title']} — {p['action']}" for p in plan["priorities"]])
            routing.specialized_system_prompt += f"\n\nПлан на сегодня:\n{p_lines}"
        elif routing.primary_intent == IntentType.VOICE or routing.workflow_suggested == "voice_to_content":
            voice_pack = self.voice_engine.process_voice_transcript(query, profile=profile)
            routing.specialized_system_prompt += f"\n\nРазбор голосового фотографа: события={voice_pack['extracted_events']}, инсайты={voice_pack['business_insights']}. Сформируй: 1 пост, 2 сценария Reels, Stories и задачу."
        elif routing.primary_intent in [IntentType.PHOTO, IntentType.MOODBOARD] or routing.workflow_suggested == "shoot_preparation":
            default_genre = (getattr(profile, "genres", None) and profile.genres[0]) or (getattr(profile, "services", None) and profile.services[0]) or getattr(profile, "niche", "Портрет") or "Портрет"
            v_logic = self.shooting_engine.build_visual_logic(query, genre=default_genre)
            routing.specialized_system_prompt += f"\n\nСхема света: {v_logic['light_scheme']['primary']}. Цветовая палитра: {[c['name'] for c in v_logic['color_palette']]}"

        # 5. Retrieve relevant memories (scored)
        memories = self.memory_engine.retrieve_relevant_memories(
            query=query, limit=4, project_id=project_id, client_id=client_id
        )

        # 6. Retrieve knowledge chunks
        target_layer = None
        if routing.primary_intent in [IntentType.PHOTO, IntentType.MOODBOARD]:
            target_layer = KnowledgeLayer.PROFESSIONAL
        elif routing.primary_intent in [IntentType.SALES, IntentType.PRICING]:
            target_layer = KnowledgeLayer.BUSINESS
            
        knowledge_hits = self.knowledge_engine.retrieve(
            query=query, layer=target_layer, project=project_id, client=client_id, limit=3
        )
        if not knowledge_hits and target_layer is not None:
            knowledge_hits = self.knowledge_engine.retrieve(
                query=query, layer=None, project=project_id, client=client_id, limit=3
            )

        # 7. Style Directives
        style_profile = StyleProfile(
            tone=profile.tone or "Искренний, кинематографичный",
            forbidden_expressions=profile.forbidden_words
        )
        style_instr = self.style_engine.build_style_instructions(style_profile)

        # 8. Assemble Context
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

        # 9. Build Messages for LLM
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

        # Live Vision Integration if images passed
        if images:
            for img_item in images:
                try:
                    v_res = self.shooting_engine.critique_shot(img_item)
                    if v_res.get("status") == "AVAILABLE" and v_res.get("description"):
                        context_parts.append(f"### ПРЯМОЙ АНАЛИЗ ФОТОГРАФИИ (GEMINI VISION):\n{v_res['description']}")
                except Exception:
                    pass

        system_message = "\n\n".join(context_parts)
        llm_messages = [{"role": "system", "content": system_message}]

        # Inject multi-turn conversation history
        if conversation_history:
            for prev_msg in conversation_history[-6:]:
                r = prev_msg.get("role")
                c = prev_msg.get("content")
                if r in ["user", "assistant"] and c:
                    llm_messages.append({"role": r, "content": str(c)})

        llm_messages.append({"role": "user", "content": query})

        # 10. Call Model Provider
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
            "model_used": model_used,
            "intent": routing.primary_intent.value if hasattr(routing.primary_intent, "value") else str(routing.primary_intent),
            "execution_time_ms": int(total_latency * 1000),
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

    # --- Task System CRUD ---
    def create_task(
        self,
        title: str,
        task_type: str = "general",
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_at: Optional[str] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        approval_state: ApprovalState = ApprovalState.NONE
    ) -> Task:
        task_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        task = Task(
            task_id=task_id,
            title=title,
            type=task_type,
            status=TaskStatus.TODO,
            priority=priority,
            created_at=now_str,
            due_at=due_at,
            project_id=project_id,
            client_id=client_id,
            inputs=inputs or {},
            outputs=outputs or {},
            approval_state=approval_state
        )
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO tasks (task_id, title, type, status, priority, created_at, due_at, project_id, client_id, inputs_json, outputs_json, approval_state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.task_id, task.title, task.type, task.status.value, task.priority.value,
            task.created_at, task.due_at, task.project_id, task.client_id,
            json.dumps(task.inputs, ensure_ascii=False), json.dumps(task.outputs, ensure_ascii=False),
            task.approval_state.value
        ))
        conn.commit()
        conn.close()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            return None
        return Task(
            task_id=r["task_id"],
            title=r["title"],
            type=r["type"],
            status=TaskStatus(r["status"]),
            priority=TaskPriority(r["priority"]),
            created_at=r["created_at"],
            due_at=r["due_at"],
            project_id=r["project_id"],
            client_id=r["client_id"],
            inputs=json.loads(r["inputs_json"] or "{}"),
            outputs=json.loads(r["outputs_json"] or "{}"),
            approval_state=ApprovalState(r["approval_state"])
        )

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None
    ) -> List[Task]:
        conn = get_connection()
        c = conn.cursor()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)
        query += " ORDER BY created_at DESC"
        c.execute(query, tuple(params))
        rows = c.fetchall()
        conn.close()
        return [
            Task(
                task_id=r["task_id"],
                title=r["title"],
                type=r["type"],
                status=TaskStatus(r["status"]),
                priority=TaskPriority(r["priority"]),
                created_at=r["created_at"],
                due_at=r["due_at"],
                project_id=r["project_id"],
                client_id=r["client_id"],
                inputs=json.loads(r["inputs_json"] or "{}"),
                outputs=json.loads(r["outputs_json"] or "{}"),
                approval_state=ApprovalState(r["approval_state"])
            )
            for r in rows
        ]

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        approval_state: Optional[ApprovalState] = None
    ) -> Optional[Task]:
        task = self.get_task(task_id)
        if not task:
            return None
        conn = get_connection()
        c = conn.cursor()
        if approval_state:
            c.execute("UPDATE tasks SET status = ?, approval_state = ? WHERE task_id = ?", (status.value, approval_state.value, task_id))
        else:
            c.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status.value, task_id))
        conn.commit()
        conn.close()
        task.status = status
        if approval_state:
            task.approval_state = approval_state
        return task

    # --- Workflow Orchestration ---
    def start_workflow(self, workflow_type: str, initial_context: Optional[Dict[str, Any]] = None, name: Optional[str] = None) -> WorkflowInstance:
        return self.workflow_engine.start_workflow(workflow_type, initial_context, name)

    def advance_workflow(self, workflow_id: str, step_output: Dict[str, Any], next_inputs: Optional[Dict[str, Any]] = None) -> WorkflowInstance:
        return self.workflow_engine.advance_step(workflow_id, step_output, next_inputs)

    def approve_workflow_step(self, workflow_id: str, approved: bool = True) -> WorkflowInstance:
        return self.workflow_engine.approve_step(workflow_id, approved)

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInstance]:
        return self.workflow_engine.get_workflow(workflow_id)

    def execute_workflow_step(self, workflow_id: str) -> Tuple[WorkflowInstance, Dict[str, Any]]:
        profile = self.profile_engine.get_profile()
        return self.workflow_engine.execute_step(workflow_id, profile=profile)
