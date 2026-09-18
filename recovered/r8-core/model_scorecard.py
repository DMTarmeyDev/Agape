from __future__ import annotations

import re
from typing import Any
import db


def _size(name: str) -> float:
    m=re.search(r'(\d+(?:\.\d+)?)b',str(name or '').lower())
    return float(m.group(1)) if m else 0.0


def build_scorecard(installed_models: list[Any], task_type: str = 'coding') -> dict[str, Any]:
    names=[]
    for x in installed_models or []:
        n=str(x.get('name') or '') if isinstance(x,dict) else str(x)
        if n and n not in names: names.append(n)
    stats={str(x['model']):x for x in db.model_outcome_stats(str(task_type or ''))}
    rows=[]
    for name in names:
        s=stats.get(name,{})
        total=int(s.get('total') or 0); wins=int(s.get('successes') or 0); rate=(wins/total) if total else 0.5
        avg=float(s.get('avg_duration_seconds') or 0.0)
        baseline=(20 if ('coder' in name.lower() or 'code' in name.lower()) else 0)+min(_size(name),14.0)*2.0
        observed=rate*50.0+min(total,10)*1.5-(min(avg,180.0)/30.0 if total else 0.0)
        score=round(baseline+observed,3)
        rows.append({'model':name,'score':score,'total':total,'successes':wins,'success_rate':round(rate,4),'avg_duration_seconds':round(avg,3)})
    rows.sort(key=lambda x:(-x['score'],x['model'].lower()))
    return {'ok':bool(rows),'task_type':str(task_type or ''),'models':rows,'recommended':rows[0]['model'] if rows else ''}
