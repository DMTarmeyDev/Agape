from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .database import StudioDatabase
from .providers import ModelInfo, OpenRouterFreeProvider, score_model


class AIProvider(Protocol):
    provider_id: str
    tier: str
    def models(self) -> list[str]: ...
    def chat(self, model: str, messages: list[dict[str, str]]) -> str: ...


@dataclass
class FakeProvider:
    provider_id: str = 'fake'
    model_name: str = 'agape-test-model'
    tier: str = 'local'
    fail_chat: bool = False

    def models(self) -> list[str]:
        return [self.model_name]

    def model_catalog(self) -> list[ModelInfo]:
        return [ModelInfo(self.provider_id, self.model_name, self.model_name, self.tier, self.tier == 'free-online', 32768, ('tools',), 'fake')]

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        if self.fail_chat:
            raise RuntimeError('FAKE_PROVIDER_FORCED_FAILURE')
        last = messages[-1]['content'] if messages else ''
        return f'FAKE_RESPONSE[{model}]: {last}'


@dataclass
class OllamaProvider:
    base_url: str = 'http://127.0.0.1:11434'
    provider_id: str = 'ollama'
    tier: str = 'local'
    timeout: float = 10
    chat_timeout: float = 120

    def _json(self, path: str, body: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        url = self.base_url.rstrip('/') + path
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout if timeout is None else timeout) as res:
                return json.loads(res.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'OLLAMA_UNAVAILABLE: {exc}') from exc

    def models(self) -> list[str]:
        payload = self._json('/api/tags')
        return [str(x.get('name')) for x in payload.get('models', []) if x.get('name')]

    def model_catalog(self) -> list[ModelInfo]:
        return [ModelInfo(self.provider_id, x, x, self.tier, True, 0, (), 'ollama-local') for x in self.models()]

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = self._json('/api/chat', {'model': model, 'messages': messages, 'stream': False}, timeout=self.chat_timeout)
        return str((payload.get('message') or {}).get('content') or '')


