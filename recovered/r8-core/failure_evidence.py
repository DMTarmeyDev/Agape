from __future__ import annotations

import hashlib
import json
import re
from typing import Any
import failure_triage

_SECRET_PATTERNS=[
    re.compile(r'(?i)(authorization\s*:\s*bearer\s+)[^\s]+'),
    re.compile(r'(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+'),
]


def _redact(text: Any, limit: int = 12000) -> str:
    value=str(text or '')
    for pattern in _SECRET_PATTERNS: value=pattern.sub(r'\1[REDACTED]',value)
    if len(value)>limit: value=value[-limit:]
    return value


def build_failure_evidence(stdout: Any = '', stderr: Any = '', error: Any = '', exit_code: int | None = None, failed_tests: list[Any] | None = None, changed_files: list[Any] | None = None) -> dict[str,Any]:
    out=_redact(stdout); err=_redact(stderr); exc=_redact(error)
    triage=failure_triage.triage_failure(out,err+'\n'+exc,exit_code)
    tests=[]
    for item in failed_tests or []:
        name=str(item.get('name') or item.get('test') or '') if isinstance(item,dict) else str(item)
        if name and name not in tests: tests.append(name[:300])
    files=[]
    for item in changed_files or []:
        name=str(item).replace('\\','/').lstrip('/')
        if name and name not in files: files.append(name[:500])
    canonical={'stdout':out,'stderr':err,'error':exc,'exit_code':exit_code,'failed_tests':tests,'changed_files':files,'triage':triage}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest().upper()
    return {'ok':True,**canonical,'evidence_sha256':digest,'redacted':True}
