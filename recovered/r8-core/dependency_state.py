from __future__ import annotations

from typing import Any


def evaluate_dependency_state(tasks: list[dict[str,Any]]) -> dict[str,Any]:
    rows=[]; ids=set()
    for i,raw in enumerate(tasks or []):
        item=dict(raw or {}); ident=str(item.get('id') or f'T{i+1}').strip()
        if not ident or ident in ids: return {'ok':False,'reason':'duplicate_or_empty_task_id','ready':[],'blocked':[]}
        ids.add(ident); rows.append({'id':ident,'depends_on':[str(x) for x in item.get('depends_on') or []],'status':str(item.get('status') or 'pending').lower()})
    missing=sorted({d for x in rows for d in x['depends_on'] if d not in ids})
    if missing: return {'ok':False,'reason':'missing_dependencies','missing':missing,'ready':[],'blocked':[]}
    graph={x['id']:x['depends_on'] for x in rows}; visiting=set(); visited=set()
    def visit(n):
        if n in visiting: return False
        if n in visited: return True
        visiting.add(n)
        for d in graph.get(n,[]):
            if not visit(d): return False
        visiting.remove(n); visited.add(n); return True
    if not all(visit(n) for n in graph): return {'ok':False,'reason':'dependency_cycle','ready':[],'blocked':[]}
    done={x['id'] for x in rows if x['status'] in {'pass','passed','completed','done'}}
    ready=[]; blocked=[]
    for x in rows:
        if x['id'] in done: continue
        unmet=[d for d in x['depends_on'] if d not in done]
        (blocked if unmet else ready).append({'id':x['id'],'unmet':unmet})
    return {'ok':True,'ready':ready,'blocked':blocked,'completed':sorted(done),'all_complete':len(done)==len(rows) and bool(rows),'task_count':len(rows)}
