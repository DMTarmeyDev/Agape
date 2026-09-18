from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,time,traceback,shutil
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASELINE=ROOT/'test-state'/'baseline-hashes.json'
REPORTS=ROOT/'test-reports'
REPORTS.mkdir(exist_ok=True)

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def changed_files(explicit:list[str])->list[str]:
    if explicit:return sorted(set(explicit))
    if not BASELINE.exists():return ['__FULL_REQUIRED__']
    old=json.loads(BASELINE.read_text(encoding='utf-8')).get('files',{})
    current={}
    for p in ROOT.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(ROOT).as_posix()
        if any(x in p.relative_to(ROOT).parts for x in ('test-reports','test-state','__pycache__')):continue
        if rel=='manifest.json':continue
        current[rel]=sha(p)
    return sorted({k for k in set(old)|set(current) if old.get(k)!=current.get(k)})

def run(cmd:list[str],label:str)->tuple[bool,str]:
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
    out=(p.stdout+'\n'+p.stderr).strip()
    print(f'PATCH_GATE::{label}={"PASS" if p.returncode==0 else "FAIL"}')
    if p.returncode!=0 and out:print(out[-4000:])
    return p.returncode==0,out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--files',nargs='*',default=[]);args=ap.parse_args()
    changed=changed_files(args.files)
    if not changed:
        print('PATCH_GATE::NO_CHANGES=PASS');return 0
    if '__FULL_REQUIRED__' in changed:
        print('PATCH_GATE::BASELINE_MISSING=FULL_TEST_REQUIRED')
        p=subprocess.run([sys.executable,str(ROOT/'scripts'/'run_full_test_process.py')],cwd=ROOT)
        return p.returncode
    units=set();live=set();full=False;notes=[]
    for rel in changed:
        if rel.endswith('.py'):
            ok,_=run([sys.executable,'-m','py_compile',rel],f'COMPILE:{rel}')
            if not ok:return 1
        if rel.startswith(('agape_studio/providers.py','agape_studio/ai.py','agape_studio/connections.py')):
            units.update(['tests.test_free_ai','tests.test_ai']);live.update(['free_ai_discovery_journey','free_ai_auto_selection_journey','free_ai_provider_test_persistence','local_to_free_fallback_journey'])
        elif rel.startswith(('agape_studio/aider_tool.py','agape_studio/planning.py')):
            units.update(['tests.test_aider','tests.test_ai']);live.update(['aider_status_planning_journey','aider_execution_journey','aider_optional_fallback_journey','aider_ui_contract'])
        elif rel.startswith(('agape_studio/database.py','agape_studio/quality.py')):
            units.update(['tests.test_database','tests.test_quality']);live.update(['quality_ledger_journey','persistence_restart'])
        elif rel.startswith('agape_studio/projects.py'):
            units.add('tests.test_projects');live.update(['project_file_journey','path_security','persistence_restart'])
        elif rel.startswith('agape_studio/terminal.py'):
            units.add('tests.test_terminal');live.add('terminal_journey')
        elif rel.startswith('agape_studio/extensions.py') or rel.startswith('extensions/'):
            units.add('tests.test_extensions');live.add('extension_journey')
        elif rel.startswith('ui/'):
            live.update(['home_ui_contract','passed_menu_contract','aider_ui_contract'])
            if rel=='ui/app.js' and shutil.which('node'):
                ok,_=run(['node','--check','ui/app.js'],'JAVASCRIPT_SYNTAX')
                if not ok:return 1
        elif rel.startswith(('agape_studio/api.py','agape_studio/context.py','agape_studio/config.py','agape_studio/server.py')):
            full=True
        elif rel.startswith(('tests/','scripts/','RUN-ALL-TESTS','START-STUDIO','INSTALL-TEST-REPORT','INSTALL-AIDER')):
            full=True
        else:
            notes.append(rel)
    started=datetime.now(timezone.utc).isoformat();details=[];ok=True
    if full:
        proc=subprocess.run([sys.executable,str(ROOT/'scripts'/'run_full_test_process.py')],cwd=ROOT,capture_output=True,text=True)
        ok=proc.returncode==0;details.append(proc.stdout+'\n'+proc.stderr);print(f'PATCH_GATE::FULL_INTEGRATION={"PASS" if ok else "FAIL"}')
    else:
        if units:
            passed,out=run([sys.executable,'-m','unittest',*sorted(units),'-q'],'TARGETED_COMPONENTS');ok &= passed;details.append(out)
        if ok and live:
            code='from tests import live_cases\n' + '\n'.join([f"print({n!r}, live_cases.CASES[{n!r}]())" for n in sorted(live)])
            passed,out=run([sys.executable,'-c',code],'TARGETED_LIVE');ok &= passed;details.append(out)
    report=['# Agape AI Studio - Patch Test Report','',f'- **Started:** {started}',f'- **Result:** **{"PASS" if ok else "FAIL"}**','','## Changed files','']
    report += [f'- `{x}`' for x in changed]
    report += ['','## Test scope','',f'- Full integration required: **{full}**',f'- Unit modules: `{", ".join(sorted(units)) or "none"}`',f'- Live cases: `{", ".join(sorted(live)) or "none"}`','','## Evidence','','```text','\n\n'.join(details)[-12000:] or '(no output)','```','', '## Next step','']
    report.append('Run `RUN-ALL-TESTS.ps1` before promotion/package.' if ok else 'Repair the failure above and rerun this patch gate before any wider testing.')
    (REPORTS/'AGAPE-PATCH-TEST-REPORT-LATEST.md').write_text('\n'.join(report),encoding='utf-8')
    print('PATCH_REPORT=' + str(REPORTS/'AGAPE-PATCH-TEST-REPORT-LATEST.md'))
    return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
