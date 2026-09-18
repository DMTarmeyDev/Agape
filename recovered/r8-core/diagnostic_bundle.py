from __future__ import annotations
import hashlib,json,re
from typing import Any

_PATTERNS=[re.compile(r'(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,;]+'),re.compile(r'(?i)bearer\s+[A-Za-z0-9._~+/-]{8,}')]
def _redact(value: Any) -> Any:
    if isinstance(value,dict): return {k:('[REDACTED]' if any(x in str(k).lower() for x in ('key','token','password','secret','authorization')) else _redact(v)) for k,v in value.items()}
    if isinstance(value,list): return [_redact(x) for x in value]
    if isinstance(value,str):
        s=value
        for pat in _PATTERNS: s=pat.sub('[REDACTED]',s)
        return s[:20000]
    return value

def build_bundle(runtime: dict[str,Any], database: dict[str,Any], failures: list[Any] | None=None, events: list[Any] | None=None) -> dict[str,Any]:
    payload=_redact({'runtime':runtime,'database':database,'failures':failures or [],'events':events or []}); raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False); digest=hashlib.sha256(raw.encode()).hexdigest().upper()
    return {'ok':True,'sanitized':True,'secret_values_included':False,'payload':payload,'bundle_sha256':digest}
