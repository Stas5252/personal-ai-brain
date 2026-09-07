"""
OpenAI-Compatible Routes for Open WebUI & External LLM Clients Integration.
Supports SSE streaming, mandatory bearer authentication, and Brain orchestration.
"""
import time
import uuid
import json
import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.brain.services.brain_service import BrainService
from src.brain.api.security import verify_brain_api_key

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

@router.get("/models", dependencies=[Depends(verify_brain_api_key)])
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "personal-ai-brain",
                "object": "model",
                "created": 1788682000,
                "owned_by": "personal-ai-brain",
                "name": "Personal AI Brain (Stage 5 Orchestrator)"
            }
        ]
    }

@router.post("/chat/completions", dependencies=[Depends(verify_brain_api_key)])
def openai_chat_completions(req: OpenAIChatRequest):
    # Extract last user message and history
    user_query = ""
    images = []
    history = []

    for idx, m in enumerate(req.messages):
        if idx == len(req.messages) - 1 and m.role == "user":
            if isinstance(m.content, str):
                user_query = m.content
            elif isinstance(m.content, list):
                for part in m.content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            user_query += part.get("text", "")
                        elif part.get("type") == "image_url":
                            img_url = part.get("image_url", {}).get("url", "")
                            if img_url:
                                images.append(img_url)
        else:
            text_content = ""
            if isinstance(m.content, str):
                text_content = m.content
            elif isinstance(m.content, list):
                for part in m.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_content += part.get("text", "")
            if text_content:
                history.append({"role": m.role, "content": text_content})
            
    if not user_query:
        user_query = "Привет"

    # Delegate to Brain Service with multi-turn history and images
    res = brain.process_chat(
        query=user_query,
        conversation_history=history,
        images=images if images else None
    )

    response_id = f"brain-chat-{uuid.uuid4().hex[:12]}"
    prompt_tokens = res["context_summary"].get("estimated_tokens", 50)
    completion_tokens = max(1, len(res["response"]) // 4)
    model_name = req.model or "personal-ai-brain"

    if req.stream:
        def sse_generator():
            full_text = res["response"]
            created_ts = int(time.time())
            # Stream in natural token fragments
            tokens = re.findall(r"\S+|\s+", full_text)
            for tok in tokens:
                chunk_obj = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": tok},
                            "finish_reason": None
                        }
                    ]
                }
                yield f"data: {json.dumps(chunk_obj, ensure_ascii=False)}\n\n"

            # Final finish stop chunk
            final_obj = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(final_obj, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    return {
        "id": response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
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
