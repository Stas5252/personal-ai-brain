"""Single-owner API with bounded uploads and explicit media failures."""
import hashlib
import base64
import logging
import uuid
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from src.brain.api.security import verify_brain_api_key
from src.brain.config import DATA_DIR, MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS, GEMINI_API_KEY
from src.brain.channels.runtime_state import confined_file, process_request

log = logging.getLogger(__name__)
app = FastAPI(title='Personal AI Brain', version='2.1.0', docs_url=None, redoc_url=None, openapi_url=None)
UPLOAD_ROOT = DATA_DIR / 'uploads'
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


@app.middleware('http')
async def protect_api(request: Request, call_next):
    if request.url.path not in {'/', '/studio', '/health'}:
        try:
            verify_brain_api_key(request.headers.get('authorization'), request.headers.get('x-brain-api-key'))
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.get('/health')
def health():
    return {'status': 'alive', 'service': 'Personal AI Brain'}


@app.get('/health/ready')
def ready():
    from src.brain.db import get_connection
    try:
        db = get_connection()
        try:
            db.execute('SELECT 1')
        finally:
            db.close()
        storage = UPLOAD_ROOT.is_dir()
        return JSONResponse({'status': 'ready' if storage else 'degraded', 'database': True,
                             'storage': storage, 'model_key_configured': bool(GEMINI_API_KEY),
                             'model_live_check': 'not_run'}, status_code=200 if storage else 503)
    except Exception:
        return JSONResponse({'status': 'degraded', 'database': False}, status_code=503)


@app.get('/', response_class=HTMLResponse)
@app.get('/studio', response_class=HTMLResponse)
def studio_ui():
    content = (Path(__file__).parent.parent / 'web' / 'index.html').read_text(encoding='utf-8')
    script = content.split('<script>', 1)[1].split('</script>', 1)[0]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return HTMLResponse(content, headers={'Content-Security-Policy':
        f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})


async def save_upload(file: UploadFile):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(415, 'Unsupported file extension.')
    path = UPLOAD_ROOT / f'{uuid.uuid4().hex}{suffix}'
    size = 0
    try:
        with path.open('xb') as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(413, 'File exceeds configured size limit.')
                target.write(chunk)
        if not size:
            raise HTTPException(400, 'Empty file.')
        from src.brain.knowledge.storage import StorageManager
        validation = await run_in_threadpool(StorageManager().validate_file, path)
        if not validation.is_valid:
            raise HTTPException(415, 'File content does not match a supported format.')
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@app.post('/api/upload')
async def upload_asset(file: UploadFile = File(...)):
    path = await save_upload(file)
    return {'status': 'success', 'filename': file.filename, 'file_path': str(path),
            'url': f'/api/uploads/{path.name}'}


@app.get('/api/uploads/{filename}')
def uploaded_asset(filename: str):
    try:
        path = confined_file(UPLOAD_ROOT / filename, UPLOAD_ROOT)
    except ValueError:
        raise HTTPException(404, 'File not found.')
    return FileResponse(path, filename=path.name, content_disposition_type='attachment')


@app.post('/api/upload_knowledge')
async def upload_knowledge(file: UploadFile = File(...)):
    path = await save_upload(file)
    try:
        from src.brain.knowledge.factory import KnowledgeIngestionFactory
        def ingest():
            return KnowledgeIngestionFactory().ingest_file(path, title=file.filename)
        source, chunks = await run_in_threadpool(ingest)
        return {'status': 'success', 'filename': file.filename,
                'source_id': source.source_id, 'chunks_count': len(chunks)}
    except Exception:
        log.exception('Knowledge ingestion failed')
        raise HTTPException(422, 'Could not index this file. Check server logs and extractor dependencies.')
    finally:
        path.unlink(missing_ok=True)


from src.brain.api.routes.brain_routes import router as brain_router, brain, ChatRequest


@app.post('/brain/chat')
def chat(req: ChatRequest):
    if len(req.query) > 32000 or sum(len(str(m.get('content', ''))) for m in (req.conversation_history or [])) > 64000:
        raise HTTPException(413, 'Conversation is too large.')
    try:
        return process_request(brain, req.query, UPLOAD_ROOT, images=req.images, audio_path=req.audio_path,
                               project_id=req.project_id, client_id=req.client_id, preferred_model=req.model,
                               auto_admission=req.auto_admission, conversation_history=req.conversation_history)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


app.include_router(brain_router)
from src.brain.api.routes.openai_routes import router as openai_router
from src.brain.api.routes.knowledge_routes import router as knowledge_router
app.include_router(openai_router)
app.include_router(knowledge_router)
