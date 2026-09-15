from __future__ import annotations

from typing import Any


def decide_interruption_recovery(session: dict[str,Any] | None, ledger: dict[str,Any] | None = None, scope: dict[str,Any] | None = None, current_snapshot_sha256: str = '', checkpoint: dict[str,Any] | None = None) -> dict[str,Any]:
    s=dict(session or {}); led=dict(ledger or {'ok':True}); sc=dict(scope or {'ok':True})
    if not s: return {'ok':False,'action':'stop','reason':'session_missing','resumable':False}
    state=str(s.get('status') or '').lower(); stored=str(s.get('snapshot_sha256') or '')
    if state in {'completed'}: return {'ok':True,'action':'complete','reason':'already_completed','resumable':False}
    if not led.get('ok',True):
        return {'ok':False,'action':'rollback' if checkpoint else 'stop','reason':'ledger_invalid','resumable':False,'checkpoint':checkpoint}
    if not sc.get('ok',True) or bool(sc.get('drift')):
        return {'ok':False,'action':'revalidate','reason':'scope_drift','resumable':False}
    if stored and current_snapshot_sha256 and stored!=str(current_snapshot_sha256):
        return {'ok':False,'action':'revalidate','reason':'workspace_snapshot_changed','resumable':False}
    if state in {'prepared','running','paused','repairing','interrupted'}:
        return {'ok':True,'action':'resume','reason':'verified_interruption_state','resumable':True}
    return {'ok':False,'action':'stop','reason':'session_state_not_resumable','resumable':False}
