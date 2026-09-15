from __future__ import annotations

from typing import Any

DEFAULTS={'max_steps':8,'max_attempts':3,'max_model_switches':2,'max_changed_files':8,'max_wall_seconds':1800}


def evaluate_execution_budget(consumed: dict[str,Any] | None = None, limits: dict[str,Any] | None = None) -> dict[str,Any]:
    lim=dict(DEFAULTS); lim.update({k:int(v) for k,v in dict(limits or {}).items() if k in DEFAULTS})
    used={k:int(dict(consumed or {}).get(k,0) or 0) for k in DEFAULTS}
    reasons=[]; remaining={}
    for key,maximum in lim.items():
        maximum=max(1,int(maximum)); value=max(0,int(used.get(key,0))); lim[key]=maximum; used[key]=value; remaining[key]=max(0,maximum-value)
        if value>maximum: reasons.append(key.upper()+'_EXCEEDED')
    return {'ok':not reasons,'allowed':not reasons,'limits':lim,'consumed':used,'remaining':remaining,'reasons':reasons}
