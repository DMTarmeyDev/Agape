from __future__ import annotations

from typing import Any


def build_task_graph(tasks: list[dict[str, Any]], completed: list[Any] | None = None, failed: list[Any] | None = None) -> dict[str, Any]:
    items=list(tasks or [])
    if not items:
        return {'ok':False,'error':'TASK_GRAPH_TASKS_REQUIRED','order':[],'ready':[],'blocked':[]}
    nodes={}
    for raw in items:
        if not isinstance(raw,dict):
            raise ValueError('TASK_GRAPH_TASK_INVALID')
        ident=raw.get('id')
        if ident is None or str(ident).strip()=='':
            raise ValueError('TASK_GRAPH_ID_REQUIRED')
        key=str(ident)
        if key in nodes:
            raise ValueError('TASK_GRAPH_DUPLICATE_ID='+key)
        deps=[str(x) for x in list(raw.get('depends_on') or [])]
        nodes[key]={'id':ident,'title':str(raw.get('title') or raw.get('name') or key),'depends_on':deps}
    for key,node in nodes.items():
        missing=[d for d in node['depends_on'] if d not in nodes]
        if missing:
            raise ValueError('TASK_GRAPH_MISSING_DEPENDENCY='+key+':'+','.join(missing))
    indegree={k:0 for k in nodes}; children={k:[] for k in nodes}
    for key,node in nodes.items():
        for dep in node['depends_on']:
            indegree[key]+=1; children[dep].append(key)
    queue=sorted([k for k,v in indegree.items() if v==0])
    order=[]
    while queue:
        key=queue.pop(0); order.append(key)
        for child in sorted(children[key]):
            indegree[child]-=1
            if indegree[child]==0:
                queue.append(child); queue.sort()
    if len(order)!=len(nodes):
        raise ValueError('TASK_GRAPH_CYCLE_DETECTED')
    done={str(x) for x in (completed or [])}; bad={str(x) for x in (failed or [])}
    ready=[]; blocked=[]
    for key in order:
        if key in done or key in bad: continue
        deps=nodes[key]['depends_on']
        if any(d in bad for d in deps): blocked.append(nodes[key])
        elif all(d in done for d in deps): ready.append(nodes[key])
    return {'ok':True,'order':[nodes[k]['id'] for k in order],'ready':ready,'blocked':blocked,'total':len(nodes),'completed':sorted(done),'failed':sorted(bad)}
