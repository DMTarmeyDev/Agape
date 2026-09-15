from __future__ import annotations

from typing import Any

_DEFAULT_CRITICAL=('baseline','database','history','tests','ledger')


def track_confidence(signals: dict[str,Any], critical: list[str] | None = None, threshold: float = 0.95) -> dict[str,Any]:
    sig=dict(signals or {}); keys=list(sig.keys())
    if not keys: return {'ok':False,'ready':False,'score':0.0,'gaps':['signals_missing'],'signals':{}}
    norm={}
    for key,value in sig.items():
        if isinstance(value,bool): score=1.0 if value else 0.0
        else:
            try: score=max(0.0,min(float(value),1.0))
            except Exception: score=0.0
        norm[str(key)]=round(score,4)
    score=sum(norm.values())/len(norm)
    req=[str(x) for x in (critical or _DEFAULT_CRITICAL) if str(x) in norm]
    gaps=[x for x in req if norm[x]<1.0]
    ready=not gaps and score>=max(0.0,min(float(threshold),1.0))
    return {'ok':ready,'ready':ready,'score':round(score,4),'threshold':round(float(threshold),4),'critical':req,'gaps':gaps,'signals':norm}
