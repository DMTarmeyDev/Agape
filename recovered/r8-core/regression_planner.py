from __future__ import annotations

from pathlib import Path
from typing import Any
import test_planner
import test_selector


def plan_regressions(workspace: str, changed_files: list[str] | None = None, historical_failures: list[str] | None = None) -> dict[str,Any]:
    root=Path(workspace).expanduser().resolve()
    planned=test_planner.plan_tests(str(root))
    test_files=sorted(p.name for p in root.glob('test_*.py') if p.is_file())
    targeted=test_selector.select_tests(list(changed_files or []),test_files) if test_files else {'selected_tests':[],'mode':'none','reason':'no_test_files'}
    selected=list(targeted.get('selected_tests') or [])
    historical=[]
    for raw in historical_failures or []:
        name=Path(str(raw)).name
        if name in test_files and name not in selected: selected.append(name); historical.append(name)
    phases=[]
    for name in selected: phases.append({'name':'targeted:'+name,'command':'python '+name,'required':True})
    if planned.get('ok') and planned.get('command'):
        phases.append({'name':'project','command':str(planned['command']),'required':True})
    ok=bool(phases)
    return {'ok':ok,'changed_files':list(changed_files or []),'selected_tests':selected,'historical_tests':historical,'project_test':planned,'phases':phases,'stop_on_failure':True}
