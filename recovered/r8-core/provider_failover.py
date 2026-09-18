from __future__ import annotations
from typing import Any

def choose_provider(candidates: list[dict[str,Any]], task: str='', offline_first: bool=True, require_online: bool=False) -> dict[str,Any]:
    rows=[]
    for raw in candidates or []:
        x=dict(raw or {}); health=str(x.get('health') or x.get('status') or 'unknown').lower(); ident=str(x.get('provider') or x.get('id') or '').lower(); online=bool(x.get('online')); enabled=bool(x.get('enabled',True)); score=float(x.get('score',1 if health in {'pass','healthy','ok'} else 0.5 if health=='unknown' else 0))
        if not ident or not enabled or health in {'fail','failed','down','disabled'}: continue
        if require_online and not online: continue
        score += 0.2 if offline_first and not online else 0
        rows.append((score,ident,online,x))
    rows.sort(key=lambda t:(-t[0],t[1]))
    if not rows: return {'ok':False,'reason':'no_healthy_provider','provider':''}
    score,ident,online,item=rows[0]
    return {'ok':True,'provider':ident,'online':online,'score':round(score,4),'reason':'health_capability_and_offline_priority','task':str(task or '')[:300]}
