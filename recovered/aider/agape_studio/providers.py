from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model: str
    name: str
    tier: str
    is_free: bool
    context_length: int = 0
    supported_parameters: tuple[str, ...] = ()
    source: str = 'provider'

    def public(self) -> dict[str, Any]:
        return {
            'provider': self.provider,
            'model': self.model,
            'name': self.name,
            'tier': self.tier,
            'is_free': self.is_free,
            'context_length': self.context_length,
            'supported_parameters': list(self.supported_parameters),
            'source': self.source,
        }


def _decimal_zero(value: Any, *, allow_empty: bool = False) -> bool:
    if value is None or str(value).strip() == '':
        return allow_empty
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _text_output(row: dict[str, Any]) -> bool:
    architecture = row.get('architecture') or {}
    outputs = architecture.get('output_modalities')
    if not outputs:
        return True
    return 'text' in {str(x).lower() for x in outputs}


def is_zero_cost_text_model(row: dict[str, Any]) -> bool:
    pricing = row.get('pricing') or {}
    return (
        bool(row.get('id'))
        and _text_output(row)
        and _decimal_zero(pricing.get('prompt'))
        and _decimal_zero(pricing.get('completion'))
        and _decimal_zero(pricing.get('request'), allow_empty=True)
    )


def score_model(info: ModelInfo, task: str) -> tuple[float, list[str]]:
    task_l = str(task or '').lower()
    model_l = (info.model + ' ' + info.name).lower()
    supported = {x.lower() for x in info.supported_parameters}
    coding = any(x in task_l for x in ('code', 'coding', 'python', 'javascript', 'typescript', 'repair', 'refactor', 'test', 'bug', 'debug'))
    score = 0.0
    reasons: list[str] = []

    if info.tier == 'local':
        score += 100.0
        reasons.append('local-first')
        if coding and any(x in model_l for x in ('coder', 'code', 'qwen')):
            score += 35.0
            reasons.append('coding-oriented-name')
        if coding and '7b' in model_l:
            score += 18.0
            reasons.append('larger-local-coding-model')
        if not coding and any(x in model_l for x in ('1.5b', '3b', 'mini', 'small')):
            score += 16.0
            reasons.append('fast-local-model')
    else:
        # Online free models are deliberately below healthy local models in Auto mode.
        # In Free mode this base does not matter because only free-online candidates remain.
        score += 20.0
        reasons.append('zero-cost-online')
        if coding and any(x in model_l for x in ('coder', 'code', 'program', 'dev')):
            score += 32.0
            reasons.append('coding-oriented-name')
        if any(x in model_l for x in ('reason', 'nemotron', 'qwen', 'deepseek', 'mistral')):
            score += 8.0
            reasons.append('reasoning-family-signal')
        if 'tools' in supported:
            score += 8.0
            reasons.append('tool-support')
        if 'structured_outputs' in supported or 'response_format' in supported:
            score += 4.0
            reasons.append('structured-output-support')
        if info.context_length > 0:
            score += min(18.0, max(0.0, math.log2(max(1, info.context_length / 4096))))
            reasons.append('context-capacity')

    return score, reasons


@dataclass
class OpenRouterFreeProvider:
    """OpenRouter adapter that will only expose zero-cost text models.

    The catalogue can normally be read without a key. Generation requires an
    OPENROUTER_API_KEY (or an explicitly supplied key). Paid models are never
    returned by model_catalog(), so AIRouter cannot silently route to them.
    """

    base_url: str = 'https://openrouter.ai/api/v1'
    api_key: str | None = None
    provider_id: str = 'openrouter-free'
    tier: str = 'free-online'
    timeout: int = 20

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get('OPENROUTER_API_KEY') or None
        self._catalog_cache: tuple[float, list[ModelInfo]] | None = None

    @property
    def credential_configured(self) -> bool:
        return bool(self.api_key)

    def _json(self, path: str, body: dict[str, Any] | None = None, *, auth: bool = False) -> dict[str, Any]:
        url = self.base_url.rstrip('/') + path
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Agape-AI-Studio/0.2',
            'X-Title': 'Agape AI Studio',
        }
        if auth:
            if not self.api_key:
                raise RuntimeError('OPENROUTER_API_KEY_NOT_CONFIGURED')
            headers['Authorization'] = 'Bearer ' + self.api_key
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')[:500]
            raise RuntimeError(f'OPENROUTER_HTTP_{exc.code}: {detail}') from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'OPENROUTER_UNAVAILABLE: {exc}') from exc

    def model_catalog(self, *, refresh: bool = False) -> list[ModelInfo]:
        now = time.time()
        if not refresh and self._catalog_cache and now - self._catalog_cache[0] < 300:
            return list(self._catalog_cache[1])
        payload = self._json('/models?sort=pricing-low-to-high', auth=bool(self.api_key))
        rows = payload.get('data') or []
        models: list[ModelInfo] = []
        for row in rows:
            if not isinstance(row, dict) or not is_zero_cost_text_model(row):
                continue
            model_id = str(row.get('id'))
            supported = tuple(str(x) for x in (row.get('supported_parameters') or []))
            try:
                context = int(row.get('context_length') or 0)
            except (TypeError, ValueError):
                context = 0
            models.append(ModelInfo(
                provider=self.provider_id,
                model=model_id,
                name=str(row.get('name') or model_id),
                tier=self.tier,
                is_free=True,
                context_length=context,
                supported_parameters=supported,
                source='openrouter-catalog-zero-price',
            ))
        models.sort(key=lambda x: x.model)
        self._catalog_cache = (now, models)
        return list(models)

    def models(self) -> list[str]:
        return [x.model for x in self.model_catalog()]

    def recommend(self, task: str) -> dict[str, Any]:
        ranked=[]
        for info in self.model_catalog():
            score, reasons = score_model(info, task)
            ranked.append((score, info, reasons))
        if not ranked:
            raise RuntimeError('NO_FREE_ONLINE_MODEL_AVAILABLE')
        ranked.sort(key=lambda x: (-x[0], -x[1].context_length, x[1].model))
        score, info, reasons = ranked[0]
        return {**info.public(), 'score': round(score, 3), 'reason': ', '.join(reasons)}

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        allowed = {x.model for x in self.model_catalog()}
        if model not in allowed:
            raise RuntimeError('PAID_OR_UNKNOWN_MODEL_BLOCKED')
        payload = self._json('/chat/completions', {
            'model': model,
            'messages': messages,
            'stream': False,
        }, auth=True)
        choices = payload.get('choices') or []
        if not choices:
            raise RuntimeError('OPENROUTER_EMPTY_CHOICES')
        content = ((choices[0] or {}).get('message') or {}).get('content')
        if isinstance(content, list):
            parts=[]
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    parts.append(str(item.get('text') or ''))
            content = ''.join(parts)
        return str(content or '')
