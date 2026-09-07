"""Authenticated single-owner Brain API. Profile routes are registered once."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from src.brain.config import DATA_DIR
from src.brain.models.profile import UserProfile
from src.brain.models.memory import MemoryType, MemoryStatus
from src.brain.models.knowledge import KnowledgeLayer
from src.brain.models.style import ExemplarType, ExemplarCategory, StyleProfile
from src.brain.models.client import ClientStatus
from src.brain.models.project import ProjectStatus
from src.brain.models.task import TaskPriority, TaskStatus, ApprovalState
from src.brain.prompts.system_policy import UNIVERSAL_SYSTEM_POLICY
from src.brain.services.brain_service import BrainService
from src.brain.api.security import verify_brain_api_key

router = APIRouter(prefix='/brain', tags=['brain'])
brain = BrainService()
verify_token = verify_brain_api_key


class ChatRequest(BaseModel):
    query: str = Field(max_length=32000)
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    model: Optional[str] = None
    auto_admission: bool = True
    conversation_history: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    audio_path: Optional[str] = None


class MemoryCreateRequest(BaseModel):
    content: str
    type: Optional[MemoryType] = None
    importance: Optional[float] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ''
    status: ProjectStatus = ProjectStatus.PLANNING
    client_id: Optional[str] = None
    deadline: Optional[str] = None


class ClientCreateRequest(BaseModel):
    name: str
    contact: str = ''
    status: ClientStatus = ClientStatus.LEAD
    service: str = ''
    budget: str = ''
    preferences: str = ''
    objections: str = ''


class KnowledgeCreateRequest(BaseModel):
    title: str
    content: str
    layer: KnowledgeLayer
    subcategory: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    project: Optional[str] = None
    client: Optional[str] = None


class ExemplarCreateRequest(BaseModel):
    title: str
    content: str
    exemplar_type: ExemplarType = ExemplarType.GOOD_EXAMPLE
    category: ExemplarCategory = ExemplarCategory.POST
    tags: List[str] = Field(default_factory=list)


class OnboardingAnswerRequest(BaseModel):
    session_id: str
    answer: str


class WorkflowStartRequest(BaseModel):
    workflow_type: str
    initial_context: Optional[Dict[str, Any]] = None
    name: Optional[str] = None


class WorkflowApproveRequest(BaseModel):
    approved: bool = True


class TaskCreateRequest(BaseModel):
    title: str
    type: str = "general"
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    approval_state: ApprovalState = ApprovalState.NONE


class TaskUpdateRequest(BaseModel):
    status: Optional[TaskStatus] = None
    approval_state: Optional[ApprovalState] = None


@router.post('/chat', dependencies=[Depends(verify_token)])
def chat_endpoint(req: ChatRequest):
    from src.brain.channels.runtime_state import process_request
    try:
        return process_request(brain, req.query, DATA_DIR / 'uploads',
                               images=req.images, audio_path=req.audio_path,
                               project_id=req.project_id, client_id=req.client_id,
                               preferred_model=req.model, auto_admission=req.auto_admission,
                               conversation_history=req.conversation_history)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.post('/memory', dependencies=[Depends(verify_token)])
def add_memory(req: MemoryCreateRequest):
    try:
        return brain.memory_engine.add_memory(content=req.content, memory_type=req.type,
            importance=req.importance, project_id=req.project_id, client_id=req.client_id).model_dump()
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get('/memory', dependencies=[Depends(verify_token)])
def get_memories(status: MemoryStatus = MemoryStatus.ACTIVE, type: Optional[MemoryType] = None,
                 project_id: Optional[str] = None, client_id: Optional[str] = None):
    return [item.model_dump() for item in brain.memory_engine.get_memories(
        status=status, memory_type=type, project_id=project_id, client_id=client_id)]


@router.delete('/memory/user', dependencies=[Depends(verify_token)])
def purge_memories():
    brain.memory_engine.purge_all()
    return {'status': 'purged', 'count': 0}


@router.delete('/memory/{memory_id}', dependencies=[Depends(verify_token)])
def delete_memory(memory_id: str):
    brain.memory_engine.delete_memory(memory_id)
    return {'status': 'deleted', 'id': memory_id}


@router.post('/profile', dependencies=[Depends(verify_token)])
def save_profile(profile: UserProfile):
    return brain.profile_engine.save_profile(profile).model_dump()


@router.get('/profile', dependencies=[Depends(verify_token)])
def get_profile():
    return brain.profile_engine.get_profile().model_dump()


@router.post('/projects', dependencies=[Depends(verify_token)])
def create_project(req: ProjectCreateRequest):
    return brain.create_project(**req.model_dump()).model_dump()


@router.get('/projects/{project_id}', dependencies=[Depends(verify_token)])
def get_project(project_id: str):
    project = brain.get_project(project_id)
    if not project:
        raise HTTPException(404, 'Project not found')
    return project.model_dump()


@router.post('/clients', dependencies=[Depends(verify_token)])
def create_client(req: ClientCreateRequest):
    return brain.create_client(**req.model_dump()).model_dump()


@router.get('/clients/{client_id}', dependencies=[Depends(verify_token)])
def get_client(client_id: str):
    client = brain.get_client(client_id)
    if not client:
        raise HTTPException(404, 'Client not found')
    return client.model_dump()


@router.post('/knowledge', dependencies=[Depends(verify_token)])
def add_knowledge(req: KnowledgeCreateRequest):
    metadata, chunks = brain.knowledge_engine.add_source(**req.model_dump())
    return {'metadata': metadata.model_dump(), 'chunks_count': len(chunks)}


@router.get('/knowledge', dependencies=[Depends(verify_token)])
def retrieve_knowledge(query: str, layer: Optional[KnowledgeLayer] = None,
                       project: Optional[str] = None, client: Optional[str] = None):
    hits = brain.knowledge_engine.retrieve(query=query, layer=layer, project=project, client=client, limit=5)
    return [{'chunk': hit[0].model_dump(), 'score': hit[1], 'trace': hit[2].model_dump()} for hit in hits]


@router.post('/style/exemplars', dependencies=[Depends(verify_token)])
def add_exemplar(req: ExemplarCreateRequest):
    return brain.style_engine.add_exemplar(**req.model_dump()).model_dump()


@router.get('/style/exemplars', dependencies=[Depends(verify_token)])
def get_exemplars(category: Optional[ExemplarCategory] = None, exemplar_type: Optional[ExemplarType] = None):
    return [ex.model_dump() for ex in brain.style_engine.get_exemplars(category=category, exemplar_type=exemplar_type)]


@router.post('/route', dependencies=[Depends(verify_token)])
def route_query(req: ChatRequest):
    return brain.router.route(req.query).model_dump()


@router.post('/context', dependencies=[Depends(verify_token)])
def assemble_context_preview(req: ChatRequest):
    routing = brain.router.route(req.query)
    memories = brain.memory_engine.retrieve_relevant_memories(req.query, limit=5,
        project_id=req.project_id, client_id=req.client_id)
    knowledge = brain.knowledge_engine.retrieve(req.query, project=req.project_id, client=req.client_id, limit=4)
    profile = brain.profile_engine.get_profile()
    project = brain.get_project(req.project_id) if req.project_id else None
    client = brain.get_client(req.client_id) if req.client_id else None
    style_instr = brain.style_engine.build_style_instructions(
        StyleProfile(tone=profile.tone, forbidden_expressions=profile.forbidden_words))
    return brain.context_engine.assemble_context(query=req.query, system_policy=UNIVERSAL_SYSTEM_POLICY,
        profile=profile, memories=memories, knowledge=knowledge, style_instructions=style_instr,
        project=project, client=client, specialized_prompt=routing.specialized_system_prompt).model_dump()


@router.post('/onboarding/start', dependencies=[Depends(verify_token)])
def start_onboarding():
    session, question = brain.profile_engine.start_onboarding()
    return {'session_id': session.session_id, 'first_question': question.model_dump()}


@router.post('/onboarding/answer', dependencies=[Depends(verify_token)])
def answer_onboarding(req: OnboardingAnswerRequest):
    try:
        return brain.profile_engine.answer_onboarding(req.session_id, req.answer)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get('/clients', dependencies=[Depends(verify_token)])
def list_clients():
    from src.brain.db import get_connection
    conn = get_connection()
    try:
        return [dict(row) for row in conn.execute('SELECT * FROM clients ORDER BY created_at DESC')]
    finally:
        conn.close()


@router.get('/traces', dependencies=[Depends(verify_token)])
def get_traces(limit: int = 20):
    return brain.get_traces(limit=limit)


@router.post('/workflows/start', dependencies=[Depends(verify_token)])
def start_workflow(req: WorkflowStartRequest):
    wf = brain.start_workflow(req.workflow_type, initial_context=req.initial_context, name=req.name)
    return wf.model_dump()


@router.get('/workflows/{workflow_id}', dependencies=[Depends(verify_token)])
def get_workflow(workflow_id: str):
    wf = brain.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, 'Workflow not found')
    return wf.model_dump()


@router.post('/workflows/{workflow_id}/execute', dependencies=[Depends(verify_token)])
def execute_workflow_step(workflow_id: str):
    try:
        wf, output = brain.execute_workflow_step(workflow_id)
        return {'workflow': wf.model_dump(), 'step_output': output}
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@router.post('/workflows/{workflow_id}/approve', dependencies=[Depends(verify_token)])
def approve_workflow_step(workflow_id: str, req: Optional[WorkflowApproveRequest] = None):
    approved = req.approved if req is not None else True
    try:
        wf = brain.approve_workflow_step(workflow_id, approved=approved)
        return wf.model_dump()
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@router.post('/workflows/{workflow_id}/cancel', dependencies=[Depends(verify_token)])
def cancel_workflow_step(workflow_id: str):
    try:
        wf = brain.cancel_workflow(workflow_id)
        return wf.model_dump()
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@router.get('/tasks', dependencies=[Depends(verify_token)])
def list_tasks(status: Optional[TaskStatus] = None, project_id: Optional[str] = None, client_id: Optional[str] = None):
    tasks = brain.list_tasks(status=status, project_id=project_id, client_id=client_id)
    return [t.model_dump() for t in tasks]


@router.post('/tasks', dependencies=[Depends(verify_token)])
def create_task(req: TaskCreateRequest):
    task = brain.create_task(
        title=req.title,
        task_type=req.type,
        priority=req.priority,
        due_at=req.due_at,
        project_id=req.project_id,
        client_id=req.client_id,
        inputs=req.inputs,
        outputs=req.outputs,
        approval_state=req.approval_state
    )
    return task.model_dump()


@router.get('/tasks/{task_id}', dependencies=[Depends(verify_token)])
def get_task(task_id: str):
    task = brain.get_task(task_id)
    if not task:
        raise HTTPException(404, 'Task not found')
    return task.model_dump()


@router.patch('/tasks/{task_id}', dependencies=[Depends(verify_token)])
def update_task(task_id: str, req: TaskUpdateRequest):
    task = brain.get_task(task_id)
    if not task:
        raise HTTPException(404, 'Task not found')
    st = req.status or task.status
    updated = brain.update_task_status(task_id=task_id, status=st, approval_state=req.approval_state)
    return updated.model_dump()


get_user_profile = get_profile
save_user_profile = save_profile
