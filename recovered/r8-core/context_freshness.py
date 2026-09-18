from __future__ import annotations

from typing import Any
import workspace_snapshot


def check_context_freshness(workspace: str, captured_snapshot: dict[str,Any], allowed_changed_paths: list[str] | None = None, max_files: int = 1000) -> dict[str,Any]:
    if not isinstance(captured_snapshot,dict) or not captured_snapshot.get('snapshot_sha256'):
        raise ValueError('CAPTURED_SNAPSHOT_REQUIRED')
    current=workspace_snapshot.create_snapshot(workspace,max_files)
    old={str(x.get('path')):str(x.get('sha256')) for x in list(captured_snapshot.get('files') or [])}
    new={str(x.get('path')):str(x.get('sha256')) for x in list(current.get('files') or [])}
    changed=sorted(p for p in set(old)|set(new) if old.get(p)!=new.get(p))
    allowed={str(x).replace('\\','/').lstrip('/') for x in (allowed_changed_paths or [])}
    unexpected=[p for p in changed if p not in allowed]
    fresh=(str(captured_snapshot.get('snapshot_sha256'))==str(current.get('snapshot_sha256')))
    return {'ok':True,'fresh':fresh,'safe':not unexpected,'stale':bool(changed),'changed_paths':changed,'unexpected_paths':unexpected,'captured_sha256':str(captured_snapshot.get('snapshot_sha256')),'current_sha256':str(current.get('snapshot_sha256')),'current':current}
