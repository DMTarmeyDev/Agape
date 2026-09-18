from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL


class ProviderError(RuntimeError):
    pass


@dataclass
class ProviderReply:
    provider: str
    model: str
    content: str
    duration_seconds: float
    raw: dict[str, Any]


def _json_request(url: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"OLLAMA_HTTP_{exc.code}: {detail[:500]}") from None
    except Exception as exc:
        raise ProviderError(f"OLLAMA_TRANSPORT_ERROR: {exc}") from None
    try:
        obj = json.loads(payload)
    except Exception as exc:
        raise ProviderError(f"OLLAMA_INVALID_JSON: {exc}") from None
    if not isinstance(obj, dict):
        raise ProviderError("OLLAMA_RESPONSE_NOT_OBJECT")
    return obj


def ollama_models(timeout: int = 8) -> list[dict[str, Any]]:
    req = urllib.request.Request(OLLAMA_URL + "/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        raise ProviderError(f"OLLAMA_TAGS_FAILED: {exc}") from None
    models = obj.get("models", []) if isinstance(obj, dict) else []
    return [m for m in models if isinstance(m, dict)]


def ollama_chat(model: str, messages: list[dict[str, str]], timeout: int | None = None, num_predict: int = 512, json_only: bool = False) -> ProviderReply:
    model = (model or "").strip()
    if not model:
        raise ProviderError("OLLAMA_MODEL_REQUIRED")
    body = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {"temperature": 0, "num_predict": int(num_predict)},
    }
    if json_only:
        body["format"] = "json"
    started = time.monotonic()
    obj = _json_request(OLLAMA_URL + "/api/chat", body, timeout or OLLAMA_TIMEOUT_SECONDS)
    duration = time.monotonic() - started
    message = obj.get("message") or {}
    content = str(message.get("content") or "")
    return ProviderReply("ollama", model, content, duration, obj)
