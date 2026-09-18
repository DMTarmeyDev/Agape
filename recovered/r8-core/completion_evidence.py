from __future__ import annotations

import hashlib
import json
from typing import Any


def evaluate_completion(requirements: dict[str,Any], evidence: dict[str,Any], ledger: dict[str,Any] | None = None) -> dict[str,Any]:
    req=dict(requirements or {}); ev=dict(evidence or {})
    criteria=list(req.get('acceptance_criteria') or [])
    if not criteria: raise ValueError('ACCEPTANCE_CRITERIA_REQUIRED')
    rows=[]; missing=[]
    by_id=dict(ev.get('criteria') or {})
    for item in criteria:
        ident=str(item.get('id') or '')
        value=by_id.get(ident)
        passed=bool(value is True or str(value).upper()=='PASS' or (isinstance(value,dict) and bool(value.get('ok') or value.get('passed'))))
        rows.append({'id':ident,'text':str(item.get('text') or ''),'passed':passed,'evidence':value})
        if not passed: missing.append(ident)
    ledger_ok=True if ledger is None else bool(ledger.get('ok'))
    if not ledger_ok: missing.append('LEDGER')
    complete=not missing
    canonical={'requirements_sha256':str(req.get('requirements_sha256') or ''),'criteria':rows,'ledger_ok':ledger_ok}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest().upper()
    return {'ok':complete,'complete':complete,'criteria':rows,'missing':missing,'ledger_ok':ledger_ok,'evidence_sha256':digest}
