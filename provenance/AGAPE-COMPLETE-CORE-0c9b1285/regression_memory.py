from __future__ import annotations

from collections import defaultdict
from typing import Any
import db


def summarize_regression_memory(observations: list[dict[str,Any]]) -> dict[str,Any]:
    groups=defaultdict(list)
    for raw in observations or []:
        item=dict(raw or {}); name=str(item.get('test_name') or '').strip()
        if name: groups[name].append(item)
    tests=[]
    for name,rows in sorted(groups.items()):
        ordered=sorted(rows,key=lambda x:int(x.get('id') or 0)); passes=sum(1 for x in ordered if str(x.get('status') or '').upper()=='PASS'); fails=len(ordered)-passes
        states={str(x.get('status') or '').upper() for x in ordered}; flaky='PASS' in states and 'FAIL' in states
        recurring=fails>=2 and fails>=passes
        tests.append({'test_name':name,'runs':len(ordered),'passes':passes,'failures':fails,'flaky':flaky,'recurring_failure':recurring,'last_status':str(ordered[-1].get('status') or '').upper()})
    recommended=[x['test_name'] for x in tests if x['recurring_failure'] or x['flaky'] or x['last_status']=='FAIL']
    return {'ok':True,'tests':tests,'recommended_tests':recommended,'tracked_tests':len(tests)}


def project_regression_memory(project_id: int, limit: int = 200) -> dict[str,Any]:
    return summarize_regression_memory(db.list_test_observations(int(project_id),'',max(1,min(int(limit or 200),500))))
