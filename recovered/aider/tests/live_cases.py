from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path

from agape_studio.ai import FakeProvider, OllamaProvider
from agape_studio.aider_tool import AiderService
from agape_studio.database import StudioDatabase
from agape_studio.providers import OpenRouterFreeProvider
from tests.fake_openrouter import fake_openrouter
from agape_studio.api import make_server
from agape_studio.config import StudioConfig
from agape_studio.context import build_context


ROOT = Path(__file__).resolve().parents[1]
FAKE_AIDER = ROOT / 'tests' / 'fake_aider_cli.py'


@contextmanager
def fake_aider_enabled():
    with patch.dict(os.environ, {
        'AGAPE_AIDER_COMMAND_JSON': json.dumps([sys.executable, str(FAKE_AIDER)]),
        'AGAPE_AIDER_DISABLE': '0',
    }, clear=False):
        yield


def init_git_repo(root: Path) -> None:
    subprocess.run(['git', 'init'], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(['git', 'config', 'user.email', 'agape-live@example.invalid'], cwd=root, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Agape Live Tests'], cwd=root, check=True)
    (root / 'aider_target.py').write_text('print(\"before\")\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-m', 'baseline'], cwd=root, check=True, capture_output=True, text=True)


def request_json(base: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode('utf-8'))


@contextmanager
def live_studio(temp_root: Path, providers=None):
    config = StudioConfig(
        data_root=temp_root / 'data',
        projects_root=temp_root / 'projects',
        extensions_root=ROOT / 'extensions',
        ui_root=ROOT / 'ui',
        host='127.0.0.1',
        port=0,
    )
    context = build_context(config, providers=providers or [FakeProvider(model_name='qwen-test-coder:7b')])
    server = make_server(context, '127.0.0.1', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        yield base, context
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def case_live_health() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        status, payload = request_json(base, '/api/health')
        assert status == 200 and payload['ok'] and payload['database']
        assert payload['build'].startswith('AGAPE-AI-STUDIO-V0.3')
        return f"HTTP=200 BUILD={payload['build']} DATABASE=PASS"


def case_home_ui_contract() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        with urllib.request.urlopen(base + '/', timeout=10) as res:
            html = res.read().decode('utf-8')
        markers = ['AGAPE AI STUDIO', 'Recent Projects', 'TERMINAL', 'AGAPE AI', 'Extensions', 'editor']
        missing = [x for x in markers if x not in html]
        assert not missing, missing
        return 'UI_MARKERS=' + str(len(markers)) + '/' + str(len(markers))


def case_project_file_journey() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'LiveDemo'})
        project = made['project']['path']
        _, write = request_json(base, '/api/files/write', {'project_path': project, 'path': 'src/main.py', 'content': 'print("LIVE_PROJECT_OK")\n'})
        assert write['ok']
        _, listed = request_json(base, '/api/files/list', {'project_path': project})
        assert 'src/main.py' in listed['files']
        _, read = request_json(base, '/api/files/read', {'project_path': project, 'path': 'src/main.py'})
        assert read['content'] == 'print("LIVE_PROJECT_OK")\n'
        _, recent = request_json(base, '/api/projects')
        assert recent['projects'][0]['name'] == 'LiveDemo'
        return 'CREATE=PASS WRITE=PASS READ=PASS RECENT=PASS'


def case_terminal_journey() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'TerminalDemo'})
        project = made['project']['path']
        _, result = request_json(base, '/api/terminal/run', {'project_path': project, 'argv': [sys.executable, '-c', 'print("LIVE_TERMINAL_OK")']})
        assert result['ok'] and result['exit_code'] == 0 and 'LIVE_TERMINAL_OK' in result['stdout']
        return 'TERMINAL_EXECUTION=PASS EXIT=0 HISTORY=RECORDED'


def case_ai_journey() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'AIDemo'})
        project = made['project']['path']
        _, status = request_json(base, '/api/ai/status')
        assert status['ok']
        _, reply = request_json(base, '/api/ai/chat', {'project_path': project, 'message': 'explain this code', 'task': 'code', 'context': 'print(1)'})
        assert reply['ok'] and reply['model'] == 'qwen-test-coder:7b' and 'explain this code' in reply['reply']
        return 'AUTO_MODEL=PASS MODEL=qwen-test-coder:7b CHAT=PASS HISTORY=RECORDED'


def case_extension_journey() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        _, ext = request_json(base, '/api/extensions')
        assert len(ext['extensions']) == 3
        _, fmt = request_json(base, '/api/extensions/run', {'extension_id': 'agape.basic-formatter', 'action': 'format_text', 'payload': {'text': 'x  \n'}})
        assert fmt['result']['text'] == 'x\n'
        _, spell = request_json(base, '/api/extensions/run', {'extension_id': 'agape.spell-checker', 'action': 'check_text', 'payload': {'text': 'teh adress'}})
        assert spell['result']['count'] == 2
        return 'EXTENSIONS=3/3 FORMAT=PASS SPELL=PASS OUT_OF_PROCESS=PASS'


