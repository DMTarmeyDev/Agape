from __future__ import annotations

import hashlib
import json
from typing import Any


def _clean(value: Any, limit: int = 1200) -> str:
    text=' '.join(str(value or '').split()).strip()
    if len(text)>limit: raise ValueError('REQUIREMENT_TOO_LONG')
    return text


def _unique(values: list[Any] | None) -> list[str]:
    out=[]
    for raw in values or []:
        text=_clean(raw)
        if text and text not in out: out.append(text)
    return out


def build_requirements(goal: str, requirements: list[Any] | None = None, acceptance_criteria: list[Any] | None = None, constraints: list[Any] | None = None) -> dict[str,Any]:
    clean_goal=_clean(goal,5000)
    if not clean_goal: raise ValueError('REQUIREMENTS_GOAL_REQUIRED')
    req=_unique(requirements)
    if not req: req=[clean_goal]
    criteria=_unique(acceptance_criteria)
    if not criteria: criteria=['project tests pass','database integrity passes','workspace scope remains safe']
    cons=_unique(constraints)
    req_rows=[{'id':f'R{i+1}','text':x} for i,x in enumerate(req)]
    ac_rows=[{'id':f'AC{i+1}','text':x} for i,x in enumerate(criteria)]
    canonical={'goal':clean_goal,'requirements':req_rows,'acceptance_criteria':ac_rows,'constraints':cons}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest().upper()
    return {'ok':True,**canonical,'requirements_sha256':digest}
