from __future__ import annotations

import hashlib
import json
from typing import Any


def build_completion_proof(requirements: dict[str,Any], confidence: dict[str,Any], ledger: dict[str,Any], database: dict[str,Any], history_preserved: bool = True, acceptance: bool = True, unresolved_critical: int = 0) -> dict[str,Any]:
    checks={
        'requirements':bool((requirements or {}).get('ok',False)),
        'confidence':bool((confidence or {}).get('ready',False)),
        'ledger':bool((ledger or {}).get('ok',False)),
        'database':str((database or {}).get('quick_check') or '').lower()=='ok',
        'history':bool(history_preserved),
        'acceptance':bool(acceptance),
        'critical_issues_clear':int(unresolved_critical or 0)==0,
    }
    failed=[k for k,v in checks.items() if not v]; canonical={'checks':checks,'confidence_score':float((confidence or {}).get('score') or 0.0),'ledger_head':str((ledger or {}).get('head_hash') or '')}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest().upper()
    return {'ok':not failed,'ready':not failed,'checks':checks,'failed':failed,'proof_sha256':digest,'evidence_required':True}
