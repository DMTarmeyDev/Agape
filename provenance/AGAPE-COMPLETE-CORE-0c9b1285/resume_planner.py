from __future__ import annotations

from typing import Any


def decide_resume(session: dict[str, Any], scope_status: dict[str, Any] | None = None, ledger_ok: bool = True) -> dict[str, Any]:
    if not isinstance(session,dict) or not session.get('session_id'):
        raise ValueError('RESUME_SESSION_REQUIRED')
    status=str(session.get('status') or '').lower()
    if not ledger_ok:
        return {'ok':True,'action':'review','reason':'ledger_integrity_failed'}
    if scope_status and not bool(scope_status.get('safe',True)):
        return {'ok':True,'action':'replan','reason':'unexpected_workspace_drift','unexpected_paths':list(scope_status.get('unexpected_paths') or [])}
    if status=='completed': return {'ok':True,'action':'done','reason':'session_completed'}
    if status in {'rolled_back'}: return {'ok':True,'action':'stop','reason':'session_rolled_back'}
    attempt=int(session.get('attempt') or 0); max_steps=int(session.get('max_steps') or 4)
    if status=='failed' and attempt>=max_steps: return {'ok':True,'action':'rollback','reason':'attempt_budget_exhausted'}
    if status=='failed': return {'ok':True,'action':'repair','reason':'failed_with_budget_remaining'}
    if status in {'prepared','running','paused','repairing'}: return {'ok':True,'action':'resume','reason':'safe_resume'}
    return {'ok':True,'action':'review','reason':'unknown_session_state'}
