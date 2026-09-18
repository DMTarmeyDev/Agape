from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agape_studio import BUILD
from agape_studio.quality import quality_from_results

TEMPLATES = ROOT / 'tests' / 'templates'
spec = importlib.util.spec_from_file_location('agape_live_cases', ROOT / 'tests' / 'live_cases.py')
live_cases = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(live_cases)


def gate(name: str, status: str, detail: str = '') -> None:
    suffix = f' | {detail}' if detail else ''
    print(f'GATE::{name}={status}{suffix}', flush=True)


def run_unit_tests() -> dict:
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-p', 'test_*.py', '-q'],
        cwd=ROOT, capture_output=True, text=True,
    )
    duration = time.perf_counter() - start
    detail = (proc.stdout + '\n' + proc.stderr).strip()
    status = 'PASS' if proc.returncode == 0 else 'FAIL'
    gate('COMPONENTS', status, f'exit={proc.returncode} duration={duration:.2f}s')
    if status == 'FAIL' and detail:
        print(detail)
    return {'name': 'Python component unit tests', 'status': status, 'required': True, 'duration': duration, 'detail': detail}


def run_templates() -> list[dict]:
    results=[]
    runner = ROOT / 'scripts' / 'run_live_case.py'
    external_timeouts = {
        'real_ollama_probe': 150,
        'real_openrouter_catalog_optional': 30,
        'real_aider_probe': 30,
    }
    for path in sorted(TEMPLATES.glob('*.json')):
        template=json.loads(path.read_text(encoding='utf-8'))
        required=bool(template.get('required', True))
        template_results=[]
        for case_name in template.get('cases', []):
            start=time.perf_counter()
            try:
                if case_name in external_timeouts:
                    timeout=external_timeouts[case_name]
                    proc=subprocess.run(
                        [sys.executable, str(runner), case_name],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    payload=None
                    for line in reversed(proc.stdout.splitlines()):
                        if line.startswith('RESULT_JSON='):
                            payload=json.loads(line[len('RESULT_JSON='):])
                            break
                    if not payload:
                        status='FAIL'
                        detail='LIVE_CASE_RESULT_MISSING'
                    else:
                        status=str(payload.get('status') or 'FAIL')
                        detail=str(payload.get('detail') or '')
                        if proc.returncode != 0 and status != 'FAIL':
                            status='FAIL'
                            detail=('LIVE_CASE_EXIT=' + str(proc.returncode) + '\n' + detail).strip()
                else:
                    fn=live_cases.CASES[case_name]
                    outcome=fn()
                    if isinstance(outcome, tuple):
                        status, detail=outcome
                    else:
                        status, detail='PASS', str(outcome)
            except subprocess.TimeoutExpired:
                status='FAIL'
                detail=f'EXTERNAL_PROBE_TIMEOUT={external_timeouts.get(case_name, 0)}s'
            except Exception:
                status='FAIL';detail=traceback.format_exc().strip()
            duration=time.perf_counter()-start
            item={'template':template['name'],'template_file':path.name,'name':case_name,'status':status,'required':required,'duration':duration,'detail':detail}
            results.append(item);template_results.append(item)
        failed=[x for x in template_results if x['status']=='FAIL']
        required_bad=[x for x in template_results if required and x['status']!='PASS']
        skipped=[x for x in template_results if x['status']=='SKIP']
        status='FAIL' if failed or required_bad else ('SKIP' if template_results and len(skipped)==len(template_results) else 'PASS')
        gate(template['name'].upper().replace(' ','_'), status, f"cases={len(template_results)} failures={len(failed)} skips={len(skipped)}")
        if failed:
            for item in failed: print(f"FAIL::{item['name']} | {item['detail'][-2000:]}")
    return results


def markdown_report(started: str, ended: str, unit: dict, live: list[dict], quality: list[dict], overall: str, packaged: bool) -> str:
    lines=[
        '# Agape AI Studio V0.3 R2 - Full Test Report', '',
        f'- **Build:** `{BUILD}`',
        f'- **Started (UTC):** {started}',
        f'- **Finished (UTC):** {ended}',
        f'- **Python:** `{sys.version.split()[0]}`',
        f'- **Platform:** `{sys.platform}`',
        f'- **Packaged-source verification:** {"Yes" if packaged else "No"}',
        f'- **Overall:** **{overall}**', '',
        '## Gate Summary', '',
        '| Gate | Required | Status |', '|---|---:|---:|',
        f"| Component tests | Yes | **{unit['status']}** |",
    ]
    seen=[]
    for item in live:
        key=(item['template'],item['required'])
        if key in seen: continue
        seen.append(key)
        group=[x for x in live if x['template']==item['template']]
        bad=[x for x in group if x['status']=='FAIL' or (item['required'] and x['status']!='PASS')]
        all_skip=group and all(x['status']=='SKIP' for x in group)
        status='FAIL' if bad else ('SKIP' if all_skip else 'PASS')
        lines.append(f"| {item['template']} | {'Yes' if item['required'] else 'No'} | **{status}** |")

    passed=[x for x in quality if x['status']=='PASS']
    open_items=[x for x in quality if x['status']!='PASS']
    lines += ['', '## Passed', '',
              'Every row here is a completed project part backed by test evidence.', '',
              '| ID | Area | Part | Status | Evidence |', '|---|---|---|---:|---|']
    for item in passed:
        lines.append(f"| `{item['id']}` | {item['area']} | {item['title']} | **PASS** | {item.get('detail','')} |")
    if not passed:
        lines.append('| - | - | Nothing published as passed | - | - |')

    lines += ['', '## Open Issues / Not Yet Passed', '',
              '| ID | Area | Part | Status | Evidence / next action |', '|---|---|---|---:|---|']
    if open_items:
        for item in open_items:
            lines.append(f"| `{item['id']}` | {item['area']} | {item['title']} | **{item['status']}** | {item.get('detail') or 'Awaiting a complete verified gate.'} |")
    else:
        lines.append('| - | - | None | **PASS** | All defined V0.3 items are closed. |')

    lines += ['', '## Detailed Test Evidence', '',
              '### Component suite', '', '```text', unit['detail'][-12000:] or '(quiet PASS)', '```', '']
    for item in live:
        lines += [f"### {item['template']} / `{item['name']}`", '', f"**Status:** {item['status']}", '', '```text', item['detail'][-8000:] or '(no detail)', '```', '']

    failures=[x for x in [unit] + live if x['status']=='FAIL' and x.get('required', True)]
    lines += ['## AI Repair Queue', '',
              'The AI should work only on these open failures, then rerun the narrow gate and finally the full process.', '',
              '| Priority | Test | Status | Action |', '|---:|---|---|---|']
    if failures:
        for i,item in enumerate(failures,1):
            lines.append(f"| {i} | `{item['name']}` | **FAIL** | Diagnose the evidence above, repair the responsible component, run its targeted tests, then rerun the full suite. |")
    else:
        lines.append('| 1 | Required suite | **PASS** | No required repair remains. |')

    lines += ['', '## Final Markers', '', '```text',
              f'QUALITY_ITEMS={len(quality)}',
              f'QUALITY_PASSED={len(passed)}',
              f'QUALITY_OPEN={len(open_items)}',
              f'REQUIRED_FAILURES={len(failures)}',
              f'OPTIONAL_SKIPS={sum(1 for x in live if not x["required"] and x["status"]=="SKIP")}',
              f'AGAPE_V0_3_FULL_TEST_PROCESS={overall}', '```', '']
    return '\n'.join(lines)


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--report-root', default=str(ROOT/'test-reports'))
    ap.add_argument('--packaged', action='store_true')
    args=ap.parse_args()
    reports=Path(args.report_root);reports.mkdir(parents=True,exist_ok=True)
    started=datetime.now(timezone.utc).isoformat()
    print('AGAPE AI STUDIO V0.3 R2 - VERIFIED TEST PROCESS')
    unit=run_unit_tests()
    live=run_templates()
    failures=[]
    if unit['status']!='PASS': failures.append(unit)
    failures.extend(x for x in live if x['required'] and x['status']!='PASS')
    overall='PASS' if not failures else 'FAIL'
    quality=quality_from_results(unit['status'],live,packaged=args.packaged)
    ended=datetime.now(timezone.utc).isoformat()
    report=markdown_report(started,ended,unit,live,quality,overall,args.packaged)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report_path=reports/f'AGAPE-V0.3-FULL-TEST-REPORT-{stamp}.md'
    latest=reports/'AGAPE-V0.3-FULL-TEST-REPORT-LATEST.md'
    quality_path=reports/'AGAPE-QUALITY-STATUS-LATEST.json'
    report_path.write_text(report,encoding='utf-8');latest.write_text(report,encoding='utf-8')
    quality_path.write_text(json.dumps({'build':BUILD,'overall':overall,'items':quality},indent=2),encoding='utf-8')
    print('REPORT=' + str(report_path))
    print('QUALITY=' + str(quality_path))
    gate('FULL_RELEASE',overall,f'required_failures={len(failures)} passed={sum(1 for x in quality if x["status"]=="PASS")}/{len(quality)}')
    return 0 if overall=='PASS' else 1

if __name__=='__main__':
    raise SystemExit(main())
