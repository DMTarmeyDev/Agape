from __future__ import annotations

import time
from typing import Any

from .ai import AIRouter


class ConnectionService:
    def __init__(self, ai: AIRouter):
        self.ai = ai
        self.db = ai.db

    def test_provider(self, provider_id: str, task: str = 'general', generation: bool = False) -> dict[str, Any]:
        provider = self.ai.provider(provider_id)
        if provider is None:
            raise RuntimeError('UNKNOWN_PROVIDER')
        started = time.perf_counter()
        try:
            catalog = self.ai._catalog(provider)
            if not catalog:
                raise RuntimeError('NO_MODELS_AVAILABLE')
            latency = int((time.perf_counter() - started) * 1000)
            self.db.record_connection_test(provider_id, None, 'PASS', f'Catalogue returned {len(catalog)} allowed model(s)', latency, 'catalog')
            model_results=[]
            for info in catalog:
                status = 'PASS' if info.is_free or info.tier == 'local' else 'FAIL'
                detail = 'Eligible zero-cost model' if info.is_free else 'Non-free model blocked'
                self.db.record_connection_test(provider_id, info.model, status, detail, None, 'eligibility')
                model_results.append({'model': info.model, 'status': status, 'detail': detail})
            generation_result = None
            if generation:
                credential_ok = bool(getattr(provider, 'credential_configured', True))
                if not credential_ok:
                    generation_result = {'status': 'SETUP_REQUIRED', 'detail': 'Provider credential is not configured.'}
                    self.db.record_connection_test(provider_id, None, 'SETUP_REQUIRED', generation_result['detail'], None, 'generation-probe')
                else:
                    ranked=[]
                    from .providers import score_model
                    for info in catalog:
                        score, _ = score_model(info, task)
                        ranked.append((score, info))
                    ranked.sort(key=lambda x: (-x[0], -x[1].context_length, x[1].model))
                    selected = ranked[0][1]
                    rec = {'model': selected.model}
                    reply = provider.chat(selected.model, [{'role': 'user', 'content': 'Reply with PASS'}])
                    if not str(reply).strip():
                        raise RuntimeError('GENERATION_PROBE_EMPTY_RESPONSE')
                    generation_result = {'status': 'PASS', 'model': rec['model'], 'response_bytes': len(reply.encode('utf-8'))}
                    self.db.record_connection_test(provider_id, rec['model'], 'PASS', 'Generation probe succeeded', None, 'generation-probe')
            return {
                'ok': True,
                'provider': provider_id,
                'tier': str(getattr(provider, 'tier', 'local')),
                'models': len(catalog),
                'model_results': model_results,
                'generation': generation_result,
            }
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self.db.record_connection_test(provider_id, None, 'FAIL', str(exc), latency, 'provider-test')
            return {'ok': False, 'provider': provider_id, 'error': str(exc)}

    def test_all(self, generation: bool = False) -> dict[str, Any]:
        results=[self.test_provider(p.provider_id, generation=generation) for p in self.ai.providers]
        return {'ok': any(x['ok'] for x in results), 'connections': results}

    def history(self, limit: int = 100) -> dict[str, Any]:
        return {'ok': True, 'tests': self.db.connection_test_history(limit)}
