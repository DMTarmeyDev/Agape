from __future__ import annotations

from typing import Any

import acceptance_gate
import adaptive_router
import autodev_pipeline
import autodev_session
import db
import failure_triage
import repair_cycle
import run_ledger
import scope_lock
import task_graph


def prepare_cycle(project_id: int, workspace: str, goal: str, constraints: list[str] | None = None, max_steps: int = 4, installed_models: list[Any] | None = None) -> dict[str, Any]:
    models=list(installed_models or [])
    created=autodev_session.create_session(project_id,workspace,goal,'',max_steps,'')
    session=created['session']; sid=str(session['session_id'])
    pipeline=autodev_pipeline.prepare_pipeline(workspace,goal,constraints,max_steps)
    graph=task_graph.build_task_graph(list(pipeline['work_plan']['tasks']))
    allowed=list(pipeline.get('context',{}).get('paths') or [])
    for extra in ('SELFTEST.py','pytest.ini','pyproject.toml','package.json'):
        if extra not in allowed: allowed.append(extra)
    lock=scope_lock.create_scope_lock(workspace,allowed)
    route=adaptive_router.choose_adaptive_model(models,goal,1,'') if models else {'ok':False,'model':'','reason':'MODELS_NOT_SUPPLIED'}
    if route.get('model'):
        session=db.update_autodev_session(sid,model=str(route['model']))
    required=['pipeline_ready','task_graph','scope_lock','test_plan']
    checks={'pipeline_ready':bool(pipeline.get('ready')),'task_graph':bool(graph.get('ok')),'scope_lock':bool(lock.get('ok')),'test_plan':bool(pipeline.get('tests',{}).get('ok'))}
    gate=acceptance_gate.evaluate_acceptance(checks,required)
    run_ledger.append_entry(sid,'PREPARED','PASS' if gate['ok'] else 'FAIL',{'snapshot_sha256':created['snapshot_sha256'],'model':route.get('model',''),'checks':checks})
    return {'ok':gate['ok'],'session':session,'pipeline':pipeline,'task_graph':graph,'scope_lock':lock,'model_route':route,'acceptance':gate,'execution_engine':'project_loop','ready':gate['ok']}


def finalize_cycle(session_id: str, test_passed: bool, stdout: str = '', stderr: str = '', exit_code: int | None = None, duration_seconds: float = 0.0, model: str = '', checks: dict[str, Any] | None = None) -> dict[str, Any]:
    session=db.autodev_session(str(session_id or ''))
    if not session: raise ValueError('AUTODEV_SESSION_NOT_FOUND')
    triage=failure_triage.triage_failure(stdout,stderr,exit_code)
    used_model=str(model or session.get('model') or '')
    if used_model:
        db.record_model_outcome(used_model,'coding',bool(test_passed),float(duration_seconds or 0.0),triage['category'],str(session_id))
    attempt=int(session.get('attempt') or 0)+1
    decision=repair_cycle.decide_repair(bool(test_passed),attempt,int(session.get('max_steps') or 4),[triage.get('summary','')] if not test_passed else [],True)
    gate=acceptance_gate.evaluate_acceptance(dict(checks or {'tests':bool(test_passed)}))
    if test_passed and gate['ok']:
        state='completed'
    elif decision['action']=='rollback': state='failed'
    elif decision['action'] in {'repair','escalate'}: state='repairing'
    else: state='paused'
    updated=db.update_autodev_session(str(session_id),status=state,attempt=attempt,model=used_model,error='' if test_passed else triage.get('summary',''))
    run_ledger.append_entry(str(session_id),'CYCLE_RESULT','PASS' if test_passed else 'FAIL',{'triage':triage,'decision':decision,'acceptance':gate,'attempt':attempt})
    return {'ok':bool(test_passed and gate['ok']),'session':updated,'triage':triage,'decision':decision,'acceptance':gate}


def execute_bounded_cycle(project_id: int, workspace: str, goal: str, constraints: list[str] | None = None, max_steps: int = 4, installed_models: list[Any] | None = None) -> dict[str, Any]:
    import project_loop
    prepared=prepare_cycle(project_id,workspace,goal,constraints,max_steps,installed_models)
    sid=str(prepared['session']['session_id'])
    model=str(prepared.get('model_route',{}).get('model') or '')
    db.update_autodev_session(sid,status='running',model=model)
    run_ledger.append_entry(sid,'EXECUTION_START','PASS',{'engine':'project_loop'})
    try:
        run=project_loop.run_project_loop(project_id=project_id,workspace=workspace,goal=goal,test_command=str(prepared['pipeline']['tests']['command']),max_steps=max_steps,auto_model=True,model=model)
        passed=str(run.get('overall') or run.get('status') or '').upper() in {'PASS','COMPLETED','SUCCESS'}
        final=finalize_cycle(sid,passed,str(run.get('summary') or ''),str(run.get('error') or ''),0,0.0,model,{'project_loop':passed})
        return {'ok':final['ok'],'prepared':prepared,'run':run,'final':final}
    except Exception as exc:
        final=finalize_cycle(sid,False,'',str(exc),1,0.0,model,{'project_loop':False})
        return {'ok':False,'prepared':prepared,'run':None,'final':final,'error':str(exc)}
