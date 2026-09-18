from __future__ import annotations
from typing import Any

def summarize_project(project: dict[str, Any], runs: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
    runs=list(runs or []); issues=list(issues or [])
    last=str(runs[0].get('status') or runs[0].get('overall') or '') if runs else 'NOT_RUN'
    open_issues=sum(1 for x in issues if str(x.get('status') or '').lower()=='open')
    overall='PASS' if last in {'PASS','completed','COMPLETED','NOT_RUN'} and open_issues==0 else ('WARN' if last not in {'FAIL','failed','FAILED'} else 'FAIL')
    return {'ok':True,'overall':overall,'project_id':int(project.get('id') or 0),'name':str(project.get('name') or ''),'last_run_status':last,'open_issues':open_issues,'run_count':len(runs)}
