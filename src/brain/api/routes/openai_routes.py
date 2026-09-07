"""OpenAI-compatible facade with the same safety rules as the first-party studio."""
import base64
import json
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from src.brain.api.security import verify_brain_api_key
from src.brain.channels.runtime_state import process_request
from src.brain.config import DATA_DIR, MAX_FILE_SIZE_BYTES
from src.brain.services.brain_service import BrainService

router = APIRouter(prefix='/v1', tags=['openai'])
brain = BrainService()


class OpenAIMessage(BaseModel):
    role: str
    content: Any


class OpenAIChatRequest(BaseModel):
    model: str = 'personal-ai-brain'
    messages: List[OpenAIMessage] = Field(min_length=1, max_length=30)
    stream: bool = False
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)


@router.get('/models', dependencies=[Depends(verify_brain_api_key)])
def list_models():
    return {'object': 'list', 'data': [{'id': 'personal-ai-brain', 'object': 'model',
        'created': 1788682000, 'owned_by': 'personal-ai-brain', 'name': 'Personal AI Brain'}]}


def _text_and_images(content):
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return '', []
    text = []
    images = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get('type') == 'text':
            text.append(str(part.get('text', '')))
        elif part.get('type') == 'image_url':
            url = part.get('image_url', {}).get('url', '')
            if url:
                images.append(url)
    return ''.join(text), images


def _save_data_images(images, root):
    paths = []
    for image in images:
        match = re.fullmatch(r'data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)', image)
        if not match:
            raise HTTPException(422, 'Only inline data images are accepted by this single-owner gateway.')
        raw = base64.b64decode(match.group(2), validate=True)
        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(413, 'Image exceeds configured size limit.')
        suffix = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}[match.group(1)]
        root.mkdir(parents=True, exist_ok=True)
        path = root / f'openai_{uuid.uuid4().hex}{suffix}'
        path.write_bytes(raw)
        paths.append(path)
    return paths


def _request(req):
    last = req.messages[-1]
    if last.role != 'user':
        raise HTTPException(422, 'The final message must be from the user.')
    user_query, image_urls = _text_and_images(last.content)
    history = []
    for message in req.messages[:-1]:
        text, _ = _text_and_images(message.content)
        if text:
            history.append({'role': message.role, 'content': text})
    if not user_query and not image_urls:
        raise HTTPException(422, 'The final user message is empty.')
    if len(user_query) > 32000 or sum(len(str(item.get('content', ''))) for item in history) > 64000:
        raise HTTPException(413, 'Conversation is too large.')
    with tempfile.TemporaryDirectory(prefix='brain-openai-') as work:
        images = _save_data_images(image_urls, Path(DATA_DIR) / 'uploads') if image_urls else None
        try:
            return process_request(brain, user_query or 'Проанализируй приложенное изображение.',
                DATA_DIR / 'uploads', images=[str(path) for path in images] if images else None,
                conversation_history=history)
        finally:
            for path in images or []:
                path.unlink(missing_ok=True)


@router.post('/chat/completions', dependencies=[Depends(verify_brain_api_key)])
def openai_chat_completions(req: OpenAIChatRequest):
    try:
        result = _request(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    text = result['response']
    response_id = f'brain-chat-{uuid.uuid4().hex[:12]}'
    model_name = req.model or 'personal-ai-brain'
    prompt_tokens = result.get('context_summary', {}).get('estimated_tokens', 50)
    completion_tokens = max(1, len(text) // 4)
    if req.stream:
        def sse_generator():
            created = int(time.time())
            for token in re.findall(r'\S+|\s+', text):
                yield 'data: ' + json.dumps({'id': response_id, 'object': 'chat.completion.chunk',
                    'created': created, 'model': model_name,
                    'choices': [{'index': 0, 'delta': {'content': token}, 'finish_reason': None}]}, ensure_ascii=False) + '\n\n'
            yield 'data: ' + json.dumps({'id': response_id, 'object': 'chat.completion.chunk',
                'created': created, 'model': model_name,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}) + '\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(sse_generator(), media_type='text/event-stream')
    return {'id': response_id, 'object': 'chat.completion', 'created': int(time.time()),
        'model': model_name, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
        'finish_reason': 'stop'}], 'usage': {'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens, 'total_tokens': prompt_tokens + completion_tokens},
        'brain_trace': result.get('trace', {})}
