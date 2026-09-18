from __future__ import annotations
from typing import Any

def plan_startup_recovery(state: dict[str,Any]) -> dict[str,Any]:
    s=dict(state or {}); actions=[]
    for key in ('incomplete_requests','incomplete_loops','interrupted_sessions','paused_supervisors'):
        n=max(0,int(s.get(key) or 0))
        if n: actions.append({'source':key,'count':n,'action':'mark_interrupted_then_revalidate'})
    deferred=max(0,int(s.get('deferred_work') or 0))
    if deferred: actions.append({'source':'deferred_work','count':deferred,'action':'retry_when_provider_healthy'})
    integrity=bool(s.get('database_ok',True)) and bool(s.get('ledger_ok',True))
    return {'ok':integrity,'safe_to_start':integrity,'actions':actions,'action_count':len(actions),'block_reason':'' if integrity else 'integrity_gate_failed'}
