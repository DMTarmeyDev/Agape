from __future__ import annotations

from typing import Any
import task_graph


def plan_next_tasks(tasks: list[dict[str,Any]], states: dict[str,Any] | None = None, max_parallel: int = 1) -> dict[str,Any]:
    state={str(k):str(v).lower() for k,v in dict(states or {}).items()}
    completed=[k for k,v in state.items() if v in {'pass','passed','complete','completed','done'}]
    failed=[k for k,v in state.items() if v in {'fail','failed','blocked','cancelled'}]
    graph=task_graph.build_task_graph(tasks,completed,failed)
    ready=list(graph.get('ready') or [])
    slots=max(1,min(int(max_parallel or 1),4))
    selected=ready[:slots]
    action='execute' if selected else ('blocked' if graph.get('blocked') else 'complete')
    return {'ok':True,'action':action,'selected':selected,'ready':ready,'blocked':graph.get('blocked',[]),'order':graph.get('order',[]),'max_parallel':slots,'completed':completed,'failed':failed}
