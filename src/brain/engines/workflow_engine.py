"""
Stateful Workflow Engine for Personal AI Brain.
Orchestrates multi-step photographer workflows, task DAGs, and approval gates.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from src.brain.db import get_connection

class WorkflowStep(BaseModel):
    step_index: int
    name: str
    description: str
    action: str
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, SKIPPED, WAITING_APPROVAL
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False

class WorkflowInstance(BaseModel):
    workflow_id: str
    name: str
    workflow_type: str
    status: str = "ACTIVE"  # ACTIVE, WAITING_INPUT, WAITING_APPROVAL, COMPLETED, CANCELLED
    current_step: int = 0
    steps: List[WorkflowStep] = Field(default_factory=list)
    context_data: Dict[str, Any] = Field(default_factory=dict)
    results: Dict[str, Any] = Field(default_factory=dict)
    approval_state: str = "NONE"  # NONE, PENDING, APPROVED, REJECTED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

WORKFLOW_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "photoday_launch": {
        "name": "Запуск фотодня под ключ",
        "steps": [
            {"name": "audit_context", "description": "Анализ профиля, жанра и аудитории", "action": "audit", "requires_approval": False},
            {"name": "concept_and_visual_logic", "description": "Разработка концепции, цветовой палитры и стиля", "action": "concept", "requires_approval": False},
            {"name": "package_architecture", "description": "Формирование пакетов, тайминга слотов и цен", "action": "pricing", "requires_approval": True},
            {"name": "announcement_post", "description": "Создание вовлекающего анонсирующего поста", "action": "content", "requires_approval": False},
            {"name": "stories_sequence", "description": "Прогревочная серия Stories из 5 кадров", "action": "stories", "requires_approval": False},
            {"name": "reels_script", "description": "Сценарий Reels с хуком и визуальным рядом", "action": "reels", "requires_approval": False},
            {"name": "client_dm_template", "description": "Шаблон ответа клиентам в Direct / Telegram", "action": "sales", "requires_approval": True},
            {"name": "launch_checklist", "description": "Финальный чек-лист подготовки и тайминга", "action": "checklist", "requires_approval": False}
        ]
    },
    "no_content_emergency": {
        "name": "Скорая помощь: Мне нечего выложить",
        "steps": [
            {"name": "mine_context", "description": "Поиск неиспользованных идей, съемок и актуального сезона", "action": "mine", "requires_approval": False},
            {"name": "generate_angles", "description": "3 готовых идеи публикаций с хуками", "action": "ideas", "requires_approval": False},
            {"name": "draft_priority_post", "description": "Полный черновик приоритетного поста в стиле фотографа", "action": "draft", "requires_approval": False}
        ]
    },
    "client_chat_analysis": {
        "name": "Анализ переписки и закрытие сделки",
        "steps": [
            {"name": "reconstruct_dialogue", "description": "Разбор сообщений клиента и эмоционального фона", "action": "parse", "requires_approval": False},
            {"name": "diagnose_objection", "description": "Определение истинной причины сомнений клиента", "action": "diagnose", "requires_approval": False},
            {"name": "consultative_strategy", "description": "Формирование мягкой консультационной стратегии", "action": "strategy", "requires_approval": False},
            {"name": "draft_response", "description": "Подготовка заботливого ответа без давления", "action": "draft_message", "requires_approval": True},
            {"name": "schedule_followup", "description": "Постановка задачи на follow-up", "action": "task", "requires_approval": False}
        ]
    },
    "shoot_preparation": {
        "name": "Полная подготовка к съёмке",
        "steps": [
            {"name": "concept_definition", "description": "Определение настроения, идеи и ассоциаций", "action": "concept", "requires_approval": False},
            {"name": "visual_logic", "description": "Свет, цветовая гамма, локация, образы и реквизит", "action": "visuals", "requires_approval": False},
            {"name": "shot_list_and_timing", "description": "Покадровый план съёмки и хронометраж", "action": "shotlist", "requires_approval": False},
            {"name": "client_memo", "description": "Памятка клиенту по гардеробу и подготовке", "action": "memo", "requires_approval": True}
        ]
    },
    "daily_planning": {
        "name": "Ежедневное планирование фотографа",
        "steps": [
            {"name": "scan_workspace", "description": "Сканирование съемок, дедлайнов и зависших клиентов", "action": "scan", "requires_approval": False},
            {"name": "priorities_synthesis", "description": "Формирование топ-3 фокусных действий на день", "action": "prioritize", "requires_approval": False}
        ]
    },
    "voice_to_content": {
        "name": "Голосовая заметка в контент-пак",
        "steps": [
            {"name": "stt_parsing", "description": "Извлечение историй, драматургии и бизнес-инсайтов", "action": "parse_voice", "requires_approval": False},
            {"name": "derivative_pack", "description": "Генерация 1 поста, 2 рилс, серии сторис и задачи", "action": "generate_pack", "requires_approval": False}
        ]
    }
}

class WorkflowEngine:
    def __init__(self):
        pass

    def start_workflow(self, workflow_type: str, initial_context: Optional[Dict[str, Any]] = None, name: Optional[str] = None) -> WorkflowInstance:
        template = WORKFLOW_TEMPLATES.get(workflow_type)
        if not template:
            template = {
                "name": f"Пользовательский workflow ({workflow_type})",
                "steps": [
                    {"name": "step_1", "description": "Выполнение задачи", "action": "execute", "requires_approval": False}
                ]
            }

        wf_id = str(uuid.uuid4())
        steps = [
            WorkflowStep(
                step_index=idx,
                name=s["name"],
                description=s["description"],
                action=s["action"],
                requires_approval=s.get("requires_approval", False),
                status="IN_PROGRESS" if idx == 0 else "PENDING"
            )
            for idx, s in enumerate(template["steps"])
        ]

        instance = WorkflowInstance(
            workflow_id=wf_id,
            name=name or template["name"],
            workflow_type=workflow_type,
            status="ACTIVE",
            current_step=0,
            steps=steps,
            context_data=initial_context or {},
            results={},
            approval_state="PENDING" if steps[0].requires_approval else "NONE"
        )
        self._save_instance(instance)
        return instance

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInstance]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_instance(row)

    def get_active_workflow_by_type(self, workflow_type: str) -> Optional[WorkflowInstance]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        SELECT * FROM workflows 
        WHERE workflow_type = ? AND status IN ('ACTIVE', 'WAITING_INPUT', 'WAITING_APPROVAL')
        ORDER BY updated_at DESC LIMIT 1
        """, (workflow_type,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_instance(row)

    def advance_step(self, workflow_id: str, step_output: Dict[str, Any], next_inputs: Optional[Dict[str, Any]] = None) -> WorkflowInstance:
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        curr_idx = wf.current_step
        if curr_idx < len(wf.steps):
            wf.steps[curr_idx].status = "COMPLETED"
            wf.steps[curr_idx].outputs = step_output
            wf.results[wf.steps[curr_idx].name] = step_output

        next_idx = curr_idx + 1
        if next_idx >= len(wf.steps):
            wf.status = "COMPLETED"
            wf.current_step = curr_idx
            wf.approval_state = "NONE"
        else:
            wf.current_step = next_idx
            wf.steps[next_idx].status = "IN_PROGRESS"
            if next_inputs:
                wf.steps[next_idx].inputs = next_inputs
            if wf.steps[next_idx].requires_approval:
                wf.status = "WAITING_APPROVAL"
                wf.approval_state = "PENDING"
            else:
                wf.status = "ACTIVE"
                wf.approval_state = "NONE"

        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_instance(wf)
        return wf

    def approve_step(self, workflow_id: str, approved: bool = True) -> WorkflowInstance:
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        curr_idx = wf.current_step
        if approved:
            wf.approval_state = "APPROVED"
            wf.steps[curr_idx].status = "APPROVED"
            wf.status = "ACTIVE"
        else:
            wf.approval_state = "REJECTED"
            wf.steps[curr_idx].status = "REJECTED"
            wf.status = "WAITING_INPUT"

        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_instance(wf)
        return wf

    def execute_step(self, workflow_id: str, profile: Optional[Any] = None) -> Tuple[WorkflowInstance, Dict[str, Any]]:
        """
        Executes the current step using the corresponding domain engine,
        records the output, and advances the workflow state.
        """
        from src.brain.engines.content_engine import ContentEngine
        from src.brain.engines.sales_engine import SalesEngine
        from src.brain.engines.shooting_engine import ShootingEngine
        from src.brain.engines.voice_engine import VoiceEngine
        from src.brain.engines.proactive_engine import ProactiveEngine

        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        curr_step = wf.steps[wf.current_step]
        action = curr_step.action
        ctx = wf.context_data
        output = {}

        if action == "mine":
            ce = ContentEngine()
            angles = ce.emergency_content_recovery(profile=profile)
            output = {"mined_angles": angles}
        elif action == "ideas":
            ce = ContentEngine()
            output = {"ideas": ce.emergency_content_recovery(profile=profile)}
        elif action == "draft":
            ce = ContentEngine()
            fmt = ce.build_format_prompt("post")
            output = {"draft_prompt": fmt, "draft_text": f"Черновик поста готов на основе контекста {wf.name}"}
        elif action in ["concept", "visuals"]:
            se = ShootingEngine()
            theme = ctx.get("theme", "Индивидуальный портрет")
            output = se.build_visual_logic(theme)
        elif action == "pricing":
            sa = SalesEngine()
            packages = ctx.get("packages", [{"name": "Стандарт", "price": 15000, "duration_hours": 1, "retouched_photos": 20}])
            output = sa.evaluate_pricing_ladder(packages)
        elif action == "content":
            ce = ContentEngine()
            output = {"post_template": ce.build_format_prompt("post")}
        elif action == "stories":
            ce = ContentEngine()
            output = {"stories_template": ce.build_format_prompt("stories")}
        elif action == "reels":
            ce = ContentEngine()
            output = {"reels_template": ce.build_format_prompt("reels")}
        elif action == "sales":
            sa = SalesEngine()
            output = {"dm_template": sa.generate_objection_response("дорого", profile=profile)}
        elif action == "checklist":
            se = ShootingEngine()
            output = {"checklist": se.generate_client_prep_memo("Участник фотодня")}
        elif action == "parse":
            sa = SalesEngine()
            dialogue = ctx.get("dialogue", "Здравствуйте! Сколько стоит?")
            output = sa.analyze_client_dialogue(dialogue)
        elif action == "diagnose":
            sa = SalesEngine()
            dialogue = ctx.get("dialogue", "Здравствуйте! Это слишком дорого.")
            output = sa.analyze_client_dialogue(dialogue)
        elif action == "strategy":
            sa = SalesEngine()
            dialogue = ctx.get("dialogue", "Здравствуйте! Это слишком дорого.")
            diag = sa.analyze_client_dialogue(dialogue)
            output = {"strategy": diag.get("recommended_strategy", "Раскрыть ценность подготовки и сервиса")}
        elif action == "draft_message":
            sa = SalesEngine()
            output = {"response": sa.generate_objection_response("дорого", profile=profile)}
        elif action == "shotlist":
            se = ShootingEngine()
            output = {"shot_list": se.generate_shot_list(60)}
        elif action == "memo":
            se = ShootingEngine()
            output = {"memo": se.generate_client_prep_memo("Герой съемки")}
        elif action == "scan":
            pe = ProactiveEngine()
            output = pe.generate_daily_plan(profile=profile)
        elif action == "prioritize":
            pe = ProactiveEngine()
            output = pe.generate_daily_plan(profile=profile)
        elif action in ["parse_voice", "generate_pack"]:
            ve = VoiceEngine()
            transcript = ctx.get("transcript", "Вчера была отличная съемка!")
            output = ve.process_voice_transcript(transcript, profile=profile)
        else:
            output = {"status": "completed", "action": action}

        updated_wf = self.advance_step(workflow_id, output)
        return updated_wf, output

    def _save_instance(self, wf: WorkflowInstance):
        conn = get_connection()
        c = conn.cursor()
        steps_json = json.dumps([s.model_dump() for s in wf.steps], ensure_ascii=False)
        context_json = json.dumps(wf.context_data, ensure_ascii=False)
        results_json = json.dumps(wf.results, ensure_ascii=False)

        c.execute("""
        INSERT INTO workflows (workflow_id, name, workflow_type, status, current_step, steps_json, context_json, results_json, approval_state, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workflow_id) DO UPDATE SET
            status=excluded.status,
            current_step=excluded.current_step,
            steps_json=excluded.steps_json,
            context_json=excluded.context_json,
            results_json=excluded.results_json,
            approval_state=excluded.approval_state,
            updated_at=excluded.updated_at
        """, (
            wf.workflow_id, wf.name, wf.workflow_type, wf.status,
            wf.current_step, steps_json, context_json, results_json,
            wf.approval_state, wf.created_at, wf.updated_at
        ))
        conn.commit()
        conn.close()

    def _row_to_instance(self, row: Any) -> WorkflowInstance:
        steps_data = json.loads(row["steps_json"] or "[]")
        steps = [WorkflowStep(**s) for s in steps_data]
        return WorkflowInstance(
            workflow_id=row["workflow_id"],
            name=row["name"],
            workflow_type=row["workflow_type"],
            status=row["status"],
            current_step=row["current_step"],
            steps=steps,
            context_data=json.loads(row["context_json"] or "{}"),
            results=json.loads(row["results_json"] or "{}"),
            approval_state=row["approval_state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
