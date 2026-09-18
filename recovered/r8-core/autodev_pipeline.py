from __future__ import annotations

from typing import Any

import goal_spec, workspace_snapshot, context_pack, work_breakdown, test_planner, test_selector, test_matrix


def prepare_pipeline(workspace: str, goal: str, constraints: list[str] | None = None, max_steps: int = 4) -> dict[str, Any]:
    steps=max(1,min(int(max_steps or 4),8))
    spec=goal_spec.normalize_goal(goal,constraints)
    snap=workspace_snapshot.create_snapshot(workspace,1000)
    ctx=context_pack.build_context_pack(workspace,spec['goal'],snap,12,24000)
    plan=work_breakdown.build_work_plan(spec,ctx,min(steps+2,8))
    tests=test_planner.plan_tests(workspace)
    test_files=[x['path'] for x in snap['files'] if x['path'].lower().startswith('test_') and x['path'].lower().endswith('.py')]
    selected=test_selector.select_tests([x['path'] for x in ctx['files'][:3]],test_files)
    matrix=test_matrix.build_test_matrix(tests,list(selected.get('selected_tests') or []),tests.get('command') or '')
    return {'ok':True,'workspace':snap['root'],'goal_spec':spec,'snapshot_sha256':snap['snapshot_sha256'],'context':{'file_count':ctx['file_count'],'paths':[x['path'] for x in ctx['files']]},'work_plan':plan,'tests':tests,'selected_tests':selected,'test_matrix':matrix,'max_steps':steps,'execution_engine':'project_loop','ready':bool(tests.get('ok'))}
