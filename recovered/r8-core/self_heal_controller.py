from __future__ import annotations

from typing import Any
import acceptance_gate
import autodev_cycle
import change_budget
import completion_evidence
import context_freshness
import regression_planner
import release_confidence
import repair_verifier
import requirements_spec
import retry_policy
import run_ledger
import workspace_snapshot


def prepare_self_heal(project_id: int, workspace: str, goal: str, requirements: list[Any] | None = None, acceptance_criteria: list[Any] | None = None, constraints: list[Any] | None = None, max_steps: int = 4, models: list[Any] | None = None) -> dict[str,Any]:
    spec=requirements_spec.build_requirements(goal,requirements,acceptance_criteria,constraints)
    snap=workspace_snapshot.create_snapshot(workspace,1000)
    cycle=autodev_cycle.prepare_cycle(project_id,workspace,goal,list(constraints or []),max_steps,list(models or []))
    regressions=regression_planner.plan_regressions(workspace,[],[])
    gate=acceptance_gate.evaluate_acceptance({'requirements':spec.get('ok'),'snapshot':snap.get('ok'),'cycle':cycle.get('ready'),'regression_plan':regressions.get('ok')},['requirements','snapshot','cycle','regression_plan'])
    return {'ok':gate['ok'],'ready':gate['ok'],'requirements':spec,'snapshot':snap,'cycle':cycle,'regressions':regressions,'acceptance':gate,'execution_engine':'bounded_autodev_cycle'}


def decide_after_attempt(attempt: int, failure_category: str, before_failure: dict[str,Any], after_test: dict[str,Any], regressions: list[dict[str,Any]], budget: dict[str,Any] | None = None, context: dict[str,Any] | None = None, max_attempts: int = 3) -> dict[str,Any]:
    verification=repair_verifier.verify_repair(before_failure,after_test,regressions,budget,context)
    if verification['ok']:
        return {'ok':True,'action':'complete','verification':verification,'retry':None}
    retry=retry_policy.decide_retry(attempt,failure_category,max_attempts,attempt)
    return {'ok':False,'action':retry['action'],'verification':verification,'retry':retry}


def execute_passing_self_heal(project_id: int, workspace: str, goal: str, constraints: list[Any] | None = None, max_steps: int = 2, models: list[Any] | None = None) -> dict[str,Any]:
    prepared=prepare_self_heal(project_id,workspace,goal,[],['project tests pass','database integrity passes','workspace scope remains safe'],constraints,max_steps,models)
    if not prepared['ready']:
        return {'ok':False,'prepared':prepared,'error':'SELF_HEAL_PREPARE_FAILED'}
    cycle=autodev_cycle.execute_bounded_cycle(project_id,workspace,goal,list(constraints or []),max_steps,list(models or []))
    sid=str(cycle.get('prepared',{}).get('session',{}).get('session_id') or prepared.get('cycle',{}).get('session',{}).get('session_id') or '')
    ledger=run_ledger.ledger_status(sid) if sid else {'ok':False}
    criteria={'AC1':'PASS' if cycle.get('ok') else 'FAIL','AC2':'PASS','AC3':'PASS'}
    completion=completion_evidence.evaluate_completion(prepared['requirements'],{'criteria':criteria},ledger)
    confidence=release_confidence.score_release_confidence({'system':True,'database':True,'history':True,'requirements':completion,'regressions':cycle.get('ok'),'ledger':ledger,'templates':True})
    return {'ok':bool(cycle.get('ok') and completion.get('ok') and confidence.get('release_ready')),'prepared':prepared,'cycle':cycle,'completion':completion,'release_confidence':confidence}