class AIRouter:
    def __init__(self, db: StudioDatabase, providers: list[AIProvider] | None = None):
        self.db = db
        self.providers = list(providers or [OllamaProvider(), OpenRouterFreeProvider()])

    def _catalog(self, provider: AIProvider) -> list[ModelInfo]:
        fn = getattr(provider, 'model_catalog', None)
        if callable(fn):
            return list(fn())
        tier = str(getattr(provider, 'tier', 'local'))
        return [ModelInfo(provider.provider_id, model, model, tier, tier != 'paid') for model in provider.models()]

    def provider(self, provider_id: str) -> AIProvider | None:
        return next((p for p in self.providers if p.provider_id == provider_id), None)

    def status(self) -> dict[str, Any]:
        available: list[dict[str, Any]] = []
        for provider in self.providers:
            started = time.perf_counter()
            try:
                catalog = self._catalog(provider)
                available.append({
                    'provider': provider.provider_id,
                    'tier': str(getattr(provider, 'tier', 'local')),
                    'ok': True,
                    'models': [x.model for x in catalog],
                    'model_count': len(catalog),
                    'credential_configured': bool(getattr(provider, 'credential_configured', True)),
                    'latency_ms': int((time.perf_counter() - started) * 1000),
                })
            except Exception as exc:
                available.append({
                    'provider': provider.provider_id,
                    'tier': str(getattr(provider, 'tier', 'local')),
                    'ok': False,
                    'models': [],
                    'model_count': 0,
                    'credential_configured': bool(getattr(provider, 'credential_configured', True)),
                    'error': str(exc),
                })
        return {'ok': any(x['ok'] and x['models'] for x in available), 'providers': available}

    def free_models(self, task: str = 'general') -> list[dict[str, Any]]:
        rows=[]
        for provider in self.providers:
            if str(getattr(provider, 'tier', 'local')) != 'free-online':
                continue
            try:
                for info in self._catalog(provider):
                    score, reasons = score_model(info, task)
                    rows.append({**info.public(), 'score': round(score, 3), 'reason': ', '.join(reasons)})
            except Exception:
                continue
        rows.sort(key=lambda x: (-float(x['score']), -int(x.get('context_length') or 0), x['model']))
        return rows

    def ranked(self, task: str = 'general', mode: str = 'auto') -> list[tuple[AIProvider, ModelInfo, float, list[str]]]:
        mode = str(mode or 'auto').lower()
        if mode not in {'auto', 'local', 'free'}:
            raise RuntimeError('INVALID_AI_MODE')
        ranked=[]
        for provider in self.providers:
            tier = str(getattr(provider, 'tier', 'local'))
            if mode == 'local' and tier != 'local':
                continue
            if mode == 'free' and tier != 'free-online':
                continue
            if tier not in {'local', 'free-online'}:
                continue
            try:
                catalog = self._catalog(provider)
            except Exception:
                continue
            for info in catalog:
                if tier == 'free-online' and not info.is_free:
                    continue
                score, reasons = score_model(info, task)
                ranked.append((provider, info, score, reasons))
        ranked.sort(key=lambda x: (-x[2], -x[1].context_length, x[1].model))
        return ranked

    def recommend(self, task: str = 'general', mode: str = 'auto') -> dict[str, Any]:
        ranked = self.ranked(task, mode)
        if not ranked:
            raise RuntimeError('NO_AI_MODEL_AVAILABLE')
        _, info, score, reasons = ranked[0]
        return {**info.public(), 'score': round(score, 3), 'reason': ', '.join(reasons), 'mode': mode}

    def choose(self, task: str = 'general', mode: str = 'auto') -> tuple[AIProvider, str]:
        ranked = self.ranked(task, mode)
        if not ranked:
            raise RuntimeError('NO_AI_MODEL_AVAILABLE')
        return ranked[0][0], ranked[0][1].model

    def chat(self, project_path: str | None, message: str, task: str = 'general', context: str = '', mode: str = 'auto') -> dict[str, Any]:
        messages=[]
        if context:
            messages.append({'role': 'system', 'content': 'Project context:\n' + context[:12000]})
        messages.append({'role': 'user', 'content': message})
        candidates = self.ranked(task, mode)
        if not candidates:
            raise RuntimeError('NO_AI_MODEL_AVAILABLE')
        errors=[]
        unavailable_providers=set()
        self.db.add_ai_history(project_path, 'user', message, None)
        for provider, info, score, reasons in candidates:
            if info.tier == 'free-online' and not bool(getattr(provider, 'credential_configured', True)):
                if provider.provider_id not in unavailable_providers:
                    detail='FREE_PROVIDER_CREDENTIAL_NOT_CONFIGURED'
                    self.db.record_connection_test(provider.provider_id, None, 'SETUP_REQUIRED', detail, None, 'routing')
                    errors.append({'provider': provider.provider_id, 'model': None, 'error': detail})
                    unavailable_providers.add(provider.provider_id)
                continue
            started = time.perf_counter()
            try:
                reply = provider.chat(info.model, messages)
                if not str(reply).strip():
                    raise RuntimeError('EMPTY_AI_RESPONSE')
                latency = int((time.perf_counter() - started) * 1000)
                self.db.record_connection_test(provider.provider_id, info.model, 'PASS', 'Generation succeeded', latency, 'generation')
                self.db.add_ai_history(project_path, 'assistant', reply, info.model)
                return {
                    'ok': True,
                    'provider': provider.provider_id,
                    'tier': info.tier,
                    'model': info.model,
                    'reply': reply,
                    'mode': mode,
                    'score': round(score, 3),
                    'reason': ', '.join(reasons),
                    'fallbacks_used': len(errors),
                    'failed_attempts': errors,
                }
            except Exception as exc:
                latency = int((time.perf_counter() - started) * 1000)
                detail = str(exc)[:500]
                self.db.record_connection_test(provider.provider_id, info.model, 'FAIL', detail, latency, 'generation')
                errors.append({'provider': provider.provider_id, 'model': info.model, 'error': detail})
                continue
        raise RuntimeError('ALL_ALLOWED_AI_MODELS_FAILED: ' + '; '.join(f"{x['provider']}/{x['model']}={x['error']}" for x in errors[:5]))
