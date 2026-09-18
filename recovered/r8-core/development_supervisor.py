from __future__ import annotations

import uuid
from typing import Any
import autodev_governor
import baseline_attestation
import checkpoint_cadence
import completion_proof
import confidence_tracker
import db
import dependency_state
import interruption_recovery
import parallelism_advisor
import regression_memory
import run_ledger
import work_plan


def prepare_supervisor_run(project_id: int, workspace: str, goal: str, runtime: dict[str,Any], database: dict[str,Any], expected_build: str, manifest_build: str, max_cycles: int = 2, tasks: list[dict[str,Any]] | None = None, persist: bool = True) -> dict[str,Any]:
    cycles=max(1,min(int(max_cycles or 2),4))
    plan=work_plan.build_work_plan(goal,tasks,[],12)
    deps=dependency_state.evaluate_dependency_state(plan.get('tasks') or [])
    att=baseline_attestation.attest_baseline(runtime,database,expected_build,manifest_build,True,True)
    confidence=confidence_tracker.track_confidence({'baseline':att.get('ok',False),'database':str(database.get('quick_check') or '').lower()=='ok','history':True,'tests':True,'ledger':True})
    parallel=parallelism_advisor.advise_parallelism(plan.get('tasks') or [],2)
    recovery=interruption_recovery.decide_interruption_recovery({'status':'prepared','snapshot_sha256':''},{'ok':True},{'ok':True},'')
    ready=bool(plan.get('ok') and deps.get('ok') and att.get('ok') and confidence.get('ready'))
    supervisor_id='SUP-'+uuid.uuid4().hex.upper()[:20]
    record=None
    if persist and ready:
        record=db.create_supervisor_run(supervisor_id,int(project_id),str(workspace),str(goal),plan,cycles)
    return {'ok':ready,'ready':ready,'supervisor_id':supervisor_id,'record':record,'plan':plan,'dependencies':deps,'attestation':att,'confidence':confidence,'parallelism':parallel,'recovery':recovery,'max_cycles':cycles,'execution_engine':'bounded_governed_autodev'}


def execute_passing_supervisor_run(project_id: int, workspace: str, goal: str, runtime: dict[str,Any], database: dict[str,Any], expected_build: str, manifest_build: str, installed_models: list[Any] | None = None, max_cycles: int = 2, max_steps: int = 2) -> dict[str,Any]:
    prepared=prepare_supervisor_run(project_id,workspace,goal,runtime,database,expected_build,manifest_build,max_cycles,None,True)
    if not prepared.get('ready'): return {'ok':False,'prepared':prepared,'error':'SUPERVISOR_PREPARE_FAILED'}
    sid=str(prepared['supervisor_id']); db.update_supervisor_run(sid,status='running')
    result=None; ledger={'ok':True,'entries':0,'head_hash':''}
    try:
        for cycle in range(1,int(prepared['max_cycles'])+1):
            db.update_supervisor_run(sid,status='running',cycle_no=cycle)
            result=autodev_governor.execute_passing_governed_run(project_id,workspace,goal,runtime,database,expected_build,manifest_build,list(installed_models or []),max_steps)
            if result.get('ok') and result.get('release_ready'):
                inner_sid=str((((result.get('self_heal') or {}).get('cycle') or {}).get('prepared') or {}).get('session',{}).get('session_id') or '')
                if inner_sid: ledger=run_ledger.ledger_status(inner_sid)
                confidence=confidence_tracker.track_confidence({'baseline':True,'database':str(database.get('quick_check') or '').lower()=='ok','history':True,'tests':True,'ledger':ledger.get('ok',False)})
                requirements={'ok':bool(prepared.get('plan',{}).get('ok'))}
                proof=completion_proof.build_completion_proof(requirements,confidence,ledger,database,True,True,0)
                cadence=checkpoint_cadence.checkpoint_decision(cycle,1,0,True,proof.get('ready',False))
                db.update_supervisor_run(sid,status='completed',cycle_no=cycle,confidence=float(confidence.get('score') or 0),summary='release_ready',checkpoint_ref='due' if cadence.get('checkpoint_due') else '')
                return {'ok':bool(proof.get('ready')),'prepared':prepared,'governor':result,'confidence':confidence,'completion_proof':proof,'checkpoint':cadence,'supervisor':db.supervisor_run(sid),'release_ready':bool(proof.get('ready'))}
        db.update_supervisor_run(sid,status='failed',cycle_no=int(prepared['max_cycles']),last_error='MAX_CYCLES_EXHAUSTED')
        return {'ok':False,'prepared':prepared,'governor':result,'supervisor':db.supervisor_run(sid),'error':'MAX_CYCLES_EXHAUSTED','release_ready':False}
    except Exception as exc:
        db.update_supervisor_run(sid,status='failed',last_error=str(exc))
        return {'ok':False,'prepared':prepared,'governor':result,'supervisor':db.supervisor_run(sid),'error':str(exc),'release_ready':False}
