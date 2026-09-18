from __future__ import annotations

from typing import Any


def build_work_plan(goal_spec: dict[str, Any], context_pack: dict[str, Any] | None = None, max_tasks: int = 6) -> dict[str, Any]:
    if not isinstance(goal_spec,dict) or not goal_spec.get('ok'): raise ValueError('GOAL_SPEC_REQUIRED')
    goal=str(goal_spec.get('goal') or '').strip()
    if not goal: raise ValueError('GOAL_REQUIRED')
    count=max(2,min(int(max_tasks or 6),8)); names=['inspect','implement','targeted_test','review','full_test','evidence','checkpoint','done'][:count]
    tasks=[]
    for i,name in enumerate(names,1):
        deps=[] if i==1 else [i-1]
        tasks.append({'id':i,'kind':name,'title':name.replace('_',' ').title(),'depends_on':deps,'status':'pending'})
    return {'ok':True,'goal':goal,'task_count':len(tasks),'tasks':tasks,'context_files':len(list((context_pack or {}).get('files') or []))}
