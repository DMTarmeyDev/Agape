from __future__ import annotations

import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import db
import model_router
from config import BUILD, DATA_ROOT, TERMINAL_TIMEOUT_SECONDS
from providers import ProviderError, ProviderReply, ollama_chat, ollama_models

MAX_STEPS = 8
MAX_INSPECT_FILES = 5
MAX_INSPECT_CHARS = 60000
MAX_EDIT_CHARS = 120000
MAX_FILE_MAP = 300
MAX_TEST_OUTPUT = 16000

TEXT_EXTENSIONS = {
    '.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss',
    '.json', '.md', '.txt', '.ps1', '.psm1', '.cmd', '.bat', '.yml', '.yaml', '.toml',
    '.ini', '.cfg', '.c', '.h', '.cpp', '.hpp', '.cc', '.s', '.asm', '.rs', '.go',
    '.java', '.cs', '.xml', '.sql', '.sh', '.properties', '.gradle', '.cmake',
}
SKIP_DIRS = {
    '.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.idea', '.vscode', 'dist', 'build', 'coverage', '.next',
    '.dmt-backups',
}

ACTION_SYSTEM = """You are the DMT Core Project Loop planner/editor.
Return ONLY one JSON object. No markdown and no prose outside the JSON.
Allowed actions:
1. {"action":"inspect","paths":["relative/file.py"]}
2. {"action":"write_file","path":"relative/file.py","content":"FULL replacement file contents","reason":"short reason"}
3. {"action":"done","summary":"short completion summary"}
Rules:
- Work only on the project goal and the file map supplied by DMT Core.
- Paths must be relative to the project workspace. Never use .. or absolute paths.
- Never ask for administrator access, system changes, downloads, package installation, deletion, disk/BCD/firmware/registry/service changes, or changes outside the workspace.
- DMT Core performs file writes and tests itself. Do not return PowerShell or shell commands.
- For write_file, return the complete intended text of exactly one file.
- Prefer inspecting relevant files before changing unfamiliar code.
- Use the latest test failure as the primary repair evidence.
- Return done only when the goal is satisfied and the current test result is passing.
"""

TEST_DENY = re.compile(
    r"(?i)(?:[;\r\n|&><`]|\b(?:invoke-webrequest|invoke-restmethod|curl|wget|start-process|"
    r"remove-item|set-content|add-content|out-file|new-item|copy-item|move-item|rename-item|"
    r"stop-process|shutdown|restart-computer|stop-computer|format|diskpart|bcdedit|manage-bde|"
    r"reagentc|reg(?:\.exe)?\s|sc(?:\.exe)?\s|schtasks|net\s+user|net\s+localgroup|"
    r"start-bitstransfer|encodedcommand|frombase64string)\b)"
)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_workspace(value: str) -> Path:
    raw = str(value or '').strip().strip('"')
    if not raw:
        raise ValueError('PROJECT_WORKSPACE_REQUIRED')
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('PROJECT_WORKSPACE_NOT_FOUND=' + str(root))
    if root.parent == root:
        raise ValueError('PROJECT_WORKSPACE_ROOT_NOT_ALLOWED')
    home = Path.home().resolve()
    if root == home:
        raise ValueError('PROJECT_WORKSPACE_HOME_ROOT_NOT_ALLOWED')
    core = Path(__file__).resolve().parent
    data = DATA_ROOT.resolve()
    for protected, label in ((core, 'CORE_PROGRAM'), (data, 'CORE_DATA')):
        if _inside(root, protected) or _inside(protected, root):
            raise ValueError('PROJECT_WORKSPACE_OVERLAPS_' + label)
    return root


