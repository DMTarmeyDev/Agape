from __future__ import annotations

def normalize_max_steps(value) -> int:
    try: n=int(value)
    except Exception: n=4
    return max(1,min(n,8))

def decide_next(test_passed: bool, step: int, max_steps: int, consecutive_failures: int, changed: bool) -> dict:
    limit=normalize_max_steps(max_steps); step=max(0,int(step)); failures=max(0,int(consecutive_failures))
    if bool(test_passed): return {'ok':True,'action':'stop_pass','reason':'tests_passed','max_steps':limit}
    if step>=limit: return {'ok':True,'action':'stop_limit','reason':'step_limit_reached','max_steps':limit}
    if failures>=2: return {'ok':True,'action':'escalate','reason':'repeated_failures','max_steps':limit}
    if not bool(changed) and step>0: return {'ok':True,'action':'continue','reason':'no_change_retry','max_steps':limit}
    return {'ok':True,'action':'continue','reason':'within_budget','max_steps':limit}
