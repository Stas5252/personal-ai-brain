"""
LLM Provider Integration with Multi-Model Fallback and Upstream Quota Protection.
"""
import time
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Tuple, Optional
from src.brain.config import (
    UPSTREAM_LLM_BASE_URL, GEMINI_API_KEY, DEFAULT_MODEL, FALLBACK_MODELS
)

class LLMProvider:
    def __init__(self):
        self.base_url = UPSTREAM_LLM_BASE_URL.rstrip("/")
        self.api_key = GEMINI_API_KEY

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
                        return 200, content, total_dt, m
                except urllib.error.HTTPError as e:
                    dt = time.time() - t0
                    total_dt += dt
                    err_body = e.read().decode("utf-8")
                    last_err = f"HTTP {e.code} on {m}: {err_body[:150]}"
                    if e.code == 429:
                        # Exponential backoff on rate limit
                        sleep_time = 2.0 * (attempt + 1)
                        time.sleep(sleep_time)
                        continue
                    else:
                        break
                except Exception as e:
                    dt = time.time() - t0
                    total_dt += dt
                    last_err = f"Error on {m}: {str(e)}"
                    time.sleep(1.0)
                    break

        return 500, f"All models exhausted. Last error: {last_err}", total_dt, models_to_try[0]
