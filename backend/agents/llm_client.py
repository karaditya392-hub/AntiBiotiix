"""
NVIDIA NIM client for the agent layer (Spec §10A, §22A).

One place where this system talks to a hosted model, so there is one place to
audit. Endpoint, key, model id and timeout all come from backend.config, which
reads the single .env at the repository root.

THREE PROPERTIES THIS CLIENT MUST HAVE, and each is a safety property rather
than an engineering preference:

  1. It is OPTIONAL. With no API key configured, `available()` is False and every
     caller must have a deterministic path that still works. A clinical system
     that stops assessing prescriptions because a vendor endpoint is down is a
     worse system than one that never called the vendor.

  2. It returns JSON or it returns nothing. A model asked for a verdict may not
     answer in prose. An unparseable response is a failure, never a guess at what
     the model meant.

  3. It records what answered. The model id and endpoint are returned with every
     result, so an audit entry says which model produced a verdict rather than
     "the LLM". Model ids change under you; a logged verdict must still be
     attributable a year later.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend import config


@dataclass
class LLMResult:
    ok: bool
    data: Optional[Dict[str, Any]]
    model: str
    error: Optional[str] = None


def available() -> bool:
    """True when a key is configured. Callers branch on this, never on try/except."""
    return bool(config.NVIDIA_API_KEY)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    The first JSON object in a response.

    Models wrap JSON in prose or fences however they were feeling. Tolerating that
    is fine; guessing at a verdict when there is no JSON at all is not, so this
    returns None rather than an empty dict.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, depth = text.find("{"), 0
        if start == -1:
            return None
        for i in range(start, len(text)):
            depth += (text[i] == "{") - (text[i] == "}")
            if depth == 0:
                candidate = text[start:i + 1]
                break
    if candidate is None:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def complete_json(system_prompt: str, user_prompt: str, max_tokens: int = 700) -> LLMResult:
    """
    One chat completion, parsed as JSON, with capacity fallback.

    Temperature defaults to 0. A filtration verdict that changes between two runs
    on the same input is not auditable, and this layer's whole claim is that its
    decisions can be reviewed afterwards.

    On 429 or 503 the next configured model is tried. Those two codes only: a 400
    is a bad request and a 401 is a bad key, and retrying either against a second
    model turns a clear error into a confusing one. The result always carries the
    model that actually answered.
    """
    if not available():
        return LLMResult(False, None, config.AGENT_LLM_MODEL, "NVIDIA_API_KEY is not configured")

    last = None
    for model in [config.AGENT_LLM_MODEL, *config.AGENT_LLM_FALLBACK_MODELS]:
        last = _complete_one(model, system_prompt, user_prompt, max_tokens)

        # ONE RETRY WHEN THE ANSWER WAS NOT JSON, and only then.
        #
        # This endpoint does not support response_format={"type":"json_object"} --
        # it answers 503 to any request carrying it, on both models -- so JSON has
        # to be obtained by asking. A model that wrapped its object in prose or a
        # markdown fence has done the work and formatted it wrongly; re-asking once
        # with an explicit instruction recovers it, and costs one call only in the
        # case that would otherwise have been discarded entirely.
        #
        # Deliberately NOT retried for anything else: an HTTP error is a transport
        # problem the fallback model handles, and retrying a refusal would be
        # asking a model to change its mind.
        if not last.ok and (last.error or "") == "response contained no parseable JSON":
            last = _complete_one(
                model,
                system_prompt
                + "\n\nReturn ONLY the JSON object. No prose before or after it, "
                  "no markdown fences, no explanation.",
                user_prompt,
                max_tokens,
            )

        if last.ok or not (last.error or "").startswith(("HTTP 429", "HTTP 503")):
            return last
    return last


def _complete_one(model: str, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResult:
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx is a pinned dependency
        return LLMResult(False, None, model, "httpx is not installed")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.AGENT_LLM_TEMPERATURE,
        "max_tokens": max_tokens,
    }

    try:
        response = httpx.post(
            f"{config.NVIDIA_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
                "Accept": "application/json",
            },
            json=payload,
            timeout=config.AGENT_LLM_TIMEOUT_S,
        )
    except Exception as exc:  # network, DNS, TLS, timeout
        return LLMResult(False, None, model, f"request failed: {type(exc).__name__}")

    if response.status_code != 200:
        return LLMResult(False, None, model, f"HTTP {response.status_code}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError, TypeError):
        return LLMResult(False, None, model, "unexpected response shape")

    parsed = _extract_json(content)
    if parsed is None:
        return LLMResult(False, None, model, "response contained no parseable JSON")
    return LLMResult(True, parsed, model)
