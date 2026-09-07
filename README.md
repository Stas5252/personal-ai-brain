# Personal AI Brain: reliability repair branch

Personal, single-owner assistant for a photographer. This branch fixes selected security and transport failures; it is **not** a verified production release or proven equivalent to Yaishka.

Historical `docs/FINAL_PRODUCT_ACCEPTANCE.md` and parity claims describe aspirations and are not valid acceptance evidence. No live comparison with Yaishka has been conducted.

## Changes in this branch

- Web UI no longer receives an API key from the server. It accepts your locally configured key, keeps it only in tab memory, and renders untrusted text with `textContent`.
- All API routes except the static studio and liveness endpoint require an explicit bearer/API-key header. Cookies and legacy test tokens do not authenticate.
- Public defaults are rejected. Set a random API key of at least 32 characters.
- Uploads use generated names, bounded copying and content validation. Download and chat file paths must stay within the upload directory.
- Telegram accepts only private messages from `TELEGRAM_OWNER_ID`, because the underlying profile and knowledge remain single-user.
- Telegram intake and processing run separately, with a SQLite inbox, persisted offsets, bounded delivery retries, cached responses and bounded conversation history.
- Voice onboarding uses the actual extractor contract. Failed transcription produces an error, never canned text. Test transcripts require explicit `allow_sidecar=True`.
- Guarded `/brain/chat` and the Telegram runner stop on media/provider failures.
- Deterministic regression tests and a GitHub Actions workflow have been added. They do not establish real model quality.

## Safe local setup (Python 3.12)

First stop old processes and back up the entire `data/` directory. Do not run old and new Telegram pollers simultaneously.

```sh
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Or on Linux/macOS:

```sh
. .venv/bin/activate
cp .env.example .env
```

```sh
python -m pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Store the generated value in `BRAIN_API_KEY` inside `.env`, not in GitHub or chat. Set `GEMINI_API_KEY`, a model ID available to your account, `TELEGRAM_BOT_TOKEN`, and your numeric `TELEGRAM_OWNER_ID`. Install FFmpeg and check `ffmpeg -version`. Whisper and embedding models may download on first use.

Run the studio locally:

```sh
python -m uvicorn src.brain.api.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and enter your `BRAIN_API_KEY`. In another activated terminal:

```sh
python -m src.brain.channels.telegram_runner
```

Telegram commands: `/start`, `/brief`, `/profile`, `/cancel`. A voice message can answer the current brief question. The profile is shared between your own web and Telegram sessions.

Open WebUI is optional. Its `OPENAI_API_KEY` must equal `BRAIN_API_KEY`. Existing docker-compose launches only Open WebUI, not the Brain API or Telegram runner. Do not mistake it for a complete deployment.

## Verification

```sh
python -m compileall -q src
python -m pytest tests/reliability -v
```

The new suite checks owner isolation, history persistence, queue deduplication/retries, upload path confinement, explicit provider failures, transcription failure behavior, API authentication and unsafe browser rendering patterns. Recognition and model responses are mocked in deterministic tests.

In the assistant's restricted Python 3.12 environment: 23 deterministic tests passed; 5 FastAPI-dependent tests were skipped. The audio tests used the inspected extractor contract and reconstructed supporting model declarations, not a complete installed checkout. Python syntax and browser-script syntax were checked separately. Full installation, all legacy tests, browser interaction, real OCR/Whisper, Gemini and Telegram have NOT been certified here. GitHub Actions results must be checked, not assumed green.

Pytest now isolates the database, index paths and working directory before collection. Legacy tests that assume relative fixtures or hardcoded test tokens may need updates; those failures should not be hidden or interpreted as product readiness.

## Live acceptance checklist

1. A random Telegram account and a group cannot access the assistant; your private chat works.
2. Complete the brief with text and real Russian voice, restart the bot, then verify the profile and continued conversation.
3. Ask for two post variants, then ask to shorten the second. Verify the correct previous variant is used.
4. Send a real photograph and a screenshot of a client conversation. Verify the analysis corresponds to their content.
5. Disable the model key and test invalid/silent audio. The assistant must report failure, not invent a transcript or image description.
6. Import an owned document and ask a question whose answer exists only in that document; verify the cited content manually.
7. Check typical and slow requests, cost, quotas, file size limits, interrupted delivery and recovery after restart.

## Remaining work / release blockers

- No implemented end-to-end MAX transport, image-generating moodboards, proactive notification scheduler or paid subscription system is supplied by this repair.
- Domain engines still contain heuristic/template fallbacks. Source overlap scoring is not a hallucination guarantee. Feedback learning and complex workflows still need end-to-end evaluation.
- Legacy `/v1` multimodal handling and direct `BrainService` callers do not use the new media guard. Prefer the studio/Telegram path until that migration is completed.
- OCR/document extraction still contains test-sidecar lookups requiring separate removal and regression coverage.
- The complete legacy suite and dependency compatibility/locking remain to be verified on a clean installation. Dependencies here have bounds, not a reproducible lockfile.
- The Telegram delivery guarantee is at-least-once: a crash between send and acknowledgement can duplicate a message. Final failed deliveries require operator review. Run one runner per bot; database state is not a distributed queue.
- Browser chat history is intentionally tab-local. Telegram history is persisted. Web uploads and request traces need an explicit retention policy; backups and data deletion remain operator responsibilities.
- For remote use, add TLS, a private network or authenticated reverse proxy, request-body limits before multipart parsing, rate limits, monitoring and encrypted backups. Do not expose the development server directly to the internet.
- Local storage does not mean fully local processing: prompts and images may go to the configured external provider; API usage can cost money.

A release is accepted only after the live checks succeed with real inputs and results are recorded. More files or green mocked tests do not prove parity with a commercial assistant.
