from __future__ import annotations

def choose_escalation(model_names, failures=0, complexity='low'):
    names=[str(x.get('name') or '') if isinstance(x,dict) else str(x) for x in (model_names or [])]
    hi='qwen2.5-coder:7b'; lo='qwen2.5-coder:1.5b-instruct'
    high=int(failures or 0)>=2 or str(complexity or '').lower() in {'high','complex','hard','critical'}
    wanted=hi if high else lo
    if wanted not in names: wanted=(hi if hi in names else (lo if lo in names else (names[0] if names else '')))
    return {'ok':bool(wanted),'model':wanted,'level':'high' if wanted==hi else 'fast','reason':'failure_or_complexity_escalation' if high else 'light_task'}
