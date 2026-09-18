from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
sandbox = Path(tempfile.mkdtemp(prefix='dmt-project-loop-mock-'))
os.environ['DMT_DATA_ROOT'] = str(sandbox / 'data')
sys.path.insert(0, str(root))

try:
    import db
    import project_loop
    from providers import ProviderReply

    db.init_db()
    project = db.create_project('Loop Mock Project')
    pid = int(project['id'])
    workspace = sandbox / 'workspace'
    workspace.mkdir(parents=True)
    source = workspace / 'main.py'
    source.write_text('VALUE = 1\n', encoding='utf-8')

    # Auto-model routing prefers the installed 7B coding model for project work.
    selected = project_loop.auto_select_model(['qwen2.5-coder:1.5b-instruct', 'qwen2.5-coder:7b'], task='Fix failing project tests')
    assert selected['model'] == 'qwen2.5-coder:7b'

    # Workspace and test-command guards fail closed.
    assert project_loop.validate_workspace(str(workspace)) == workspace.resolve()
    try:
        project_loop.safe_file(workspace.resolve(), '../outside.py')
        raise AssertionError('TRAVERSAL_ALLOWED')
    except ValueError:
        pass
    try:
        project_loop.validate_test_command('python -m pytest -q; Remove-Item x')
        raise AssertionError('UNSAFE_TEST_ALLOWED')
    except ValueError:
        pass

    # Windows PowerShell 5.1 boundary: quoted executable paths must not require '&'.
    win_command = r'"C:\Users\Example\AppData\Local\Programs\Python\Python312\python.exe" test_value.py'
    win_parts = project_loop._split_test_command(win_command, windows=True)
    assert win_parts == [r'C:\Users\Example\AppData\Local\Programs\Python\Python312\python.exe', 'test_value.py'], win_parts
    assert '&' not in win_command
    print('PROJECT_LOOP_WINDOWS_QUOTED_EXECUTABLE_PARSE=PASS')

    original_models = project_loop.ollama_models
    original_chat = project_loop.ollama_chat
    original_test = project_loop._run_test

    # End-to-end mocked loop: failing baseline -> model write -> passing test -> model done.
    responses = [
        {'action': 'write_file', 'path': 'main.py', 'content': 'VALUE = 2\n', 'reason': 'Fix expected value'},
        {'action': 'done', 'summary': 'Value fixed and tests pass.'},
    ]

    def fake_models():
        return [{'name': 'qwen2.5-coder:1.5b-instruct'}, {'name': 'qwen2.5-coder:7b'}]

    def fake_chat(model, messages, timeout=None, num_predict=512):
        assert model == 'qwen2.5-coder:7b'
        action = responses.pop(0)
        return ProviderReply('ollama', model, json.dumps(action), 0.01, {})

    def fake_test(root_path, command, project_id=None):
        text = (Path(root_path) / 'main.py').read_text(encoding='utf-8')
        ok = 'VALUE = 2' in text
        return {'ok': ok, 'exit_code': 0 if ok else 1, 'stdout': 'PASS\n' if ok else '', 'stderr': '' if ok else 'expected VALUE = 2', 'duration_seconds': 0.01, 'command': command}

    project_loop.ollama_models = fake_models
    project_loop.ollama_chat = fake_chat
    project_loop._run_test = fake_test

    result = project_loop.run_project_loop(
        pid,
        workspace=str(workspace),
        goal='Change VALUE to 2 and finish with tests passing.',
        test_command='python -m pytest -q',
        max_steps=2,
        auto_model=True,
    )
    assert result['ok'] is True, result
    assert result['overall'] == 'PASS', result
    assert result['model'] == 'qwen2.5-coder:7b'
    assert source.read_text(encoding='utf-8') == 'VALUE = 2\n'
    stored = db.project_loop_run(result['run_id'])
    assert stored and stored['status'] == 'PASS'
    assert any(step['phase'] == 'WRITE_FILE' for step in stored['steps'])
    assert Path(result['backup_root']).exists()

    print('PROJECT_LOOP_MODEL_SELECTION_MOCK=PASS')
    print('PROJECT_LOOP_EDIT_TEST_REPAIR_MOCK=PASS')
    print('PROJECT_LOOP_DATABASE_HISTORY_MOCK=PASS')

    # Rollback proof: an unproven write is restored at the configured limit.
    rollback_project = db.create_project('Rollback Mock Project')
    rollback_pid = int(rollback_project['id'])
    rollback_workspace = sandbox / 'rollback-workspace'
    rollback_workspace.mkdir()
    rollback_file = rollback_workspace / 'main.py'
    rollback_file.write_text('SAFE = 1\n', encoding='utf-8')

    def rollback_chat(model, messages, timeout=None, num_predict=512):
        action = {'action': 'write_file', 'path': 'main.py', 'content': 'SAFE = 0\n', 'reason': 'Intentional failing mock edit'}
        return ProviderReply('ollama', model, json.dumps(action), 0.01, {})

    def rollback_test(root_path, command, project_id=None):
        ok = 'SAFE = 1' in (Path(root_path) / 'main.py').read_text(encoding='utf-8')
        # Baseline passes, edited file fails, restored file passes.
        return {'ok': ok, 'exit_code': 0 if ok else 1, 'stdout': 'PASS\n' if ok else '', 'stderr': '' if ok else 'SAFE regression', 'duration_seconds': 0.01, 'command': command}

    project_loop.ollama_chat = rollback_chat
    project_loop._run_test = rollback_test
    rollback_result = project_loop.run_project_loop(
        rollback_pid,
        workspace=str(rollback_workspace),
        goal='Do not leave a regression behind.',
        test_command='python -m pytest -q',
        max_steps=1,
        auto_model=True,
    )
    assert rollback_result['ok'] is False, rollback_result
    assert rollback_result['overall'] == 'ROLLED_BACK_LIMIT', rollback_result
    assert rollback_file.read_text(encoding='utf-8') == 'SAFE = 1\n'
    assert rollback_result['rollback_test']['ok'] is True

    print('PROJECT_LOOP_FAILED_EDIT_ROLLBACK_MOCK=PASS')

    # Crash journal proof: a run left active with an unproven edit is restored on restart recovery.
    crash_project = db.create_project('Crash Recovery Mock Project')
    crash_pid = int(crash_project['id'])
    crash_workspace = sandbox / 'crash-workspace'
    crash_workspace.mkdir()
    crash_file = crash_workspace / 'main.py'
    crash_file.write_text('CRASH_SAFE = 1\n', encoding='utf-8')
    crash_run = 'LOOP-CRASHMOCK0001'
    db.project_loop_run_start(crash_run, crash_pid, 'Crash recovery proof', str(crash_workspace), 'python -m pytest -q', 'qwen2.5-coder:7b', 2, True)
    crash_backup = Path(project_loop.DATA_ROOT).parent / 'project-loop-backups' / crash_run
    crash_pending = {}
    project_loop._backup_before_write(crash_workspace.resolve(), crash_backup, 'main.py', crash_pending)
    project_loop._write_backup_index(crash_backup, crash_pending, crash_run)
    project_loop._write_text_atomic(crash_file, 'CRASH_SAFE = 0\n')
    assert crash_file.read_text(encoding='utf-8') == 'CRASH_SAFE = 0\n'
    recovered = project_loop.recover_interrupted_edits()
    assert any(x['run_id'] == crash_run and not x['error'] for x in recovered), recovered
    assert crash_file.read_text(encoding='utf-8') == 'CRASH_SAFE = 1\n'
    crash_row = db.project_loop_run(crash_run)
    assert crash_row and crash_row['stage'] == 'INTERRUPTED_RESTART_ROLLBACK'

    print('PROJECT_LOOP_CRASH_ROLLBACK_MOCK=PASS')
finally:
    try:
        if 'project_loop' in globals():
            project_loop.ollama_models = original_models
            project_loop.ollama_chat = original_chat
            project_loop._run_test = original_test
    except Exception:
        pass
    shutil.rmtree(sandbox, ignore_errors=True)
