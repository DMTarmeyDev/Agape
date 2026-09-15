from __future__ import annotations

from typing import Any

_SAFE_KINDS={'inspect','read','analysis','test','evidence'}


def advise_parallelism(tasks: list[dict[str,Any]], max_parallel: int = 2) -> dict[str,Any]:
    cap=max(1,min(int(max_parallel or 2),4)); safe=[]; serial=[]
    for raw in tasks or []:
        item=dict(raw or {}); ident=str(item.get('id') or ''); kind=str(item.get('kind') or 'work').lower(); files={str(x).replace('\\','/') for x in item.get('files') or []}; writes=bool(item.get('writes')) or kind in {'edit','write','patch','delete','install'}
        row={'id':ident,'kind':kind,'files':sorted(files),'writes':writes}
        if not writes and kind in _SAFE_KINDS: safe.append(row)
        else: serial.append(row)
    groups=[]; pending=list(safe)
    while pending:
        group=[]; used=set(); rest=[]
        for item in pending:
            files=set(item['files'])
            if len(group)<cap and not (used & files): group.append(item); used|=files
            else: rest.append(item)
        groups.append([x['id'] for x in group]); pending=rest
    groups.extend([[x['id']] for x in serial])
    return {'ok':True,'max_parallel':cap if safe else 1,'parallel_groups':groups,'serialized':[x['id'] for x in serial],'policy':'read_and_test_only;writes_serialized'}
