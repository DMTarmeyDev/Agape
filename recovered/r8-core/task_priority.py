from __future__ import annotations

def prioritize_tasks(tasks):
    sev={'critical':0,'high':1,'medium':2,'low':3}
    copied=[dict(x) for x in (tasks or [])]
    ordered=sorted(copied,key=lambda x:(sev.get(str(x.get('severity') or '').lower(),4),bool(x.get('blocked')),int(x.get('dependency_count') or 0),str(x.get('id') or ''),str(x.get('title') or '')))
    for i,x in enumerate(ordered,1): x['priority_rank']=i
    return {'ok':True,'tasks':ordered}
