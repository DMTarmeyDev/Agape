from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import db
from config import BUILD, WORKFLOW_ROOT
from orchestrator import run_chat
from providers import ollama_models
from security import ensure_session_token
from tools import analyze_command, run_powershell

PREFERRED_MODEL = "qwen2.5-coder:1.5b-instruct"
SNAKE_HTML = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DMT Snake</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1220;color:#e5eef9;font-family:Segoe UI,Arial,sans-serif}.wrap{width:min(94vw,620px);text-align:center}.bar{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:10px 0}canvas{width:100%;height:auto;border:2px solid #334155;background:#020617;image-rendering:pixelated}.help{color:#9fb0c5;font-size:14px}button{padding:8px 12px;border:1px solid #475569;border-radius:8px;background:#172033;color:#fff;cursor:pointer}</style></head><body><main class="wrap"><h1>DMT Snake</h1><div class="bar"><b>Score: <span id="score">0</span></b><b>Best: <span id="best">0</span></b><span id="state">Running</span></div><canvas id="game" width="600" height="600"></canvas><p class="help">Arrow keys / WASD move · Space/P pause · R restart</p><button id="restart">Restart</button></main><script>(()=>{\'use strict\';const c=document.getElementById(\'game\'),x=c.getContext(\'2d\'),scoreEl=document.getElementById(\'score\'),bestEl=document.getElementById(\'best\'),stateEl=document.getElementById(\'state\'),N=20,S=c.width/N;let snake,dir,next,food,score,best=Number(localStorage.getItem(\'dmt-snake-best\')||0),paused,dead,timer;bestEl.textContent=best;function rnd(){return Math.floor(Math.random()*N)}function spawn(){do{food={x:rnd(),y:rnd()}}while(snake.some(p=>p.x===food.x&&p.y===food.y))}function reset(){snake=[{x:10,y:10},{x:9,y:10},{x:8,y:10}];dir={x:1,y:0};next={...dir};score=0;paused=false;dead=false;scoreEl.textContent=0;stateEl.textContent=\'Running\';spawn();clearInterval(timer);timer=setInterval(tick,105);draw()}function turn(nx,ny){if(nx===-dir.x&&ny===-dir.y)return;next={x:nx,y:ny}}function tick(){if(paused||dead)return;dir=next;const h={x:snake[0].x+dir.x,y:snake[0].y+dir.y};if(h.x<0||h.y<0||h.x>=N||h.y>=N||snake.some(p=>p.x===h.x&&p.y===h.y)){dead=true;stateEl.textContent=\'Game over — press R\';draw();return}snake.unshift(h);if(h.x===food.x&&h.y===food.y){score++;scoreEl.textContent=score;if(score>best){best=score;bestEl.textContent=best;localStorage.setItem(\'dmt-snake-best\',String(best))}spawn()}else snake.pop();draw()}function draw(){x.fillStyle=\'#020617\';x.fillRect(0,0,c.width,c.height);x.fillStyle=\'#ef4444\';x.fillRect(food.x*S+2,food.y*S+2,S-4,S-4);snake.forEach((p,i)=>{x.fillStyle=i?\'#22c55e\':\'#86efac\';x.fillRect(p.x*S+1,p.y*S+1,S-2,S-2)})}addEventListener(\'keydown\',e=>{const k=e.key.toLowerCase();if([\'arrowup\',\'arrowdown\',\'arrowleft\',\'arrowright\',\'w\',\'a\',\'s\',\'d\',\' \',\'p\',\'r\'].includes(k))e.preventDefault();if(k===\'arrowup\'||k===\'w\')turn(0,-1);else if(k===\'arrowdown\'||k===\'s\')turn(0,1);else if(k===\'arrowleft\'||k===\'a\')turn(-1,0);else if(k===\'arrowright\'||k===\'d\')turn(1,0);else if(k===\' \'||k===\'p\'){if(!dead){paused=!paused;stateEl.textContent=paused?\'Paused\':\'Running\'}}else if(k===\'r\')reset()});document.getElementById(\'restart\').onclick=reset;reset()})();</script></body></html>'

TEMPLATES = [
    {"id":"system-stress","number":1,"name":"System Stress Test + Fault Finder","kind":"diagnostic","description":"Deterministic end-to-end Core, AI, terminal, safety, database and recovery checks."},
    {"id":"snake-game","number":2,"name":"Snake Game - Build, Verify + Run","kind":"build","description":"Builds a self-contained Snake game, verifies required features, hashes it and launches it."},
]


def list_templates() -> list[dict[str, Any]]:
    return [dict(x) for x in TEMPLATES]


def _project(name: str) -> dict[str, Any]:
    for item in db.list_projects(scope="all"):
        if str(item.get("name")) == name:
            return item
    project=db.create_project(name, kind="template", archived=True)
    return project


