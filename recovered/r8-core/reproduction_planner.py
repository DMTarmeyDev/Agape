from __future__ import annotations

from pathlib import Path
from typing import Any
import regression_planner
import test_planner

_ALLOWED_PREFIXES=('python ','python.exe ','py ','pytest ','node ','npm ','npx ','dotnet ','cargo ','go ','ctest ','ninja ','make ')


def _safe(command: str) -> bool:
    c=str(command or '').strip(); low=c.lower()
    return bool(c) and not any(x in low for x in ('&&','||',';','|','>','<','powershell','cmd.exe','rm ','del ','remove-item','curl ','wget ')) and low.startswith(_ALLOWED_PREFIXES)


def plan_reproduction(workspace: str, evidence: dict[str,Any] | None = None, changed_files: list[Any] | None = None) -> dict[str,Any]:
    root=Path(workspace).expanduser().resolve()
    if not root.is_dir(): return {'ok':False,'reason':'workspace_not_found','commands':[]}
    ev=dict(evidence or {})
    history=list(ev.get('failed_tests') or [])
    plan=regression_planner.plan_regressions(str(root),list(changed_files or ev.get('changed_files') or []),history)
    commands=[]
    for phase in plan.get('phases') or []:
        cmd=str(phase.get('command') or '').strip()
        if _safe(cmd) and cmd not in commands: commands.append(cmd)
    if not commands:
        basic=test_planner.plan_tests(str(root)); cmd=str(basic.get('command') or '')
        if basic.get('ok') and _safe(cmd): commands=[cmd]
    return {'ok':bool(commands),'workspace':str(root),'commands':commands[:5],'minimal_command':commands[0] if commands else '','source':'regression_planner','reason':'safe_test_reproduction' if commands else 'no_safe_reproduction'}
