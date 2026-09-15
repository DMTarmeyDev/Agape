from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

def plan_retention(records: list[dict[str,Any]], keep_recent: int=50, preserve_failed: bool=True) -> dict[str,Any]:
    rows=[dict(x) for x in records or []]; recent=max(1,int(keep_recent or 50)); keep_ids=[]; archive_ids=[]
    for i,x in enumerate(rows):
        ident=x.get('id') or x.get('run_id') or x.get('session_id') or i
        status=str(x.get('status') or '').lower()
        if i<recent or (preserve_failed and status in {'failed','interrupted','rolled_back'}): keep_ids.append(ident)
        else: archive_ids.append(ident)
    return {'ok':True,'keep':keep_ids,'archive_candidates':archive_ids,'delete':[],'hard_delete':False,'policy':'archive_only_by_default'}