def _psq(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest().upper()


def _report(template_id: str, result: dict[str, Any]) -> Path:
    root=WORKFLOW_ROOT / "reports"
    root.mkdir(parents=True,exist_ok=True)
    stamp=time.strftime('%Y%m%d-%H%M%S')
    path=root / f"{template_id}-{stamp}.json"
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return path


def _check(results: list[dict[str, Any]], name: str, fn: Callable[[], Any]) -> Any:
    started=time.monotonic()
    try:
        value=fn()
        results.append({"name":name,"status":"PASS","duration_seconds":round(time.monotonic()-started,3),"detail":value})
        return value
    except Exception as exc:
        results.append({"name":name,"status":"FAIL","duration_seconds":round(time.monotonic()-started,3),"error":str(exc)})
        return None


def run_template_1(model: str=PREFERRED_MODEL) -> dict[str, Any]:
    started=time.monotonic(); checks=[]
    root=WORKFLOW_ROOT / "template-1-system-stress"; root.mkdir(parents=True,exist_ok=True)
    project=_project("Template 1 - System Stress Test")
    pid=int(project['id'])

    _check(checks,"database_integrity",lambda: _require(db.status().get('ok') is True,'DB_QUICK_CHECK_FAILED') or db.status())
    _check(checks,"session_security",lambda: _require(len(ensure_session_token())>=32,'SESSION_TOKEN_INVALID') or {"token_exposed":False})
    models=_check(checks,"ollama_service",lambda: [str(m.get('name') or '') for m in ollama_models()])
    _check(checks,"preferred_model",lambda: _require(isinstance(models,list) and model in models,'PREFERRED_MODEL_MISSING') or model)

    terminal=_check(checks,"powershell_execution",lambda: run_powershell("Write-Output 'DMT_TEMPLATE1_TERMINAL_OK'",pid))
    if terminal is not None and not (terminal.get('executed') and terminal.get('exit_code')==0 and terminal.get('stdout','').strip()=='DMT_TEMPLATE1_TERMINAL_OK'):
        checks[-1].update(status='FAIL',error='POWERSHELL_OUTPUT_MISMATCH')

    ai_path=root/'ai-terminal-proof.txt'; ai_value='DMT_TEMPLATE1_AI_TERMINAL_OK'
    def ai_probe(probe_model: str):
        if ai_path.exists():
            ai_path.unlink()
        exact_cmd=(
            f"Set-Content -LiteralPath {_psq(str(ai_path))} -Value {_psq(ai_value)} -Encoding UTF8; "
            f"Get-Content -LiteralPath {_psq(str(ai_path))} -Raw"
        )
        msg=(
            "Use exactly ONE real shell tool call. This is a Windows PowerShell 5.1 compatibility boundary test.\n"
            "Your shell tool arguments.cmd must perform only this simple proof operation: write the supplied marker to the supplied file and read it back.\n"
            "Use this exact PowerShell 5.1 command:\n"
            f"{exact_cmd}\n"
            "Use Set-Content and Get-Content only. Do not use &&, ||, .NET constructors, UTF8Encoding, variables, or additional commands. "
            "Do not merely print PowerShell. Do not claim PASS; DMT will verify the real terminal result independently."
        )
        result=run_chat(pid,msg,'ollama',probe_model,'T1-'+uuid.uuid4().hex,single_tool=True)
        execution=result.get('execution',{})
        events=list(execution.get('tool_events') or [])
        if not execution.get('proven'): raise RuntimeError('AI_TERMINAL_EXECUTION_NOT_PROVEN')
        if len(events) != 1: raise RuntimeError('AI_TERMINAL_EXPECTED_ONE_TOOL_EVENT')
        terminal_result=(events[0].get('result') or {})
        if not execution.get('succeeded'):
            diag={
                'job_id':terminal_result.get('job_id'),
                'exit_code':terminal_result.get('exit_code'),
                'stdout':str(terminal_result.get('stdout') or '')[-500:],
                'stderr':str(terminal_result.get('stderr') or '')[-500:],
                'reason':terminal_result.get('reason'),
            }
            raise RuntimeError('AI_TERMINAL_EXECUTION_FAILED '+json.dumps(diag,ensure_ascii=True))
        if str(terminal_result.get('stdout') or '').strip() != ai_value:
            raise RuntimeError('AI_TERMINAL_STDOUT_MISMATCH')
        if not ai_path.is_file(): raise RuntimeError('AI_PROOF_FILE_MISSING')
        value=ai_path.read_text(encoding='utf-8-sig').strip()
        if value != ai_value: raise RuntimeError('AI_PROOF_READBACK_MISMATCH')
        return {
            "request_id":result.get('request_id'),
            "model":probe_model,
            "readback":value,
            "stdout":str(terminal_result.get('stdout') or '').strip(),
            "sha256":_sha(ai_path),
            "job_id":terminal_result.get('job_id'),
            "exit_code":terminal_result.get('exit_code'),
            "tool_events":len(events),
            "execution_mode":execution.get('mode'),
        }
    def ai_probe_with_retry():
        errors=[]
        installed=set(models or []) if isinstance(models,list) else set()
        strong='qwen2.5-coder:7b'
        sequence=[model]
        if strong in installed and strong != model:
            sequence.extend([strong,strong])
        else:
            sequence.extend([model,model])
        for attempt,probe_model in enumerate(sequence,1):
            try:
                value=ai_probe(probe_model)
                value["attempts"]=attempt
                value["escalated"]=(probe_model != model)
                return value
            except Exception as exc:
                errors.append({"attempt":attempt,"model":probe_model,"error":str(exc)})
                if attempt < len(sequence):
                    time.sleep(0.75)
        raise RuntimeError("AI_TERMINAL_RETRIES_EXHAUSTED "+json.dumps(errors,ensure_ascii=True))
    _check(checks,"real_ai_to_terminal",ai_probe_with_retry)

    proof=root/'proof.txt'
    def create_read():
        cmd=f"Set-Content -LiteralPath {_psq(str(proof))} -Value 'DMT_TEMPLATE1_INITIAL' -Encoding UTF8; Get-Content -LiteralPath {_psq(str(proof))} -Raw"
        r=run_powershell(cmd,pid)
        if not r.get('executed') or r.get('exit_code')!=0 or r.get('stdout','').strip()!='DMT_TEMPLATE1_INITIAL': raise RuntimeError('CREATE_READBACK_FAILED')
        return {"job_id":r.get('job_id'),"readback":r.get('stdout','').strip()}
    _check(checks,"file_create_readback",create_read)

    def update_read():
        cmd=f"Set-Content -LiteralPath {_psq(str(proof))} -Value 'DMT_TEMPLATE1_UPDATED' -Encoding UTF8; Get-Content -LiteralPath {_psq(str(proof))} -Raw"
        r=run_powershell(cmd,pid)
        if not r.get('executed') or r.get('exit_code')!=0 or r.get('stdout','').strip()!='DMT_TEMPLATE1_UPDATED': raise RuntimeError('UPDATE_READBACK_FAILED')
        return {"job_id":r.get('job_id'),"readback":r.get('stdout','').strip(),"sha256":_sha(proof)}
    _check(checks,"file_update_readback_hash",update_read)

    missing=root/'deliberately-missing.txt'
    def expected_fail():
        if missing.exists(): missing.unlink()
        r=run_powershell(f"Get-Content -LiteralPath {_psq(str(missing))} -Raw -ErrorAction Stop",pid)
        if not r.get('executed') or r.get('exit_code')==0: raise RuntimeError('EXPECTED_FAILURE_NOT_OBSERVED')
        return {"job_id":r.get('job_id'),"exit_code":r.get('exit_code'),"truthful_failure":True}
    _check(checks,"expected_error_handling",expected_fail)

    def safety():
        protected=analyze_command('bcdedit /enum'); source=analyze_command('Set-Content app.py x')
        if protected.allowed or source.allowed: raise RuntimeError('SAFETY_POLICY_FAILED')
        return {"protected_reason":protected.reason,"source_reason":source.reason}
    _check(checks,"safety_blocks",safety)

    _check(checks,"terminal_history",lambda: _require(len(db.terminal_history())>=4,'TERMINAL_HISTORY_TOO_SHORT') or {"count":len(db.terminal_history())})
    _check(checks,"final_database_integrity",lambda: _require(db.status().get('ok') is True,'DB_FINAL_CHECK_FAILED') or db.status())

    failed=[x for x in checks if x['status']=='FAIL']
    result={"ok":not failed,"overall":"PASS" if not failed else "FAIL","template_id":"system-stress","template_number":1,"template_name":"System Stress Test + Fault Finder","build":BUILD,"model":model,"workspace":str(root),"checks":checks,"passed":len(checks)-len(failed),"total":len(checks),"failed":[x['name'] for x in failed],"duration_seconds":round(time.monotonic()-started,3)}
    rp=_report('template-1-system-stress',result); result['report']=str(rp); result['report_sha256']=_sha(rp)
    return result


def _require(condition: bool, message: str) -> None:
    if not condition: raise RuntimeError(message)


def run_template_2(model: str=PREFERRED_MODEL, launch: bool=True) -> dict[str, Any]:
    started=time.monotonic(); checks=[]
    root=WORKFLOW_ROOT / "template-2-snake-game"; root.mkdir(parents=True,exist_ok=True)
    project=_project("Template 2 - Snake Game")
    pid=int(project['id']); game=root/'snake.html'

    encoded=base64.b64encode(SNAKE_HTML.encode('utf-8')).decode('ascii')
    def build_file():
        cmd=f"[IO.File]::WriteAllBytes({_psq(str(game))},[Convert]::FromBase64String('{encoded}')); Write-Output 'DMT_SNAKE_BUILD_OK'"
        if len(cmd)>5900: raise RuntimeError(f'SNAKE_BUILD_COMMAND_TOO_LONG={len(cmd)}')
        r=run_powershell(cmd,pid)
        if not r.get('executed') or r.get('exit_code')!=0 or 'DMT_SNAKE_BUILD_OK' not in r.get('stdout',''): raise RuntimeError('SNAKE_BUILD_TERMINAL_FAILED')
        return {"job_id":r.get('job_id'),"command_chars":len(cmd),"bytes":game.stat().st_size if game.exists() else 0}
    _check(checks,"build_snake_via_terminal",build_file)

    def readback():
        r=run_powershell(f"Get-Content -LiteralPath {_psq(str(game))} -Raw",pid)
        if not r.get('executed') or r.get('exit_code')!=0: raise RuntimeError('SNAKE_READBACK_COMMAND_FAILED')
        actual=game.read_text(encoding='utf-8-sig') if game.is_file() else ''
        if actual != SNAKE_HTML: raise RuntimeError('SNAKE_EXACT_READBACK_MISMATCH')
        return {"job_id":r.get('job_id'),"sha256":_sha(game),"bytes":len(actual.encode('utf-8'))}
    _check(checks,"independent_readback",readback)

    def features():
        text=game.read_text(encoding='utf-8-sig')
        required={
            'self_contained': '<canvas' in text and '<script>' in text and 'http://' not in text and 'https://' not in text,
            'arrow_wasd': all(x in text for x in ['arrowup','arrowdown','arrowleft','arrowright',"k==='w'","k==='a'","k==='s'","k==='d'"]),
            'no_reverse': 'nx===-dir.x&&ny===-dir.y' in text,
            'score_growth_food': all(x in text for x in ['score++','spawn()','snake.unshift']),
            'wall_self_collision': 'h.x<0||h.y<0||h.x>=N||h.y>=N||snake.some' in text,
            'restart': "k==='r'" in text and 'restart' in text,
            'pause': "k===' '||k==='p'" in text,
            'best_localstorage': "localStorage.setItem('dmt-snake-best'" in text,
            'responsive': 'width:min(94vw,620px)' in text and 'width:100%' in text,
        }
        bad=[k for k,v in required.items() if not v]
        if bad: raise RuntimeError('SNAKE_FEATURES_MISSING='+','.join(bad))
        return required
    _check(checks,"snake_feature_validation",features)

    _check(checks,"snake_sha256",lambda: {"sha256":_sha(game),"path":str(game)})

    if launch:
        def launch_game():
            r=run_powershell(f"Start-Process -FilePath {_psq(str(game))}; Write-Output 'DMT_SNAKE_LAUNCH_REQUESTED'",pid)
            if not r.get('executed') or r.get('exit_code')!=0: raise RuntimeError('SNAKE_LAUNCH_FAILED')
            return {"job_id":r.get('job_id'),"launch_requested":True}
        _check(checks,"launch_snake",launch_game)
    else:
        checks.append({"name":"launch_snake","status":"PASS","duration_seconds":0,"detail":{"launch_requested":False,"test_mode":True}})

    _check(checks,"final_database_integrity",lambda: _require(db.status().get('ok') is True,'DB_FINAL_CHECK_FAILED') or db.status())
    failed=[x for x in checks if x['status']=='FAIL']
    result={"ok":not failed,"overall":"PASS" if not failed else "FAIL","template_id":"snake-game","template_number":2,"template_name":"Snake Game - Build, Verify + Run","build":BUILD,"model":model,"workspace":str(root),"snake_file":str(game),"snake_sha256":_sha(game) if game.is_file() else '',"checks":checks,"passed":len(checks)-len(failed),"total":len(checks),"failed":[x['name'] for x in failed],"duration_seconds":round(time.monotonic()-started,3)}
    rp=_report('template-2-snake-game',result); result['report']=str(rp); result['report_sha256']=_sha(rp)
    return result


def run_template(template_id: str, model: str=PREFERRED_MODEL, launch: bool=True) -> dict[str, Any]:
    template_id=str(template_id or '').strip().lower()
    if template_id in {'1','system-stress','stress'}: return run_template_1(model)
    if template_id in {'2','snake-game','snake'}: return run_template_2(model,launch=launch)
    raise ValueError('TEMPLATE_NOT_FOUND')
