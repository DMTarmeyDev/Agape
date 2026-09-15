from __future__ import annotations

import hashlib
import json
from typing import Any


def _clean_list(values: list[Any] | None, limit: int = 30) -> list[str]:
    out=[]
    for raw in values or []:
        value=str(raw or '').strip()
        if value and value not in out: out.append(value[:500])
        if len(out)>=limit: break
    return out


def build_work_plan(goal: str, tasks: list[dict[str,Any]] | None = None, requirements: list[Any] | None = None, max_tasks: int = 12) -> dict[str,Any]:
    text=' '.join(str(goal or '').split()).strip()
    if not text: return {'ok':False,'reason':'goal_required','tasks':[]}
    limit=max(1,min(int(max_tasks or 12),30))
    rows=[]; seen=set()
    source=list(tasks or [])
    if not source:
        source=[
            {'id':'inspect','title':'Inspect current state','depends_on':[],'kind':'inspect'},
            {'id':'implement','title':'Implement the smallest safe change','depends_on':['inspect'],'kind':'edit'},
            {'id':'test','title':'Run targeted and project tests','depends_on':['implement'],'kind':'test'},
            {'id':'prove','title':'Build completion evidence','depends_on':['test'],'kind':'evidence'},
        ]
    for i,raw in enumerate(source[:limit]):
        item=dict(raw or {}); ident=str(item.get('id') or f'T{i+1}').strip()[:80]
        if not ident or ident in seen: ident=f'T{i+1}'
        seen.add(ident)
        deps=_clean_list(list(item.get('depends_on') or []),20)
        rows.append({'id':ident,'title':str(item.get('title') or item.get('goal') or ident).strip()[:300],'depends_on':deps,'kind':str(item.get('kind') or 'work').strip().lower()[:40],'status':str(item.get('status') or 'pending').strip().lower()})
    known={x['id'] for x in rows}
    for item in rows: item['depends_on']=[x for x in item['depends_on'] if x in known and x!=item['id']]
    canonical={'goal':text,'requirements':_clean_list(requirements,40),'tasks':rows}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest().upper()
    return {'ok':True,**canonical,'plan_sha256':digest,'task_count':len(rows)}
