from __future__ import annotations
from typing import Any

def evaluate_request_budget(consumed: dict[str,Any], limits: dict[str,Any] | None=None) -> dict[str,Any]:
    c=dict(consumed or {}); l={'requests':20,'tokens':50000,'seconds':900.0,'cost_usd':5.0}; l.update(dict(limits or {})); used={'requests':int(c.get('requests') or 0),'tokens':int(c.get('tokens') or 0),'seconds':float(c.get('seconds') or 0),'cost_usd':float(c.get('cost_usd') or 0)}
    exceeded=[]
    for k in l:
        if float(used.get(k,0))>float(l[k]): exceeded.append(k)
    return {'ok':not exceeded,'allowed':not exceeded,'consumed':used,'limits':l,'exceeded':exceeded,'action':'continue' if not exceeded else 'stop'}
