"""
OpenAI-Compatible Routes for Open WebUI & External LLM Clients Integration.
"""
import time
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from src.brain.services.brain_service import BrainService

router = APIRouter(prefix="/v1", tags=["openai"])
brain = BrainService()

class OpenAIMessage(BaseModel):
    role: str
    content: Any

class OpenAIChatRequest(BaseModel):
    model: str = "personal-ai-brain"
    messages: List[OpenAIMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7

@router.get("/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "personal-ai-brain",
                "object": "model",
                "created": 1788682000,
                "owned_by": "personal-ai-brain",
                "name": "Personal AI Brain (Stage 2 Orchestrator)"
            }
        ]
    }

@router.post("/chat/completions")
def openai_chat_completions(req: OpenAIChatRequest):
    # Extract last user message
    user_query = ""
    for m in reversed(req.messages):
        if m.role == "user":
            if isinstance(m.content, str):
                user_query = m.content
            elif isinstance(m.content, list):
                for part in m.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        user_query += part.get("text", "")
            break
            
    if not user_query:
        user_query = "Привет"

    # Delegate to Brain Service
    res = brain.process_chat(query=user_query)

    response_id = f"brain-chat-{uuid.uuid4().hex[:12]}"
    prompt_tokens = res["context_summary"].get("estimated_tokens", 50)
    completion_tokens = max(1, len(res["response"]) // 4)

    return {
        "id": response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "personal-ai-brain",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": res["response"]
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        },
        "brain_trace": res["trace"]
    }
