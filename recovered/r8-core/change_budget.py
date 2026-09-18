from __future__ import annotations

import difflib
from typing import Any

DEFAULT_LIMITS={'max_files':8,'max_changed_lines':400,'max_total_bytes':262144,'max_single_file_bytes':131072}


def evaluate_change_budget(changes: list[dict[str,Any]], limits: dict[str,Any] | None = None) -> dict[str,Any]:
    rows=list(changes or [])
    lim=dict(DEFAULT_LIMITS); lim.update(dict(limits or {}))
    file_count=len({str(x.get('path') or '') for x in rows if str(x.get('path') or '')})
    changed_lines=0; total_bytes=0; largest=0
    details=[]
    for item in rows:
        path=str(item.get('path') or '').strip()
        if not path: raise ValueError('CHANGE_BUDGET_PATH_REQUIRED')
        before=str(item.get('before_content') or '')
        after=str(item.get('after_content') if item.get('after_content') is not None else item.get('content') or '')
        diff=list(difflib.ndiff(before.splitlines(),after.splitlines()))
        lines=sum(1 for line in diff if line.startswith('+ ') or line.startswith('- '))
        size=len(after.encode('utf-8')); total_bytes+=size; largest=max(largest,size); changed_lines+=lines
        details.append({'path':path,'changed_lines':lines,'after_bytes':size})
    reasons=[]
    if file_count>int(lim['max_files']): reasons.append('FILE_BUDGET_EXCEEDED')
    if changed_lines>int(lim['max_changed_lines']): reasons.append('LINE_BUDGET_EXCEEDED')
    if total_bytes>int(lim['max_total_bytes']): reasons.append('TOTAL_BYTE_BUDGET_EXCEEDED')
    if largest>int(lim['max_single_file_bytes']): reasons.append('SINGLE_FILE_BUDGET_EXCEEDED')
    return {'ok':not reasons,'allowed':not reasons,'file_count':file_count,'changed_lines':changed_lines,'total_bytes':total_bytes,'largest_file_bytes':largest,'limits':lim,'reasons':reasons,'changes':details}
