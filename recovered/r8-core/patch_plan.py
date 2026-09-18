from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

_MAX_TEXT=512000


def _resolve(root: Path, rel: str) -> Path:
    rel=str(rel or '').replace('\\','/').strip()
    if not rel or rel.startswith('/') or ':' in rel.split('/')[0] or '..' in Path(rel).parts: raise ValueError('PATCH_PATH_INVALID')
    p=(root/rel).resolve()
    try: p.relative_to(root)
    except ValueError: raise ValueError('PATCH_PATH_ESCAPE')
    if p.is_symlink(): raise ValueError('PATCH_SYMLINK_BLOCKED')
    return p


def validate_patch_plan(workspace: str, changes: list[dict[str, Any]], protected_names: list[str] | None = None) -> dict[str, Any]:
    root=Path(workspace).expanduser().resolve()
    if not root.is_dir(): raise ValueError('WORKSPACE_NOT_FOUND')
    protected={str(x).replace('\\','/').lower() for x in list(protected_names or [])}; clean=[]
    if not changes or len(changes)>20: raise ValueError('PATCH_CHANGE_COUNT_INVALID')
    for item in changes:
        rel=str(item.get('path') or '').replace('\\','/'); p=_resolve(root,rel); op=str(item.get('op') or 'write').lower()
        if op not in {'write'}: raise ValueError('PATCH_OPERATION_NOT_ALLOWED')
        if rel.lower() in protected or Path(rel).name.lower() in protected: raise ValueError('PATCH_PROTECTED_FILE')
        text=item.get('content')
        if not isinstance(text,str): raise ValueError('PATCH_TEXT_REQUIRED')
        if len(text.encode('utf-8'))>_MAX_TEXT: raise ValueError('PATCH_TEXT_TOO_LARGE')
        before=''
        if p.exists():
            if not p.is_file(): raise ValueError('PATCH_TARGET_NOT_FILE')
            data=p.read_bytes()
            if b'\x00' in data[:4096]: raise ValueError('PATCH_BINARY_BLOCKED')
            before=hashlib.sha256(data).hexdigest().upper()
        expected=str(item.get('expected_sha256') or '').upper()
        if expected and expected!=before: raise ValueError('PATCH_STALE_SOURCE')
        clean.append({'op':'write','path':rel,'before_sha256':before,'after_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest().upper(),'content':text})
    return {'ok':True,'safe':True,'workspace':str(root),'changes':clean,'change_count':len(clean)}
