from __future__ import annotations
import hashlib
from pathlib import Path

SKIP={'.git','.venv','venv','node_modules','__pycache__'}
def _snapshot(root):
    base=Path(root).expanduser().resolve(); out={}
    if not base.is_dir(): raise ValueError('ROOT_NOT_FOUND')
    for p in base.rglob('*'):
        if any(x in SKIP for x in p.relative_to(base).parts): continue
        if p.is_symlink(): raise ValueError('SYMLINK_NOT_ALLOWED')
        if p.is_file(): out[p.relative_to(base).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return out

def preview_changes(before_root, after_root, protected_names=None):
    a=_snapshot(before_root); b=_snapshot(after_root); protected=set(str(x).replace('\\','/') for x in (protected_names or []))
    added=sorted(set(b)-set(a)); removed=sorted(set(a)-set(b)); changed=sorted(k for k in set(a)&set(b) if a[k]!=b[k])
    touched=set(added+removed+changed); protected_changed=sorted(p for p in touched if p in protected or Path(p).name in protected)
    return {'ok':True,'safe':not protected_changed,'added_files':added,'removed_files':removed,'changed_files':changed,'protected_changed':protected_changed}
