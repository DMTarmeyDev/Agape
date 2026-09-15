from __future__ import annotations

from typing import Any
import baseline_attestation
import execution_budget
import failure_evidence
import root_cause
import reproduction_planner
import repair_candidate
import checkpoint_selector
import autonomy_policy
import self_heal_controller


def prepare_governed_run(project_id: int, workspace: str, goal: str, runtime: dict[str,Any], database: dict[str,Any], expected_build: str, manifest_build: str, source_manifest_ok: bool = True, history_preserved: bool = True, failure: dict[str,Any] | None = None, changed_files: list[Any] | None = None, checkpoints: list[dict[str,Any]] | None = None, consumed: dict[str,Any] | None = None, limits: dict[str,Any] | None = None, change: dict[str,Any] | None = None) -> dict[str,Any]:
    att=baseline_attestation.attest_baseline(runtime,database,expected_build,manifest_build,source_manifest_ok,history_preserved)
    budget=execution_budget.evaluate_execution_budget(consumed,limits)
    autonomy=autonomy_policy.decide_autonomy(change or {'files':list(changed_files or []),'command':''},'safe')
    evidence=None; causes=None; reproduction=None
    if failure is not None:
        f=dict(failure or {})
        evidence=failure_evidence.build_failure_evidence(f.get('stdout',''),f.get('stderr',''),f.get('error',''),f.get('exit_code'),f.get('failed_tests'),list(changed_files or f.get('changed_files') or []))
        causes=root_cause.rank_root_causes(evidence,None,list(changed_files or []))
        reproduction=reproduction_planner.plan_reproduction(workspace,evidence,list(changed_files or []))
    checkpoint=checkpoint_selector.select_checkpoint(list(checkpoints or []),expected_build,True) if checkpoints else {'ok':True,'selected':None,'reason':'not_required'}
    ready=bool(att.get('ok') and budget.get('allowed') and autonomy.get('action')=='auto_continue' and (reproduction is None or reproduction.get('ok')))
    return {'ok':ready,'ready':ready,'project_id':int(project_id),'workspace':str(workspace),'goal':str(goal),'attestation':att,'execution_budget':budget,'autonomy':autonomy,'failure_evidence':evidence,'root_causes':causes,'reproduction':reproduction,'checkpoint':checkpoint,'execution_engine':'quality_controlled_self_heal'}


def score_repairs(candidates: list[dict[str,Any]]) -> dict[str,Any]:
    return repair_candidate.score_candidates(candidates)


def execute_passing_governed_run(project_id: int, workspace: str, goal: str, runtime: dict[str,Any], database: dict[str,Any], expected_build: str, manifest_build: str, installed_models: list[Any] | None = None, max_steps: int = 2) -> dict[str,Any]:
    prepared=prepare_governed_run(project_id,workspace,goal,runtime,database,expected_build,manifest_build,True,True,None,[],None,{'max_steps':0},{'max_steps':max(1,int(max_steps or 2))},{'files':[],'command':''})
    if not prepared['ready']:
        return {'ok':False,'prepared':prepared,'error':'GOVERNOR_PREPARE_FAILED'}
    result=self_heal_controller.execute_passing_self_heal(project_id,workspace,goal,['stay inside workspace','run tests after changes'],max_steps,list(installed_models or []))
    return {'ok':bool(result.get('ok')),'prepared':prepared,'self_heal':result,'release_ready':bool(result.get('release_confidence',{}).get('release_ready'))}
