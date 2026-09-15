from __future__ import annotations

import json, shutil, tempfile
from pathlib import Path
from typing import Any


def apply_transaction(workspace: str, plan: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
    if not isinstance(plan,dict) or not plan.get('ok') or not plan.get('safe'): raise ValueError('SAFE_PATCH_PLAN_REQUIRED')
    root=Path(workspace).expanduser().resolve()
    if not root.is_dir(): raise ValueError('WORKSPACE_NOT_FOUND')
    changes=list(plan.get('changes') or [])
    preview=[{'path':str(x.get('path') or ''),'before_sha256':str(x.get('before_sha256') or ''),'after_sha256':str(x.get('after_sha256') or '')} for x in changes]
    if dry_run: return {'ok':True,'dry_run':True,'applied':False,'changes':preview}
    backup=Path(tempfile.mkdtemp(prefix='agape-patch-backup-')); journal=[]
    try:
        for item in changes:
            rel=str(item['path']); target=(root/rel).resolve(); target.relative_to(root)
            if target.is_symlink(): raise ValueError('PATCH_SYMLINK_BLOCKED')
            existed=target.exists(); back=backup/rel
            if existed:
                back.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,back)
            journal.append({'path':rel,'existed':existed})
            target.parent.mkdir(parents=True,exist_ok=True)
            tmp=target.with_name(target.name+'.agape-tmp')
            tmp.write_text(str(item['content']),encoding='utf-8',newline='')
            tmp.replace(target)
        return {'ok':True,'dry_run':False,'applied':True,'changes':preview,'backup_root':str(backup)}
    except Exception:
        for item in reversed(journal):
            target=(root/item['path']).resolve(); back=backup/item['path']
            try:
                if item['existed'] and back.is_file():
                    target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(back,target)
                elif not item['existed'] and target.exists(): target.unlink()
            except Exception: pass
        raise
