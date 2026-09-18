from __future__ import annotations

from typing import Any


def _pass(value: Any) -> bool:
    if value is True: return True
    if isinstance(value,str): return value.strip().upper() in {'PASS','OK','TRUE','SUCCESS'} or value.strip().upper().endswith(' PASS')
    if isinstance(value,dict): return bool(value.get('ok')) and str(value.get('overall','PASS')).upper()!='FAIL'
    return False


def evaluate_acceptance(checks: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    values=dict(checks or {})
    names=list(required or values.keys())
    missing=[n for n in names if n not in values]
    failed=[n for n in names if n in values and not _pass(values[n])]
    passed=[n for n in names if n in values and _pass(values[n])]
    ok=not missing and not failed
    return {'ok':ok,'overall':'PASS' if ok else 'FAIL','passed':passed,'failed':failed,'missing':missing,'required':names,'passed_count':len(passed),'total':len(names)}