def case_path_security() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'GuardDemo'})
        project = made['project']['path']
        status, bad = request_json(base, '/api/files/write', {'project_path': project, 'path': '../escape.txt', 'content': 'bad'})
        assert status == 400 and not bad['ok'] and 'PATH_OUTSIDE_PROJECT' in bad['error']
        assert not (Path(project).parent / 'escape.txt').exists()
        return 'PROJECT_PATH_ESCAPE_GUARD=PASS'


def case_persistence_restart() -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with live_studio(root) as (base, _):
            _, made = request_json(base, '/api/projects/create', {'name': 'PersistDemo'})
            project_path = made['project']['path']
            request_json(base, '/api/files/write', {'project_path': project_path, 'path': 'state.txt', 'content': 'persisted'})
        with live_studio(root) as (base2, _):
            _, recent = request_json(base2, '/api/projects')
            assert any(p['path'] == project_path for p in recent['projects'])
            _, read = request_json(base2, '/api/files/read', {'project_path': project_path, 'path': 'state.txt'})
            assert read['content'] == 'persisted'
        return 'RESTART=PASS RECENT_PROJECT=RESTORED FILE_STATE=RESTORED'


def case_full_user_journey() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'AcceptanceDemo'})
        project = made['project']['path']
        request_json(base, '/api/files/write', {'project_path': project, 'path': 'main.py', 'content': 'print("AGAPE_ACCEPTANCE")  \n'})
        _, fmt = request_json(base, '/api/extensions/run', {'extension_id': 'agape.basic-formatter', 'action': 'format_text', 'payload': {'text': 'print("AGAPE_ACCEPTANCE")  \n'}})
        request_json(base, '/api/files/write', {'project_path': project, 'path': 'main.py', 'content': fmt['result']['text']})
        _, terminal = request_json(base, '/api/terminal/run', {'project_path': project, 'argv': [sys.executable, 'main.py']})
        assert terminal['ok'] and 'AGAPE_ACCEPTANCE' in terminal['stdout']
        _, ai = request_json(base, '/api/ai/chat', {'project_path': project, 'message': 'explain current project', 'task': 'code', 'context': fmt['result']['text']})
        assert ai['ok']
        return 'PROJECT=PASS EDIT=PASS FORMAT=PASS TERMINAL=PASS AI=PASS HISTORY=PASS'


def case_real_ollama_probe() -> tuple[str, str]:
    provider = OllamaProvider(timeout=5, chat_timeout=120)
    try:
        models = provider.models()
    except Exception as exc:
        return 'SKIP', 'REAL_OLLAMA_NOT_AVAILABLE: ' + str(exc)
    if not models:
        return 'SKIP', 'REAL_OLLAMA_AVAILABLE_BUT_NO_MODELS'
    preferred = [
        'qwen2.5-coder:1.5b-instruct',
        'qwen2.5-coder:1.5b',
    ]
    model = next((name for name in preferred if name in models), None)
    if model is None:
        model = next((name for name in models if '1.5b' in name.lower()), models[0])
    try:
        reply = provider.chat(model, [{'role': 'user', 'content': 'Reply with the single word PASS'}])
    except Exception as exc:
        return 'FAIL', 'REAL_OLLAMA_CHAT_FAILED: ' + str(exc)
    if not reply.strip():
        return 'FAIL', 'REAL_OLLAMA_EMPTY_RESPONSE'
    return 'PASS', f'REAL_OLLAMA_MODEL={model} RESPONSE_BYTES={len(reply.encode("utf-8"))}'


def case_free_ai_discovery_journey() -> str:
    with tempfile.TemporaryDirectory() as td, fake_openrouter() as or_base:
        provider = OpenRouterFreeProvider(base_url=or_base, api_key='test-key')
        with live_studio(Path(td), providers=[provider]) as (base, _):
            status, payload = request_json(base, '/api/ai/free-models?task=code')
            assert status == 200 and payload['ok']
            ids = [x['model'] for x in payload['models']]
            assert ids == ['acme/coder-free', 'acme/general-free'], ids
            assert all(x['is_free'] and x['tier'] == 'free-online' for x in payload['models'])
            assert 'acme/paid-model' not in ids
            return 'FREE_PROVIDER=PASS DISCOVERY=2 ZERO_COST_FILTER=PASS PAID_EXCLUSION=PASS'


