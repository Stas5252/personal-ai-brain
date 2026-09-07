"""
FastAPI Routes for Brain Internal API.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from src.brain.config import BRAIN_API_KEY
from src.brain.models.profile import UserProfile
from src.brain.models.memory import MemoryItem, MemoryType, MemoryStatus
from src.brain.models.knowledge import KnowledgeLayer
from src.brain.models.style import ExemplarType, ExemplarCategory
from src.brain.models.client import ClientStatus
from src.brain.models.project import ProjectStatus
from src.brain.services.brain_service import BrainService

router = APIRouter(prefix="/brain", tags=["brain"])
brain = BrainService()

# --- Request/Response Schemas ---
class ChatRequest(BaseModel):
    query: str
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
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNING
    client_id: Optional[str] = None
    deadline: Optional[str] = None

class ClientCreateRequest(BaseModel):
    name: str
    contact: str = ""
    status: ClientStatus = ClientStatus.LEAD
    service: str = ""
    budget: str = ""
    preferences: str = ""
    objections: str = ""

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

from src.brain.api.security import verify_brain_api_key

# Mandatory Auth dependency
verify_token = verify_brain_api_key

# --- Endpoints ---
@router.post("/chat", dependencies=[Depends(verify_token)])
def chat_endpoint(req: ChatRequest):
    res = brain.process_chat(
        query=req.query,
        project_id=req.project_id,
        client_id=req.client_id,
        preferred_model=req.model,
        auto_admission=req.auto_admission,
        conversation_history=req.conversation_history,
        images=req.images,
        audio_path=req.audio_path
    )
    return res

@router.post("/memory", dependencies=[Depends(verify_token)])
def add_memory(req: MemoryCreateRequest):
    try:
        item = brain.memory_engine.add_memory(
            content=req.content,
            memory_type=req.type,
            importance=req.importance,
            project_id=req.project_id,
            client_id=req.client_id
        )
        return item.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/memory", dependencies=[Depends(verify_token)])
def get_memories(
    status: MemoryStatus = MemoryStatus.ACTIVE,
    type: Optional[MemoryType] = None,
    project_id: Optional[str] = None,
    client_id: Optional[str] = None
):
    items = brain.memory_engine.get_memories(
        status=status, memory_type=type, project_id=project_id, client_id=client_id
    )
    return [i.model_dump() for i in items]

@router.delete("/memory/user", dependencies=[Depends(verify_token)])
def purge_memories():
    brain.memory_engine.purge_all()
    return {"status": "purged", "count": 0}

@router.delete("/memory/{memory_id}", dependencies=[Depends(verify_token)])
def delete_memory(memory_id: str):
    brain.memory_engine.delete_memory(memory_id)
    return {"status": "deleted", "id": memory_id}

@router.post("/profile", dependencies=[Depends(verify_token)])
def save_profile(profile: UserProfile):
    saved = brain.profile_engine.save_profile(profile)
    return saved.model_dump()

@router.get("/profile", dependencies=[Depends(verify_token)])
def get_profile():
    return brain.profile_engine.get_profile().model_dump()

@router.post("/projects", dependencies=[Depends(verify_token)])
def create_project(req: ProjectCreateRequest):
    proj = brain.create_project(
        name=req.name, description=req.description,
        status=req.status, client_id=req.client_id, deadline=req.deadline
    )
    return proj.model_dump()

@router.get("/projects/{project_id}", dependencies=[Depends(verify_token)])
def get_project(project_id: str):
    proj = brain.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj.model_dump()

@router.post("/clients", dependencies=[Depends(verify_token)])
def create_client(req: ClientCreateRequest):
    client = brain.create_client(
        name=req.name, contact=req.contact, status=req.status,
        service=req.service, budget=req.budget, preferences=req.preferences, objections=req.objections
    )
    return client.model_dump()

@router.get("/clients/{client_id}", dependencies=[Depends(verify_token)])
def get_client(client_id: str):
    client = brain.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client.model_dump()

@router.post("/knowledge", dependencies=[Depends(verify_token)])
def add_knowledge(req: KnowledgeCreateRequest):
    meta, chunks = brain.knowledge_engine.add_source(
        title=req.title,
        content=req.content,
        layer=req.layer,
        subcategory=req.subcategory,
        tags=req.tags,
        project=req.project,
        client=req.client
    )
    return {"metadata": meta.model_dump(), "chunks_count": len(chunks)}

@router.get("/knowledge", dependencies=[Depends(verify_token)])
def retrieve_knowledge(query: str, layer: Optional[KnowledgeLayer] = None, project: Optional[str] = None, client: Optional[str] = None):
    hits = brain.knowledge_engine.retrieve(query=query, layer=layer, project=project, client=client, limit=5)
    return [{"chunk": h[0].model_dump(), "score": h[1], "trace": h[2].model_dump()} for h in hits]

@router.post("/style/exemplars", dependencies=[Depends(verify_token)])
def add_exemplar(req: ExemplarCreateRequest):
    ex = brain.style_engine.add_exemplar(
        title=req.title, content=req.content,
        exemplar_type=req.exemplar_type, category=req.category, tags=req.tags
    )
    return ex.model_dump()

@router.get("/style/exemplars", dependencies=[Depends(verify_token)])
def get_exemplars(category: Optional[ExemplarCategory] = None, exemplar_type: Optional[ExemplarType] = None):
    exs = brain.style_engine.get_exemplars(category=category, exemplar_type=exemplar_type)
    return [e.model_dump() for e in exs]

@router.post("/route", dependencies=[Depends(verify_token)])
def route_query(req: ChatRequest):
    decision = brain.router.route(req.query)
    return decision.model_dump()

@router.post("/context", dependencies=[Depends(verify_token)])
def assemble_context_preview(req: ChatRequest):
    # Preview context without invoking LLM
    routing = brain.router.route(req.query)
    memories = brain.memory_engine.retrieve_relevant_memories(req.query, limit=5, project_id=req.project_id, client_id=req.client_id)
    knowledge = brain.knowledge_engine.retrieve(req.query, project=req.project_id, client=req.client_id, limit=4)
    profile = brain.profile_engine.get_profile()
    project = brain.get_project(req.project_id) if req.project_id else None
    client = brain.get_client(req.client_id) if req.client_id else None
    style_instr = brain.style_engine.build_style_instructions(StyleProfile(tone=profile.tone, forbidden_expressions=profile.forbidden_words))

    ctx = brain.context_engine.assemble_context(
        query=req.query,
        system_policy=UNIVERSAL_SYSTEM_POLICY,
        profile=profile,
        memories=memories,
        knowledge=knowledge,
        style_instructions=style_instr,
        project=project,
        client=client,
        specialized_prompt=routing.specialized_system_prompt
    )
    return ctx.model_dump()

@router.post("/onboarding/start", dependencies=[Depends(verify_token)])
def start_onboarding():
    session, q = brain.profile_engine.start_onboarding()
    return {"session_id": session.session_id, "first_question": q.model_dump()}

@router.post("/onboarding/answer", dependencies=[Depends(verify_token)])
def answer_onboarding(req: OnboardingAnswerRequest):
    try:
        res = brain.profile_engine.answer_onboarding(req.session_id, req.answer)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/profile", dependencies=[Depends(verify_token)])
def get_user_profile():
    prof = brain.profile_engine.get_profile()
    return prof.model_dump()

@router.post("/profile", dependencies=[Depends(verify_token)])
def save_user_profile(prof: UserProfile):
    updated = brain.profile_engine.save_profile(prof)
    return updated.model_dump()

@router.get("/clients", dependencies=[Depends(verify_token)])
def list_clients():
    from src.brain.db import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM clients ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/traces", dependencies=[Depends(verify_token)])
def get_traces(limit: int = 20):
    return brain.get_traces(limit=limit)
