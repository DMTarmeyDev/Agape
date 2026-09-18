from __future__ import annotations

from pathlib import Path
from typing import Any

import workspace_snapshot


def _clean_path(value: str) -> str:
    text=str(value or '').strip().replace('\\','/').lstrip('/')
    if not text or text.startswith('../') or '/..' in text or ':' in text.split('/')[0]:
        raise ValueError('SCOPE_PATH_INVALID')
    return text


def create_scope_lock(workspace: str, allowed_paths: list[str] | None = None, max_files: int = 1000) -> dict[str, Any]:
    snap=workspace_snapshot.create_snapshot(workspace,max_files)
    hashes={str(x['path']):str(x['sha256']) for x in snap['files']}
    allowed=sorted({_clean_path(x) for x in (allowed_paths or [])})
    if not allowed:
        allowed=sorted(hashes)
    return {'ok':True,'root':snap['root'],'snapshot_sha256':snap['snapshot_sha256'],'file_hashes':hashes,'allowed_paths':allowed,'file_count':snap['file_count']}


def check_scope_lock(lock: dict[str, Any], workspace: str, max_files: int = 1000) -> dict[str, Any]:
    if not isinstance(lock,dict) or not lock.get('snapshot_sha256'):
        raise ValueError('SCOPE_LOCK_REQUIRED')
    snap=workspace_snapshot.create_snapshot(workspace,max_files)
    if Path(str(lock.get('root') or '')).resolve()!=Path(str(snap['root'])).resolve():
        raise ValueError('SCOPE_ROOT_MISMATCH')
    before={str(k):str(v) for k,v in dict(lock.get('file_hashes') or {}).items()}
    after={str(x['path']):str(x['sha256']) for x in snap['files']}
    changed=sorted([p for p in set(before)|set(after) if before.get(p)!=after.get(p)])
    allowed=set(str(x) for x in list(lock.get('allowed_paths') or []))
    unexpected=sorted([p for p in changed if p not in allowed])
    return {'ok':True,'safe':not unexpected,'drifted':bool(changed),'changed_paths':changed,'unexpected_paths':unexpected,'snapshot_sha256':snap['snapshot_sha256']}
