from __future__ import annotations

import re
from typing import Any

_MAX_GOAL = 4000


def normalize_goal(goal: str, constraints: list[str] | None = None) -> dict[str, Any]:
    raw = str(goal or '').strip()
    if not raw:
        raise ValueError('GOAL_REQUIRED')
    if len(raw) > _MAX_GOAL:
        raise ValueError('GOAL_TOO_LONG')
    clean = re.sub(r'\s+', ' ', raw).strip()
    items=[]
    for item in list(constraints or []):
        value=re.sub(r'\s+', ' ', str(item or '')).strip()
        if value and value not in items:
            items.append(value[:500])
    lowered=clean.lower()
    task_type='coding' if any(x in lowered for x in ('code','fix','build','implement','test','api','bug','app','project')) else 'general'
    complexity='high' if len(clean) > 500 or any(x in lowered for x in ('architecture','refactor','migration','security','database','multi-step','whole system')) else 'normal'
    return {'ok':True,'goal':clean,'constraints':items,'task_type':task_type,'complexity':complexity,'goal_chars':len(clean)}