def safe_file(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    rel = str(relative or '').strip().replace('\\', '/')
    if not rel or rel.startswith('/') or re.match(r'^[A-Za-z]:', rel):
        raise ValueError('RELATIVE_PROJECT_PATH_REQUIRED')
    parts = Path(rel).parts
    if '..' in parts:
        raise ValueError('PROJECT_PATH_TRAVERSAL_BLOCKED')
    path = (root / Path(*parts)).resolve()
    if not _inside(path, root):
        raise ValueError('PROJECT_PATH_OUTSIDE_WORKSPACE')
    if path.exists() and path.is_symlink():
        raise ValueError('PROJECT_SYMLINK_FILE_BLOCKED')
    if must_exist and not path.is_file():
        raise ValueError('PROJECT_FILE_NOT_FOUND=' + rel)
    return path


def file_map(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(root.rglob('*')):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS and path.name.lower() not in {'dockerfile', 'makefile'}:
                continue
            size = path.stat().st_size
        except OSError:
            continue
        out.append({'path': rel.as_posix(), 'bytes': int(size)})
        if len(out) >= MAX_FILE_MAP:
            break
    return out


def inspect_files(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    if not isinstance(paths, list) or not paths:
        raise ValueError('INSPECT_PATHS_REQUIRED')
    if len(paths) > MAX_INSPECT_FILES:
        raise ValueError('TOO_MANY_INSPECT_PATHS')
    remaining = MAX_INSPECT_CHARS
    output: list[dict[str, Any]] = []
    for rel in paths:
        path = safe_file(root, str(rel), must_exist=True)
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name.lower() not in {'dockerfile', 'makefile'}:
            raise ValueError('NON_TEXT_PROJECT_FILE_BLOCKED=' + str(rel))
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig', errors='replace')
        chunk = text[:remaining]
        output.append({
            'path': path.relative_to(root).as_posix(),
            'content': chunk,
            'truncated': len(text) > len(chunk),
            'chars': len(text),
        })
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return output


def _parse_action(text: str) -> dict[str, Any]:
    raw = str(text or '').strip()
    fenced = re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```', raw, flags=re.I | re.S)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise ValueError('PROJECT_LOOP_MODEL_JSON_INVALID=' + str(exc)) from None
    if not isinstance(value, dict):
        raise ValueError('PROJECT_LOOP_MODEL_ACTION_NOT_OBJECT')
    action = str(value.get('action') or '').strip().lower()
    if action not in {'inspect', 'write_file', 'done'}:
        raise ValueError('PROJECT_LOOP_MODEL_ACTION_INVALID=' + action)
    if action == 'inspect':
        paths = value.get('paths')
        if not isinstance(paths, list) or not paths or len(paths) > MAX_INSPECT_FILES:
            raise ValueError('PROJECT_LOOP_INSPECT_PATHS_INVALID')
        return {'action': action, 'paths': [str(x) for x in paths]}
    if action == 'write_file':
        path = str(value.get('path') or '').strip()
        content = value.get('content')
        if not path or not isinstance(content, str):
            raise ValueError('PROJECT_LOOP_WRITE_ACTION_INVALID')
        if len(content) > MAX_EDIT_CHARS:
            raise ValueError('PROJECT_LOOP_WRITE_TOO_LARGE')
        return {'action': action, 'path': path, 'content': content, 'reason': str(value.get('reason') or '')[:500]}
    return {'action': action, 'summary': str(value.get('summary') or '')[:2000]}


def _model_action(model: str, prompt: str) -> tuple[dict[str, Any], float]:
    messages = [
        {'role': 'system', 'content': ACTION_SYSTEM},
        {'role': 'user', 'content': prompt},
    ]
    total = 0.0
    last = ''
    for attempt in range(2):
        reply = ollama_chat(model, messages, num_predict=1800)
        total += reply.duration_seconds
        last = reply.content
        try:
            return _parse_action(last), total
        except ValueError:
            if attempt == 0:
                messages += [
                    {'role': 'assistant', 'content': last},
                    {'role': 'user', 'content': 'Your response was invalid. Return exactly one allowed JSON action object and nothing else.'},
                ]
    raise ValueError('PROJECT_LOOP_MODEL_RETURNED_NO_VALID_ACTION=' + last[:500].replace('\n', ' '))


def auto_select_model(models: list[dict[str, Any]] | list[str] | None = None, task: str = "") -> dict[str, Any]:
    """Choose the best installed local model for the current development job.

    Coding/debug/refactor work prefers the strongest practical coder model. Very small
    inspection/documentation jobs may use the faster 1.5B model when present.
    """
    source = ollama_models() if models is None else models
    names: list[str] = []
    for item in source:
        name = str(item.get('name') or '') if isinstance(item, dict) else str(item)
        if name and name not in names:
            names.append(name)
    if not names:
        raise ProviderError('NO_OLLAMA_MODELS_AVAILABLE')

    lower = {n.lower(): n for n in names}
    task_l = str(task or '').lower()
    heavy = any(k in task_l for k in (
        'fix', 'repair', 'debug', 'implement', 'build', 'refactor', 'error', 'fail',
        'test', 'feature', 'code', 'project', 'function', 'class', 'api', 'database',
    ))
    light = bool(task_l) and not heavy and any(k in task_l for k in (
        'inspect', 'read', 'review', 'explain', 'document', 'rename', 'format', 'comment',
    ))

    if light:
        for wanted in ('qwen2.5-coder:1.5b-instruct', 'qwen2.5-coder:1.5b'):
            if wanted in lower:
                return {'model': lower[wanted], 'reason': 'FAST_MODEL_FOR_LIGHT_TASK', 'models': names}

    for wanted in (
        'qwen2.5-coder:7b',
        'qwen2.5-coder:7b-instruct',
        'qwen2.5-coder:3b',
        'qwen2.5-coder:3b-instruct',
        'qwen2.5-coder:1.5b-instruct',
        'qwen2.5-coder:1.5b',
    ):
        if wanted in lower:
            return {'model': lower[wanted], 'reason': 'CODING_PREFERENCE', 'models': names}

    def score(name: str) -> tuple[int, float, str]:
        n = name.lower()
        coder = 100 if 'coder' in n or 'code' in n else 0
        qwen = 25 if 'qwen' in n else 0
        size = 0.0
        m = re.search(r'(?<![\d.])(\d+(?:\.\d+)?)b\b', n)
        if m:
            try:
                size = min(float(m.group(1)), 14.0)
            except ValueError:
                size = 0.0
        oversize_penalty = -50 if size > 14 else 0
        return (coder + qwen + int(size * 4) + oversize_penalty, size, n)

    selected = max(names, key=score)
    return {'model': selected, 'reason': 'BEST_AVAILABLE_CODING_MODEL', 'models': names}

def validate_test_command(command: str) -> str:
    cmd = str(command or '').strip()
    if not cmd:
        raise ValueError('PROJECT_TEST_COMMAND_REQUIRED')
    if len(cmd) > 1200:
        raise ValueError('PROJECT_TEST_COMMAND_TOO_LONG')
    if TEST_DENY.search(cmd):
        raise ValueError('PROJECT_TEST_COMMAND_UNSAFE')
    stripped = cmd.lstrip()
    if stripped.startswith('"'):
        end = stripped.find('"', 1)
        if end < 0:
            raise ValueError('PROJECT_TEST_COMMAND_QUOTE_INVALID')
        first = stripped[1:end]
    else:
        first = stripped.split(None, 1)[0].strip('"\'')
    first_base = re.split(r'[\\/]', first)[-1].lower()
    allowed = {
        'python', 'python.exe', 'py', 'py.exe', 'pytest', 'pytest.exe', 'node', 'node.exe',
        'npm', 'npm.cmd', 'npx', 'npx.cmd', 'dotnet', 'dotnet.exe', 'cargo', 'cargo.exe',
        'go', 'go.exe', 'ctest', 'ctest.exe', 'ninja', 'ninja.exe', 'make', 'make.exe',
    }
    # Quoted absolute Python paths are allowed by checking the executable basename.
    if first_base not in allowed and not first_base.startswith('python'):
        raise ValueError('PROJECT_TEST_COMMAND_NOT_ALLOWLISTED=' + first_base)
    return cmd


def autodetect_test_command(root: Path) -> str:
    py = '"' + sys.executable.replace('"', '') + '"'
    if (root / 'pytest.ini').is_file() or (root / 'pyproject.toml').is_file() or any(root.glob('test_*.py')) or (root / 'tests').is_dir():
        return py + ' -m pytest -q'
    if (root / 'package.json').is_file():
        try:
            package = json.loads((root / 'package.json').read_text(encoding='utf-8-sig'))
            test = str((package.get('scripts') or {}).get('test') or '')
            if test and 'no test specified' not in test.lower():
                return 'npm test'
        except Exception:
            pass
    raise ValueError('PROJECT_TEST_AUTODETECT_FAILED_ENTER_TEST_COMMAND')


def _split_test_command(command: str, *, windows: bool | None = None) -> list[str]:
    """Split an already safety-validated test command without invoking a shell.

    Windows PowerShell requires the call operator to execute a quoted executable path.
    Project Loop deliberately forbids shell operators, so tests are parsed and launched
    directly instead. This keeps quoted Python paths PowerShell-5.1 compatible while
    preserving the command allowlist and no-shell safety boundary.
    """
    cmd = validate_test_command(command)
    is_windows = (os.name == 'nt') if windows is None else bool(windows)
    try:
        parts = shlex.split(cmd, posix=not is_windows)
    except ValueError as exc:
        raise ValueError('PROJECT_TEST_COMMAND_PARSE_FAILED=' + str(exc)) from None
    cleaned: list[str] = []
    for part in parts:
        value = str(part)
        if is_windows and len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        cleaned.append(value)
    if not cleaned:
        raise ValueError('PROJECT_TEST_COMMAND_PARSE_EMPTY')
    return cleaned


def _test_argv(command: str) -> list[str]:
    parts = _split_test_command(command)
    executable = parts[0]
    resolved = executable if Path(executable).is_file() else shutil.which(executable)
    if not resolved:
        raise ValueError('PROJECT_TEST_EXECUTABLE_NOT_FOUND=' + executable)
    argv = [str(resolved), *parts[1:]]
    if os.name == 'nt' and Path(str(resolved)).suffix.lower() in {'.cmd', '.bat'}:
        comspec = os.environ.get('COMSPEC') or os.path.join(
            os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'cmd.exe'
        )
        return [comspec, '/d', '/s', '/c', subprocess.list2cmdline(argv)]
    return argv


def _run_test(root: Path, command: str, project_id: int | None = None) -> dict[str, Any]:
    cmd = validate_test_command(command)
    started = time.monotonic()
    job_id = 'TERM-' + uuid.uuid4().hex[:16].upper()
    db.terminal_job_create(job_id, int(project_id) if project_id else None, cmd, 'project_test')
    try:
        argv = _test_argv(cmd)
        cp = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, errors='replace', timeout=TERMINAL_TIMEOUT_SECONDS)
        stdout = cp.stdout[-MAX_TEST_OUTPUT:]
        stderr = cp.stderr[-MAX_TEST_OUTPUT:]
        db.terminal_job_finish(job_id, int(cp.returncode), stdout, stderr)
        return {
            'ok': cp.returncode == 0,
            'executed': True,
            'job_id': job_id,
            'exit_code': int(cp.returncode),
            'stdout': stdout,
            'stderr': stderr,
            'duration_seconds': round(time.monotonic() - started, 3),
            'command': cmd,
            'risk': 'project_test',
        }
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ''
        err = exc.stderr if isinstance(exc.stderr, str) else ''
        stderr = (err + '\nTIMEOUT')[-MAX_TEST_OUTPUT:]
        db.terminal_job_finish(job_id, 124, out[-MAX_TEST_OUTPUT:], stderr)
        return {
            'ok': False,
            'executed': True,
            'job_id': job_id,
            'exit_code': 124,
            'stdout': out[-MAX_TEST_OUTPUT:],
            'stderr': stderr,
            'duration_seconds': round(time.monotonic() - started, 3),
            'command': cmd,
            'risk': 'project_test',
        }

def _backup_before_write(root: Path, backup_root: Path, relative: str, pending: dict[str, dict[str, Any]]) -> Path:
    target = safe_file(root, relative)
    key = target.relative_to(root).as_posix()
    if key in pending:
        return target
    backup_path = backup_root / key
    existed = target.is_file()
    if existed:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
    pending[key] = {'existed': existed, 'backup': str(backup_path), 'target': str(target)}
    return target


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.dmt-tmp-' + uuid.uuid4().hex[:8])
    try:
        tmp.write_text(content, encoding='utf-8', newline='')
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def _write_backup_index(backup_root: Path, pending: dict[str, dict[str, Any]], run_id: str) -> None:
    backup_root.mkdir(parents=True, exist_ok=True)
    index = {'run_id': run_id, 'entries': pending}
    (backup_root / 'backup-index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')


def _rollback_pending(root: Path, pending: dict[str, dict[str, Any]]) -> list[str]:
    restored: list[str] = []
    for rel, item in reversed(list(pending.items())):
        target = safe_file(root, rel)
        if bool(item.get('existed')):
            backup = Path(str(item.get('backup') or ''))
            if not backup.is_file():
                raise RuntimeError('PROJECT_LOOP_BACKUP_MISSING=' + rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        else:
            if target.is_file():
                target.unlink()
        restored.append(rel)
    return restored


def _prompt(project: dict[str, Any], goal: str, root: Path, step: int, max_steps: int, test: dict[str, Any], inspected: list[dict[str, Any]] | None = None) -> str:
    fmap = file_map(root)
    info = {
        'project': {'id': project.get('id'), 'name': project.get('name')},
        'goal': goal,
        'workspace': str(root),
        'step': step,
        'max_steps': max_steps,
        'test': test,
        'files': fmap,
        'inspected_files': inspected or [],
    }
    return (
        'Choose the single safest next action for this project. The current automated test result is authoritative. '
        'If it fails, repair the failure. If it passes but the goal is not complete, make one focused change. '
        'If the goal is complete and the test passes, return done.\nSTATE_JSON:\n' + json.dumps(info, ensure_ascii=False)
    )


def recover_interrupted_edits() -> list[dict[str, Any]]:
    """Restore only journaled, unproven edits from runs left active by a process crash."""
    recovered: list[dict[str, Any]] = []
    running = db.rows("SELECT run_id,project_id,workspace FROM project_loop_runs WHERE status='running' ORDER BY created_at ASC")
    for item in running:
        run_id = str(item.get('run_id') or '')
        workspace = str(item.get('workspace') or '')
        backup_root = DATA_ROOT.parent / 'project-loop-backups' / run_id
        index_path = backup_root / 'backup-index.json'
        restored: list[str] = []
        error = ''
        try:
            root = validate_workspace(workspace)
            pending: dict[str, dict[str, Any]] = {}
            if index_path.is_file():
                value = json.loads(index_path.read_text(encoding='utf-8-sig'))
                entries = value.get('entries', {}) if isinstance(value, dict) else {}
                if isinstance(entries, dict):
                    pending = {str(k): v for k, v in entries.items() if isinstance(v, dict)}
            if pending:
                restored = _rollback_pending(root, pending)
                pending.clear()
                _write_backup_index(backup_root, pending, run_id)
            db.project_loop_run_finish(run_id, 'interrupted', 'INTERRUPTED_RESTART_ROLLBACK', 0, 'Process restarted; journaled unproven edits were restored.', '')
        except Exception as exc:
            error = str(exc)
            try:
                db.project_loop_run_finish(run_id, 'interrupted', 'INTERRUPTED_RESTART_ROLLBACK_FAILED', 0, 'Process restarted; automatic rollback could not be fully confirmed.', error)
            except Exception:
                pass
        recovered.append({'run_id': run_id, 'restored': restored, 'error': error})
    return recovered


def configure_project_loop(project_id: int, workspace: str, goal: str, test_command: str = '', max_steps: int = 4, auto_model: bool = True, model: str = '') -> dict[str, Any]:
    project = db.project(int(project_id))
    if not project:
        raise ValueError('PROJECT_NOT_FOUND')
    root = validate_workspace(workspace)
    goal = str(goal or '').strip()
    if not goal:
        raise ValueError('PROJECT_GOAL_REQUIRED')
    if len(goal) > 5000:
        raise ValueError('PROJECT_GOAL_TOO_LONG')
    steps = max(1, min(int(max_steps), MAX_STEPS))
    test = str(test_command or '').strip()
    if test:
        test = validate_test_command(test)
    else:
        test = autodetect_test_command(root)
    selected = str(model or '').strip()
    if not auto_model and not selected:
        raise ValueError('PROJECT_MODEL_REQUIRED_WHEN_AUTO_MODEL_OFF')
    db.save_project_loop_settings(int(project_id), str(root), goal, test, steps, bool(auto_model), selected)
    return db.project_loop_settings(int(project_id)) or {}


def run_project_loop(project_id: int, *, workspace: str = '', goal: str = '', test_command: str = '', max_steps: int | None = None, auto_model: bool | None = None, model: str = '') -> dict[str, Any]:
    project_id = int(project_id)
    project = db.project(project_id)
    if not project:
        raise ValueError('PROJECT_NOT_FOUND')
    saved = db.project_loop_settings(project_id) or {}
    workspace_value = str(workspace or saved.get('workspace') or '')
    goal_value = str(goal or saved.get('goal') or '').strip()
    test_value = str(test_command or saved.get('test_command') or '').strip()
    steps = int(max_steps if max_steps is not None else (saved.get('max_steps') or 4))
    use_auto = bool(saved.get('auto_model', 1)) if auto_model is None else bool(auto_model)
    requested_model = str(model or saved.get('model') or '').strip()

    root = validate_workspace(workspace_value)
    if not goal_value:
        raise ValueError('PROJECT_GOAL_REQUIRED')
    steps = max(1, min(steps, MAX_STEPS))
    if not test_value:
        test_value = autodetect_test_command(root)
    test_value = validate_test_command(test_value)

    if use_auto:
        choice = auto_select_model(task=goal_value)
        selected_model = str(choice['model'])
        model_reason = str(choice['reason'])
    else:
        selected_model = requested_model
        if not selected_model:
            raise ValueError('PROJECT_MODEL_REQUIRED_WHEN_AUTO_MODEL_OFF')
        installed = [str(m.get('name') or '') for m in ollama_models()]
        if selected_model not in installed:
            raise ValueError('PROJECT_MODEL_NOT_INSTALLED=' + selected_model)
        model_reason = 'USER_SELECTED'

    # Persist resolved configuration before starting the run.
    db.save_project_loop_settings(project_id, str(root), goal_value, test_value, steps, use_auto, requested_model)

    run_id = 'LOOP-' + uuid.uuid4().hex[:16].upper()
    backup_root = DATA_ROOT.parent / 'project-loop-backups' / run_id
    db.project_loop_run_start(run_id, project_id, goal_value, str(root), test_value, selected_model, steps, use_auto)
    pending: dict[str, dict[str, Any]] = {}
    started = time.monotonic()
    edits: list[str] = []
    model_seconds = 0.0

    try:
        baseline = _run_test(root, test_value, project_id)
        db.project_loop_step_add(run_id, 0, 'TEST_BASELINE', 'PASS' if baseline['ok'] else 'FAIL', {'test': baseline})
        last_test = baseline

        for step in range(1, steps + 1):
            db.project_loop_run_update(run_id, 'running', 'MODEL', step)
            inspected: list[dict[str, Any]] = []
            action: dict[str, Any] | None = None
            for interaction in range(3):
                prompt = _prompt(project, goal_value, root, step, steps, last_test, inspected)
                action, seconds = _model_action(selected_model, prompt)
                model_seconds += seconds
                db.project_loop_step_add(run_id, step, 'MODEL_ACTION', 'PASS', {'action': action, 'interaction': interaction + 1, 'model': selected_model})
                if action['action'] == 'inspect':
                    inspected = inspect_files(root, action['paths'])
                    db.project_loop_step_add(run_id, step, 'INSPECT', 'PASS', {'files': [{'path': x['path'], 'chars': x['chars'], 'truncated': x['truncated']} for x in inspected]})
                    continue
                break

            if not action:
                raise RuntimeError('PROJECT_LOOP_NO_ACTION')
            if action['action'] == 'inspect':
                raise RuntimeError('PROJECT_LOOP_INSPECT_LIMIT_REACHED')

            if action['action'] == 'done':
                final_test = _run_test(root, test_value, project_id)
                last_test = final_test
                db.project_loop_step_add(run_id, step, 'FINAL_TEST', 'PASS' if final_test['ok'] else 'FAIL', {'test': final_test, 'summary': action.get('summary', '')})
                if final_test['ok']:
                    pending.clear()
                    _write_backup_index(backup_root, pending, run_id)
                    db.project_loop_run_finish(run_id, 'PASS', 'DONE', step, action.get('summary', ''), '')
                    return {
                        'ok': True,
                        'overall': 'PASS',
                        'run_id': run_id,
                        'project_id': project_id,
                        'project': project.get('name'),
                        'workspace': str(root),
                        'goal': goal_value,
                        'model': selected_model,
                        'model_reason': model_reason,
                        'steps_used': step,
                        'max_steps': steps,
                        'test': final_test,
                        'edits': edits,
                        'backup_root': str(backup_root),
                        'duration_seconds': round(time.monotonic() - started, 3),
                        'model_seconds': round(model_seconds, 3),
                        'summary': action.get('summary', ''),
                    }
                # A model cannot declare success over a failing test. Continue with that failure.
                continue

            rel = str(action['path'])
            target = safe_file(root, rel)
            if target.suffix.lower() not in TEXT_EXTENSIONS and target.name.lower() not in {'dockerfile', 'makefile'}:
                raise ValueError('PROJECT_LOOP_EDIT_NON_TEXT_BLOCKED=' + rel)
            _backup_before_write(root, backup_root, rel, pending)
            _write_backup_index(backup_root, pending, run_id)
            _write_text_atomic(target, str(action['content']))
            edits.append(rel)
            db.project_loop_step_add(run_id, step, 'WRITE_FILE', 'PASS', {'path': rel, 'reason': action.get('reason', ''), 'chars': len(str(action['content'])), 'sha256': _sha256(target)})

            db.project_loop_run_update(run_id, 'running', 'TEST', step)
            last_test = _run_test(root, test_value, project_id)
            db.project_loop_step_add(run_id, step, 'TEST', 'PASS' if last_test['ok'] else 'FAIL', {'test': last_test})
            if last_test['ok']:
                # This is the new last-known-good state. Backups remain on disk for audit/manual recovery,
                # but later rollback only applies to changes made after this passing point.
                pending.clear()
                _write_backup_index(backup_root, pending, run_id)

        # Bounded loop reached its configured step limit.
        if last_test.get('ok'):
            db.project_loop_run_finish(run_id, 'paused', 'PAUSED_LIMIT', steps, 'Step limit reached with tests passing.', '')
            return {
                'ok': True,
                'overall': 'PAUSED_LIMIT',
                'run_id': run_id,
                'project_id': project_id,
                'project': project.get('name'),
                'workspace': str(root),
                'goal': goal_value,
                'model': selected_model,
                'model_reason': model_reason,
                'steps_used': steps,
                'max_steps': steps,
                'test': last_test,
                'edits': edits,
                'backup_root': str(backup_root),
                'duration_seconds': round(time.monotonic() - started, 3),
                'model_seconds': round(model_seconds, 3),
                'summary': 'Step limit reached safely; current tests pass. Run again to continue if the goal is not complete.',
            }

        restored = _rollback_pending(root, pending) if pending else []
        pending.clear()
        _write_backup_index(backup_root, pending, run_id)
        rollback_test = _run_test(root, test_value, project_id)
        db.project_loop_step_add(run_id, steps, 'ROLLBACK', 'PASS', {'restored': restored, 'test_after_restore': rollback_test})
        db.project_loop_run_finish(run_id, 'failed', 'ROLLED_BACK_LIMIT', steps, 'Repair limit reached; unproven edits were restored.', 'TEST_STILL_FAILING')
        return {
            'ok': False,
            'overall': 'ROLLED_BACK_LIMIT',
            'run_id': run_id,
            'project_id': project_id,
            'project': project.get('name'),
            'workspace': str(root),
            'goal': goal_value,
            'model': selected_model,
            'model_reason': model_reason,
            'steps_used': steps,
            'max_steps': steps,
            'test': last_test,
            'rollback_test': rollback_test,
            'restored': restored,
            'edits': edits,
            'backup_root': str(backup_root),
            'duration_seconds': round(time.monotonic() - started, 3),
            'model_seconds': round(model_seconds, 3),
            'summary': 'Step limit reached while tests failed. Unproven edits were restored to the last passing/starting state.',
        }
    except Exception as exc:
        restored: list[str] = []
        rollback_error = ''
        try:
            if pending:
                restored = _rollback_pending(root, pending)
                pending.clear()
                _write_backup_index(backup_root, pending, run_id)
        except Exception as rb_exc:
            rollback_error = str(rb_exc)
        error = str(exc)
        if rollback_error:
            error += '; ROLLBACK_ERROR=' + rollback_error
        db.project_loop_run_finish(run_id, 'failed', 'FAILED', 0, 'Project loop failed safely.', error)
        return {
            'ok': False,
            'overall': 'FAIL',
            'run_id': run_id,
            'project_id': project_id,
            'project': project.get('name'),
            'workspace': str(root),
            'goal': goal_value,
            'model': selected_model,
            'model_reason': model_reason,
            'edits': edits,
            'restored': restored,
            'backup_root': str(backup_root),
            'duration_seconds': round(time.monotonic() - started, 3),
            'model_seconds': round(model_seconds, 3),
            'error': error,
        }