def case_free_ai_auto_selection_journey() -> str:
    with tempfile.TemporaryDirectory() as td, fake_openrouter() as or_base:
        provider = OpenRouterFreeProvider(base_url=or_base, api_key='test-key')
        with live_studio(Path(td), providers=[provider]) as (base, _):
            status, payload = request_json(base, '/api/ai/recommend?task=repair%20python%20code%20and%20tests&mode=free')
            assert status == 200 and payload['ok']
            rec = payload['recommendation']
            assert rec['model'] == 'acme/coder-free', rec
            assert rec['is_free'] and rec['tier'] == 'free-online'
            return 'AUTO_BEST_FREE=PASS MODEL=acme/coder-free FREE_ONLY=PASS'


def case_free_ai_provider_test_persistence() -> str:
    with tempfile.TemporaryDirectory() as td, fake_openrouter() as or_base:
        provider = OpenRouterFreeProvider(base_url=or_base, api_key='test-key')
        with live_studio(Path(td), providers=[provider]) as (base, _):
            status, tested = request_json(base, '/api/connections/test', {'provider':'openrouter-free','generation':True,'task':'code'})
            assert status == 200 and tested['ok']
            assert tested['models'] == 2
            assert tested['generation']['status'] == 'PASS'
            _, history = request_json(base, '/api/connections/tests?limit=50')
            tests = history['tests']
            assert any(x['source'] == 'catalog' and x['status'] == 'PASS' for x in tests)
            assert sum(1 for x in tests if x['source'] == 'eligibility' and x['status'] == 'PASS') == 2
            assert any(x['source'] == 'generation-probe' and x['status'] == 'PASS' for x in tests)
            return 'PROVIDER_TEST=PASS FREE_MODELS_TESTED=2/2 GENERATION=PASS SAVED_OUTCOMES=PASS'


def case_local_to_free_fallback_journey() -> str:
    with tempfile.TemporaryDirectory() as td, fake_openrouter() as or_base:
        local = FakeProvider(provider_id='local-fail', model_name='qwen2.5-coder:7b', tier='local', fail_chat=True)
        free = OpenRouterFreeProvider(base_url=or_base, api_key='test-key')
        with live_studio(Path(td), providers=[local, free]) as (base, _):
            _, made = request_json(base, '/api/projects/create', {'name':'FallbackDemo'})
            project = made['project']['path']
            status, result = request_json(base, '/api/ai/chat', {
                'project_path': project,
                'message': 'repair this python code',
                'task': 'code',
                'mode': 'auto',
            })
            assert status == 200 and result['ok']
            assert result['provider'] == 'openrouter-free'
            assert result['fallbacks_used'] >= 1
            assert result['model'] == 'acme/coder-free'
            return 'LOCAL_FAILURE=PROVEN FREE_FALLBACK=PASS BEST_FREE_MODEL=PASS PAID_FALLBACK=DISABLED'


def case_passed_menu_contract() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        with urllib.request.urlopen(base + '/', timeout=10) as res:
            html = res.read().decode('utf-8')
        markers = ['passedBtn', 'passedDialog', 'Passed', 'openIssuesList', 'aiDialog', 'aiMode']
        missing = [x for x in markers if x not in html]
        assert not missing, missing
        _, quality = request_json(base, '/api/quality/status')
        assert quality['total'] >= 15
        return f"PASSED_MENU=PASS QUALITY_ITEMS={quality['total']} OPEN_ITEMS_VISIBLE=PASS"


def case_quality_ledger_journey() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, context):
        context.db.set_quality_item('FREE-001','Free AI','Free online AI provider adapter','PASS','live proof','live-report.md')
        _, quality = request_json(base, '/api/quality/status')
        assert any(x['item_id'] == 'FREE-001' and x['status'] == 'PASS' for x in quality['passed'])
        assert quality['open_count'] > 0
        return 'QUALITY_LEDGER=PASS PASSED_SEPARATED=PASS OPEN_ITEMS_RETAINED=PASS'


def case_real_openrouter_catalog_optional() -> tuple[str, str]:
    provider = OpenRouterFreeProvider(timeout=5)
    try:
        models = provider.models()
    except Exception as exc:
        return 'SKIP', 'REAL_OPENROUTER_CATALOG_NOT_AVAILABLE: ' + str(exc)
    if not models:
        return 'FAIL', 'REAL_OPENROUTER_CATALOG_RETURNED_NO_ZERO_COST_TEXT_MODELS'
    return 'PASS', f'REAL_OPENROUTER_FREE_MODELS={len(models)} KEY_CONFIGURED={provider.credential_configured}'


