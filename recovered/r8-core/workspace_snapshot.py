from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

_SKIP={'.git','node_modules','.venv','venv','__pycache__','.pytest_cache'}
_TEXT={'.py','.js','.ts','.tsx','.jsx','.json','.md','.txt','.html','.css','.ps1','.cmd','.bat','.toml','.ini','.yaml','.yml','.c','.h','.cpp','.hpp','.rs','.go','.java','.cs','.xml','.sql'}


def _root(value: str) -> Path:
    p=Path(value).expanduser().resolve()
    if not p.is_dir(): raise ValueError('WORKSPACE_NOT_FOUND')
    return p


def create_snapshot(workspace: str, max_files: int = 1000) -> dict[str, Any]:
    root=_root(workspace); limit=max(1,min(int(max_files or 1000),5000)); rows=[]
    for p in sorted(root.rglob('*'), key=lambda x: str(x).lower()):
        if len(rows)>=limit: break
        try:
            rel=p.relative_to(root)
        except ValueError:
            continue
        if any(part in _SKIP for part in rel.parts) or p.is_symlink() or not p.is_file() or p.suffix.lower() not in _TEXT:
            continue
        try: data=p.read_bytes()
        except OSError: continue
        if b'\x00' in data[:4096]: continue
        rows.append({'path':rel.as_posix(),'size':len(data),'sha256':hashlib.sha256(data).hexdigest().upper()})
    digest=hashlib.sha256('\n'.join(f"{x['path']}:{x['sha256']}" for x in rows).encode('utf-8')).hexdigest().upper()
    return {'ok':True,'root':str(root),'file_count':len(rows),'truncated':len(rows)>=limit,'snapshot_sha256':digest,'files':rows}
