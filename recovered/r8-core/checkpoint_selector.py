from __future__ import annotations

from typing import Any


def select_checkpoint(checkpoints: list[dict[str,Any]], expected_build: str = '', require_verified: bool = True) -> dict[str,Any]:
    expected=str(expected_build or '').strip(); rows=[]
    for raw in checkpoints or []:
        c=dict(raw or {}); verified=bool(c.get('verified',c.get('ok',False))); build=str(c.get('build') or ''); path=str(c.get('path') or '')
        compatible=(not expected) or build==expected
        eligible=bool(path) and compatible and (verified or not require_verified)
        ts=float(c.get('modified') or c.get('timestamp') or 0.0)
        rows.append({'path':path,'build':build,'verified':verified,'compatible':compatible,'eligible':eligible,'timestamp':ts,'label':str(c.get('label') or c.get('name') or '')})
    rows.sort(key=lambda x:(not x['eligible'],-x['timestamp'],x['path']))
    selected=next((x for x in rows if x['eligible']),None)
    return {'ok':bool(selected),'selected':selected,'candidates':rows,'reason':'latest_verified_compatible' if selected else 'no_verified_compatible_checkpoint'}
