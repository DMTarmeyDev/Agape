from __future__ import annotations

from typing import Any


def checkpoint_decision(cycles_since: int = 0, accepted_changes: int = 0, minutes_since: float = 0.0, tests_passed: bool = False, final_acceptance: bool = False, max_cycles: int = 2, max_changes: int = 3, max_minutes: float = 30.0) -> dict[str,Any]:
    reasons=[]
    if final_acceptance: reasons.append('final_acceptance')
    if tests_passed and int(accepted_changes or 0)>=max(1,int(max_changes or 3)): reasons.append('change_threshold')
    if tests_passed and int(cycles_since or 0)>=max(1,int(max_cycles or 2)): reasons.append('cycle_threshold')
    if tests_passed and float(minutes_since or 0)>=max(1.0,float(max_minutes or 30.0)): reasons.append('time_threshold')
    due=bool(reasons)
    return {'ok':True,'checkpoint_due':due,'action':'checkpoint' if due else 'continue','reasons':reasons or ['not_due'],'requires_passing_tests':True}
