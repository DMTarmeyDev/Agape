from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}', str(text or '').lower()) if len(x)>=3}


def build_context_pack(workspace: str, goal: str, snapshot: dict[str, Any] | None = None, max_files: int = 12, max_chars: int = 24000) -> dict[str, Any]:
    root=Path(workspace).expanduser().resolve()
    if not root.is_dir(): raise ValueError('WORKSPACE_NOT_FOUND')
    want=_tokens(goal); candidates=[]
    for item in list((snapshot or {}).get('files') or []):
        rel=str(item.get('path') or '')
        if not rel: continue
        path=(root/rel).resolve()
        try: path.relative_to(root)
        except ValueError: continue
        if not path.is_file() or path.is_symlink(): continue
        name_tokens=_tokens(rel); score=len(want & name_tokens)*8
        try: text=path.read_text(encoding='utf-8-sig',errors='replace')
        except OSError: continue
        head=text[:12000]; score += len(want & _tokens(head))
        if rel.lower() in {'readme.md','manifest.json','app.py','config.py'}: score += 2
        candidates.append((score,rel,head))
    candidates.sort(key=lambda x:(-x[0],x[1].lower()))
    selected=[]; used=0
    for score,rel,text in candidates:
        if len(selected)>=max(1,min(int(max_files or 12),40)): break
        if used>=max_chars: break
        take=text[:max(0,max_chars-used)]
        selected.append({'path':rel,'score':score,'content':take}); used+=len(take)
    return {'ok':True,'goal':str(goal or '').strip(),'files':selected,'file_count':len(selected),'chars':used}
