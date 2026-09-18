from __future__ import annotations

from typing import Any


def decide_repair(test_passed: bool, attempt: int, max_attempts: int = 3, failures: list[str] | None = None, changed: bool = True) -> dict[str, Any]:
    a=max(1,int(attempt or 1)); m=max(1,min(int(max_attempts or 3),5)); items=[str(x) for x in list(failures or []) if str(x).strip()]
    if test_passed: return {'ok':True,'action':'checkpoint','reason':'tests_passed','attempt':a,'max_attempts':m}
    if not changed: return {'ok':True,'action':'stop_no_progress','reason':'no_change','attempt':a,'max_attempts':m}
    if a>=m: return {'ok':True,'action':'rollback','reason':'attempt_limit','attempt':a,'max_attempts':m}
    if a>=2 or len(items)>=2: return {'ok':True,'action':'escalate','reason':'repeated_failure','attempt':a,'max_attempts':m}
    return {'ok':True,'action':'repair','reason':'first_failure','attempt':a,'max_attempts':m}