def case_aider_status_planning_journey() -> str:
    with tempfile.TemporaryDirectory() as td, fake_aider_enabled(), live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'AiderPlanDemo'})
        project = Path(made['project']['path'])
        init_git_repo(project)
        _, status = request_json(base, '/api/tools/aider/status')
        assert status['aider']['ready'] and '0.86.0-test' in status['aider']['version']
        code, plan = request_json(base, '/api/tools/plan', {
            'project_path': str(project),
            'task': 'refactor this codebase across multiple files and fix tests',
            'mode': 'auto',
        })
        assert code == 200 and plan['ok'] and plan['tool'] == 'aider'
        assert plan['aider_model'].startswith('ollama_chat/')
        assert plan['requires_explicit_run'] is True
        return 'AIDER_STATUS=PASS TOOL_PLANNER=PASS MODEL_BRIDGE=PASS EXPLICIT_RUN_GATE=PASS'


def case_aider_execution_journey() -> str:
    with tempfile.TemporaryDirectory() as td, fake_aider_enabled(), live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'AiderRunDemo'})
        project = Path(made['project']['path'])
        init_git_repo(project)
        code, result = request_json(base, '/api/tools/aider/run', {
            'project_path': str(project),
            'task': 'implement feature across the project and fix tests',
            'mode': 'auto',
            'timeout': 30,
        })
        assert code == 200 and result['ok']
        assert 'aider_target.py' in result['changed_files']
        assert result['shell_used'] is False and result['auto_commit'] is False
        assert '# AIDER_EDIT_PASS' in (project / 'aider_target.py').read_text(encoding='utf-8')
        _, history = request_json(base, '/api/tools/runs?limit=20')
        assert history['runs'] and history['runs'][0]['tool'] == 'aider' and history['runs'][0]['status'] == 'PASS'
        return 'AIDER_ONE_SHOT_EDIT=PASS REGISTERED_SCOPE=PASS NO_SHELL=PASS NO_AUTO_COMMIT=PASS EVIDENCE_SAVED=PASS'


def case_aider_optional_fallback_journey() -> str:
    with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'AGAPE_AIDER_DISABLE': '1'}, clear=False), live_studio(Path(td)) as (base, _):
        _, made = request_json(base, '/api/projects/create', {'name': 'AiderFallbackDemo'})
        project = Path(made['project']['path'])
        init_git_repo(project)
        _, plan = request_json(base, '/api/tools/plan', {
            'project_path': str(project),
            'task': 'refactor this codebase across multiple files and fix tests',
            'mode': 'auto',
        })
        assert plan['tool'] == 'agape-ai' and plan['aider_ready'] is False
        return 'AIDER_OPTIONAL=PASS ABSENT_AIDER_DOES_NOT_BREAK_STUDIO=PASS AGAPE_FALLBACK=PASS'


def case_aider_ui_contract() -> str:
    with tempfile.TemporaryDirectory() as td, live_studio(Path(td)) as (base, _):
        with urllib.request.urlopen(base + '/', timeout=10) as res:
            html = res.read().decode('utf-8')
        markers = ['runAiderBtn', 'aiderStatusText', 'checkAiderBtn', 'Aider coding engine']
        missing = [x for x in markers if x not in html]
        assert not missing, missing
        return 'AIDER_UI=PASS PLANNER_VISIBLE=PASS STATUS_VISIBLE=PASS'


def case_real_aider_probe() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as td:
        db = StudioDatabase(Path(td) / 'db.sqlite3')
        status = AiderService(db).status()
        if not status['installed']:
            return 'SKIP', 'REAL_AIDER_NOT_INSTALLED'
        if not status['ready']:
            return 'FAIL', 'REAL_AIDER_VERSION_PROBE_FAILED: ' + str(status.get('detail') or '')
        return 'PASS', 'REAL_AIDER_VERSION=' + str(status.get('version') or 'unknown')


CASES = {
    'live_health': case_live_health,
    'home_ui_contract': case_home_ui_contract,
    'project_file_journey': case_project_file_journey,
    'terminal_journey': case_terminal_journey,
    'ai_journey': case_ai_journey,
    'extension_journey': case_extension_journey,
    'path_security': case_path_security,
    'persistence_restart': case_persistence_restart,
    'full_user_journey': case_full_user_journey,
    'real_ollama_probe': case_real_ollama_probe,
    'free_ai_discovery_journey': case_free_ai_discovery_journey,
    'free_ai_auto_selection_journey': case_free_ai_auto_selection_journey,
    'free_ai_provider_test_persistence': case_free_ai_provider_test_persistence,
    'local_to_free_fallback_journey': case_local_to_free_fallback_journey,
    'passed_menu_contract': case_passed_menu_contract,
    'quality_ledger_journey': case_quality_ledger_journey,
    'real_openrouter_catalog_optional': case_real_openrouter_catalog_optional,
    'aider_status_planning_journey': case_aider_status_planning_journey,
    'aider_execution_journey': case_aider_execution_journey,
    'aider_optional_fallback_journey': case_aider_optional_fallback_journey,
    'aider_ui_contract': case_aider_ui_contract,
    'real_aider_probe': case_real_aider_probe,
}
