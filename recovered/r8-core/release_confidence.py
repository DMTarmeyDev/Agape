from __future__ import annotations

from typing import Any

REQUIRED=('system','database','history','requirements','regressions','ledger','templates')


def score_release_confidence(signals: dict[str,Any], required: list[str] | None = None) -> dict[str,Any]:
    sig=dict(signals or {}); req=list(required or REQUIRED)
    def passed(v: Any) -> bool:
        if isinstance(v,dict): return bool(v.get('ok') or v.get('passed') or str(v.get('overall') or '').upper()=='PASS')
        if isinstance(v,str): return v.upper().startswith('PASS') or v.upper() in {'OK','TRUE'}
        return bool(v)
    results={name:passed(sig.get(name)) for name in req}
    missing=[x for x in req if x not in sig]
    failed=[x for x,v in results.items() if not v and x not in missing]
    passed_count=sum(1 for x in req if results.get(x))
    score=round(100.0*passed_count/max(1,len(req)),1)
    ready=not missing and not failed and score==100.0
    return {'ok':ready,'release_ready':ready,'confidence':score,'required':req,'results':results,'missing':missing,'failed':failed}
