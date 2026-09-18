from __future__ import annotations

import hashlib
from typing import Any
import db


def failure_hash(text: Any) -> str:
    return hashlib.sha256(str(text or '').encode('utf-8',errors='replace')).hexdigest().upper()[:20]


def classify_observations(observations: list[dict[str,Any]], min_runs: int = 3) -> dict[str,Any]:
    rows=list(observations or []); total=len(rows); passes=sum(1 for x in rows if str(x.get('status') or '').upper()=='PASS'); fails=total-passes
    signatures=sorted({str(x.get('failure_hash') or '') for x in rows if str(x.get('status') or '').upper()!='PASS' and str(x.get('failure_hash') or '')})
    enough=total>=max(2,int(min_runs or 3))
    flaky=bool(enough and passes>0 and fails>0)
    deterministic=bool(enough and fails==total and len(signatures)<=1)
    classification='flaky' if flaky else ('deterministic_failure' if deterministic else ('stable_pass' if enough and passes==total else 'insufficient_data'))
    return {'ok':True,'classification':classification,'flaky':flaky,'deterministic_failure':deterministic,'runs':total,'passes':passes,'failures':fails,'pass_rate':round((passes/total) if total else 0.0,4),'failure_signatures':signatures}


def record_and_classify(project_id: int, test_name: str, status: str, duration_seconds: float = 0.0, failure_text: str = '', session_id: str = '', limit: int = 20) -> dict[str,Any]:
    state=str(status or '').upper()
    if state not in {'PASS','FAIL'}: raise ValueError('TEST_OBSERVATION_STATUS_INVALID')
    item=db.record_test_observation(int(project_id),str(test_name or ''),state,float(duration_seconds or 0.0),failure_hash(failure_text) if state=='FAIL' else '',str(session_id or ''))
    history=db.list_test_observations(int(project_id),str(test_name or ''),int(limit or 20))
    result=classify_observations(list(reversed(history)))
    return {'ok':True,'observation':item,'history':history,'classification':result}
