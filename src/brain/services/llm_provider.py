"""
LLM Provider Integration with Multi-Model Fallback and Upstream Quota Protection.
"""
import logging
import time
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Tuple, Optional
from src.brain.config import (
    UPSTREAM_LLM_BASE_URL, GEMINI_API_KEY, DEFAULT_MODEL, FALLBACK_MODELS
)
from src.brain.services import knowledge_grounding as grounding

log = logging.getLogger(__name__)

class LLMProvider:
    def __init__(self):
        self.base_url = UPSTREAM_LLM_BASE_URL.rstrip("/")
        self.api_key = GEMINI_API_KEY
        # Titles of the owner's own materials that grounded the last call, so a
        # channel can show them without running retrieval a second time.
        self.last_grounding_sources: List[str] = []

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        preferred_model: Optional[str] = None,
        temperature: float = 0.7,
        stream: bool = False,
        max_retries_per_model: int = 2
    ) -> Tuple[int, str, float, str]:
        """
        Executes chat completion with cascading model fallback and exponential retry backoff.
        Returns: (status_code, content, latency_sec, model_used)
        """
        models_to_try = [preferred_model or DEFAULT_MODEL]
        for m in FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        import os
        if os.environ.get("ENV") == "test" and not self.api_key:
            return 200, "Тестовый ответ ассистента фотографа.", 0.05, models_to_try[0]

        # Decided before grounding: a JSON contract is the caller's, and the
        # evidence block must not be mistaken for one.
        wants_prose = not grounding.expects_json(messages)

        # Every engine and every guided action reaches the model through this
        # method, so grounding the prompt here is what makes the course corpus
        # reachable from all of them — not only from BrainService.process_chat.
        try:
            messages, self.last_grounding_sources = grounding.augment_messages(messages)
        except Exception:
            # Grounding is an addition, never a dependency: a broken index must
            # cost citations, not the answer.
            self.last_grounding_sources = []
            log.warning("Knowledge grounding failed; sending the prompt unchanged.", exc_info=True)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        last_err = ""
        total_dt = 0.0

        for m in models_to_try:
            payload = {
                "model": m,
                "messages": messages,
                "temperature": temperature,
                "stream": stream
            }
            data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

            for attempt in range(max_retries_per_model + 1):
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                t0 = time.time()
                try:
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        dt = time.time() - t0
                        total_dt += dt
                        raw = resp.read().decode("utf-8")
                        parsed = json.loads(raw)
                        content = parsed["choices"][0]["message"]["content"]
                        return 200, self._cite(content, wants_prose), total_dt, m
                except urllib.error.HTTPError as e:
                    dt = time.time() - t0
                    total_dt += dt
                    err_body = e.read().decode("utf-8")
                    last_err = f"HTTP {e.code} on {m}: {err_body[:150]}"
                    if e.code == 429:
                        # Rate limit: Google free tier allows 15 RPM. Sleep 5-10s to clear the minute window.
                        if attempt < max_retries_per_model:
                            time.sleep(5.0 * (attempt + 1))
                            continue
                        else:
                            break
                    elif e.code in (500, 502, 503, 504):
                        if attempt < max_retries_per_model:
                            time.sleep(1.5 * (attempt + 1))
                            continue
                        else:
                            break
                    else:
                        break
                except Exception as e:
                    dt = time.time() - t0
                    total_dt += dt
                    last_err = f"Error on {m}: {str(e)}"
                    time.sleep(1.0)
                    break

        return 500, f"All models exhausted. Last error: {last_err}", total_dt, models_to_try[0]

    def _cite(self, content: str, wants_prose: bool) -> str:
        """Attach the sources that were actually retrieved for this answer.

        Asking the model to cite produced three failure modes: a forgotten
        line, a line listing material it never used, and an invented lesson
        title. The line is therefore rendered from retrieval, and a line the
        model wrote itself is dropped. JSON contracts are left untouched.
        """
        if not wants_prose or not grounding.sources_in_answer():
            return content
        try:
            return grounding.append_sources(content, self.last_grounding_sources)
        except Exception:
            log.warning("Could not render the source line; returning the answer as is.", exc_info=True)
            return content
