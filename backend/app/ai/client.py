"""One small client for the language model.

Providers:
  n8n    – POST {op, payload} to the n8n AI Gateway webhook; n8n holds the OpenAI key (production demo)
  openai – call OpenAI directly with OPENAI_API_KEY (for anyone running the repo without n8n)
  fake   – deterministic answers for automated tests (no network)

Retries transient failures (timeouts, 429, 5xx) with exponential backoff. A daily call budget in
Redis stops runaway costs.
"""
import json
import random
import time
from datetime import date

import httpx

from ..config import get_settings


class AIUnavailable(Exception):
    """The model could not be reached after retries. The document fails and can be reprocessed later."""


class AIBudgetExceeded(AIUnavailable):
    pass


_fake_handler = None


def set_fake_handler(fn):
    """Tests install a function (op, payload) -> response dict."""
    global _fake_handler
    _fake_handler = fn


def _check_budget():
    s = get_settings()
    if s.ai_provider == "fake" or s.ai_daily_call_limit <= 0:
        return
    try:
        from redis import Redis
        r = Redis.from_url(s.redis_url, socket_timeout=2)
        key = f"docintel:ai_calls:{date.today().isoformat()}"
        n = r.incr(key)
        if n == 1:
            r.expire(key, 2 * 86400)
        if n > s.ai_daily_call_limit:
            raise AIBudgetExceeded("The daily AI budget for this demo is used up. Try again tomorrow.")
    except AIBudgetExceeded:
        raise
    except Exception:
        return  # budget counter is a safety net; never block processing because Redis blipped


def call(op: str, payload: dict) -> dict:
    s = get_settings()
    if s.ai_provider == "fake":
        if _fake_handler is None:
            raise AIUnavailable("No fake AI handler installed.")
        return _fake_handler(op, payload)
    _check_budget()
    if s.ai_provider == "n8n":
        url, headers, body = s.ai_gateway_url, {"X-DocIntel-Key": s.ai_gateway_key}, {"op": op, "payload": payload}
    elif s.ai_provider == "openai":
        url = f"https://api.openai.com/v1/{op}"
        headers = {"Authorization": f"Bearer {s.openai_api_key}"}
        body = {**payload, "store": False} if op == "responses" else payload
    else:
        raise AIUnavailable(f"Unknown AI provider {s.ai_provider!r}.")

    last = None
    for attempt in range(4):
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=s.ai_timeout_s)
            if r.status_code == 200:
                _remember("ok", op)
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in (408, 409, 429, 500, 502, 503, 504):
                break
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = f"{type(e).__name__}"
        time.sleep(min(20, 1.5 * 2 ** attempt) + random.random())
    _remember("error", f"{op}: {last}")
    raise AIUnavailable(f"The AI service did not answer ({last}).")


def _remember(kind: str, detail: str):
    try:
        from datetime import datetime, timezone
        from redis import Redis
        Redis.from_url(get_settings().redis_url, socket_timeout=1).set(
            f"docintel:ai_last_{kind}", f"{datetime.now(timezone.utc).isoformat()}|{detail[:200]}", ex=7 * 86400)
    except Exception:
        pass


def response_text(resp: dict) -> str:
    """Extract the text output from a Responses API result."""
    if "output_text" in resp and isinstance(resp["output_text"], str):
        return resp["output_text"]
    parts = []
    for item in resp.get("output", []) or []:
        for c in item.get("content", []) or []:
            if c.get("type") in ("output_text", "text") and c.get("text"):
                parts.append(c["text"])
    return "".join(parts)


def structured(model: str, system: str, user_content, schema: dict, name: str) -> dict:
    """Ask for JSON that must match `schema` (strict structured output) and parse it."""
    payload = {
        "model": model,
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        "text": {"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
    }
    if model.startswith(("gpt-4", "gpt-4.1")):
        payload["temperature"] = 0
    resp = call("responses", payload)
    text = response_text(resp)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise AIUnavailable("The AI returned an answer that was not valid JSON.")


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        chunk = [t[:8000] for t in texts[i:i + 64]]
        resp = call("embeddings", {"model": s.embedding_model, "input": chunk})
        out.extend(d["embedding"] for d in sorted(resp["data"], key=lambda d: d["index"]))
    return out
