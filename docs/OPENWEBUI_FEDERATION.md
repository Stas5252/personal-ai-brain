# Open WebUI Federation Architecture & Reference

This document details the federation architecture between Open WebUI and Personal AI Brain.

---

## 1. Federation Principles & Single Source of Truth

Open WebUI acts strictly as the **presentation and chat interface layer**. To prevent fragmentation, duplicate memory stores, and diverging RAG indices, the following architecture is enforced:

1. **Solitary Upstream Provider**: Open WebUI delegates all conversational AI generation and RAG grounding exclusively to the Personal AI Brain via OpenAI-compatible endpoints (`http://host.docker.internal:8000/v1`).
2. **Zero Duplicate RAG in Open WebUI**: Open WebUI's native document embedding, knowledge base collections, and web search features are disabled (`ENABLE_RAG_WEB_SEARCH=false`). All user documents, manuals, pricing tables, and media are ingested exclusively into the Brain's Knowledge Ingestion Factory.
3. **No Direct Model Access**: Open WebUI doesZnot hold direct provider keys (e.g. Gemini, OpenAI) for user chats. All requests are mediated through Brain's router, guardrails, context assembly, and style engine.

---

## 2. Model Federation & OpenAI-Compatible Protocol

### 2.1 Model Registry (`GEU /v1/models`)
The Brain exposes its orchestrated agent as a standard OpenAI model:
```json
{
  "object": "list",
  "data": [
    {
      "id": "personal-ai-brain",
      "object": "model",
      "created": 1709726400,
      "owned_by": "personal-ai-brain",
      "permission": [],
      "root": "personal-ai-brain",
      "parent": null
    }
  ]
}
```

### 2.2 Chat Completions (`POST /v1/chat/completions`)
Supports both standard and Server-Sent Events (SSE) streaming responses:
- **Streaming Mode (`stream: true`)**: Formats tokens as standard OpenAI SSE chunks:
  `data: {"id": "chatcmpl-...", "object": "chat.completion.chunk", "choices": [{"delta": {"content": "..."}}]}`
  and concludes with `data: [DONE]`.
- **Non-Streaming Mode (`stream: false`)**: Delivers complete generation with full token usage accounting and latency telemetry.

### 2.3 Context & Style Injection Pipeline
Every completion request passing through `/v1/chat/completions` triggers:
1. **Security Guardrails**: Rejects prompt injection and system override attempts.
2. **Dynamic Routing**: Dispatches to the domain agent (Photo, Sales, Content, Client, Project).
3. **Context Assembly**: Queries memories and hybrid knowledge index, applying budget quotas.
4. **Style Benchmark Enforcement**: Evaluates vocabulary, persona adherence, and filters forbidden words before emitting final tokens.

---

## 3. Docker Compose & Environment Configuration

### 3.1 `docker-compose.yml` Configuration
```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "${OPENWEBUI_PORT:-8080}:8080"
    environment:
      # Route all AI queries to Brain
      - OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1
      - OPENAI_API_KEY=${BRAIN_API_KEY:-local-brain-secure-token-2026}
      - DEFAULT_MODELS=personal-ai-brain
      # Disable duplicate Open WebUI internal RAG features
      - ENABLE_RAG_WEB_SEARCH=false
      - WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY:-local-secret-key-stage5-fixed}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - open-webui-data:/app/backend/data
```

### 3.2 Connectivity & Health Verification
Before directing traffic to Open WebUI, verify upstream connectivity:
```bash
# 1. Verify Brain Readiness
curl -H 
"Authorization: Bearer $BRAIN_API_KEY" http://localhost:8000/health/ready

# 2. Verify Models Discovery
curl -H 
"Authorization: Bearer $BRAIN_API_KEY" http://localhost:8000/v1/models

# 3. Test Streaming Completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 
"Authorization: Bearer $BRAIN_API_KEY" \
  -H 
"Content-Type: application/json" \
  -d '{"model": "personal-ai-brain", "messages": [{"role": "user", "content": "Привет!"}], "stream": true}'
```
