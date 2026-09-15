from __future__ import annotations

from typing import Any


def classify_failure_freshness(failure: dict[str,Any], current_snapshot_sha256: str = '', observations: list[dict[str,Any]] | None = None) -> dict[str,Any]:
    f=dict(failure or {}); current=str(current_snapshot_sha256 or ''); old=str(f.get('snapshot_sha256') or '')
    if old and current and old!=current:
        return {'ok':True,'stale':True,'action':'suppress','reason':'workspace_changed_since_failure'}
    fail_id=int(f.get('observation_id') or f.get('id') or 0); test=str(f.get('test_name') or '')
    later_pass=False
    for raw in observations or []:
        item=dict(raw or {}); oid=int(item.get('id') or 0); state=str(item.get('status') or '').upper(); name=str(item.get('test_name') or '')
        if state=='PASS' and (not test or name==test) and (not fail_id or oid>fail_id): later_pass=True; break
    if later_pass: return {'ok':True,'stale':True,'action':'suppress','reason':'later_pass_supersedes_failure'}
    return {'ok':True,'stale':False,'action':'keep','reason':'failure_still_relevant'}
